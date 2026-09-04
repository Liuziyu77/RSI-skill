#!/usr/bin/env python3
"""Portable, approval-gated storage and retrieval for the RSI skill.

The CLI deliberately does not generate lessons. An agent proposes and a user
approves content; this helper validates, persists, retrieves, and audits it.
It uses only the Python standard library and supports Python 3.8+.
"""

from __future__ import print_function

import argparse
import contextlib
import datetime as dt
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import unicodedata


VERSION = "0.2.0"
KINDS = {"preference", "procedure", "pitfall", "constraint", "decision", "tooling"}
OUTCOMES = {"success", "failure", "neutral"}
ID_RE = re.compile(r"^xp-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}(?:-[0-9]+)?$")
SECRET_PATTERNS = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.I)),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("API token", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    (
        "assigned secret",
        re.compile(
            r"\b(?:password|passwd|api[_-]?key|access[_-]?token)\s*[:=]\s*[^\s,;]{8,}",
            re.I,
        ),
    ),
]
REQUIRED_EXPERIENCE_FIELDS = (
    "kind",
    "title",
    "lesson",
    "scope",
    "task_types",
    "applicability",
    "evidence",
    "confidence",
    "tags",
)
OPTIONAL_EXPERIENCE_FIELDS = ("avoid", "source_task")


class RSIError(Exception):
    """A user-correctable CLI error."""


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compact_timestamp(iso_timestamp):
    return iso_timestamp.replace("-", "").replace(":", "")


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def candidate_fingerprint(candidate):
    selected = {key: candidate.get(key) for key in REQUIRED_EXPERIENCE_FIELDS + OPTIONAL_EXPERIENCE_FIELDS}
    return hashlib.sha256(canonical_json(selected).encode("utf-8")).hexdigest()


def normalize_space(value):
    return " ".join(value.split())


def require_text(value, field, minimum=1, maximum=4000):
    if not isinstance(value, str):
        raise RSIError("%s must be a string" % field)
    clean = normalize_space(value)
    if len(clean) < minimum or len(clean) > maximum:
        raise RSIError("%s must contain %d..%d characters" % (field, minimum, maximum))
    if any(unicodedata.category(char) == "Cc" for char in clean):
        raise RSIError("%s contains control characters" % field)
    return clean


def require_string_list(value, field, minimum=0, maximum=30, item_maximum=240):
    if not isinstance(value, list):
        raise RSIError("%s must be an array" % field)
    if len(value) < minimum or len(value) > maximum:
        raise RSIError("%s must contain %d..%d items" % (field, minimum, maximum))
    clean = [require_text(item, "%s[]" % field, 1, item_maximum) for item in value]
    folded = [item.casefold() for item in clean]
    if len(set(folded)) != len(folded):
        raise RSIError("%s contains duplicate items" % field)
    return clean


def scan_secrets(value):
    text = canonical_json(value)
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            raise RSIError("candidate appears to contain a %s; generalize it before saving" % label)


def validate_experience(candidate):
    if not isinstance(candidate, dict):
        raise RSIError("each experience candidate must be a JSON object")
    unknown = set(candidate) - set(REQUIRED_EXPERIENCE_FIELDS) - set(OPTIONAL_EXPERIENCE_FIELDS)
    missing = set(REQUIRED_EXPERIENCE_FIELDS) - set(candidate)
    if missing:
        raise RSIError("experience is missing fields: %s" % ", ".join(sorted(missing)))
    if unknown:
        raise RSIError("experience has unknown fields: %s" % ", ".join(sorted(unknown)))
    if candidate["kind"] not in KINDS:
        raise RSIError("kind must be one of: %s" % ", ".join(sorted(KINDS)))
    confidence = candidate["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise RSIError("confidence must be a number from 0 to 1")

    clean = {
        "kind": candidate["kind"],
        "title": require_text(candidate["title"], "title", 3, 120),
        "lesson": require_text(candidate["lesson"], "lesson", 8, 4000),
        "scope": require_text(candidate["scope"], "scope", 1, 160),
        "task_types": require_string_list(candidate["task_types"], "task_types", 1, 20, 80),
        "applicability": require_string_list(candidate["applicability"], "applicability", 1, 20, 240),
        "evidence": require_text(candidate["evidence"], "evidence", 3, 2000),
        "confidence": round(float(confidence), 4),
        "tags": require_string_list(candidate["tags"], "tags", 0, 30, 80),
    }
    if "avoid" in candidate:
        clean["avoid"] = require_text(candidate["avoid"], "avoid", 1, 2000)
    if "source_task" in candidate:
        clean["source_task"] = require_text(candidate["source_task"], "source_task", 1, 200)
    scan_secrets(clean)
    return clean


def validate_memory(candidate):
    if not isinstance(candidate, dict):
        raise RSIError("each memory candidate must be a JSON object")
    required = {"statement", "scope", "evidence"}
    missing = required - set(candidate)
    unknown = set(candidate) - required
    if missing:
        raise RSIError("memory is missing fields: %s" % ", ".join(sorted(missing)))
    if unknown:
        raise RSIError("memory has unknown fields: %s" % ", ".join(sorted(unknown)))
    clean = {
        "statement": require_text(candidate["statement"], "statement", 8, 1000),
        "scope": require_text(candidate["scope"], "scope", 1, 160),
        "evidence": require_text(candidate["evidence"], "evidence", 3, 1000),
    }
    scan_secrets(clean)
    return clean


def load_json_input(path_value):
    if path_value == "-":
        raw = sys.stdin.read()
    else:
        try:
            raw = Path(path_value).read_text(encoding="utf-8")
        except OSError as exc:
            raise RSIError("cannot read input: %s" % exc)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RSIError("input is not valid JSON: %s" % exc)
    return value if isinstance(value, list) else [value]


def ensure_approved(args):
    if not getattr(args, "approved", False):
        raise RSIError("write refused: obtain user approval, then pass --approved")


def atomic_write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=str(path.parent), prefix=".rsi-", suffix=".tmp", delete=False
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


@contextlib.contextmanager
def store_lock(store, timeout=5.0):
    store.mkdir(parents=True, exist_ok=True)
    lock_path = store / ".lock"
    deadline = time.monotonic() + timeout
    descriptor = None
    while descriptor is None:
        try:
            descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise RSIError("store is busy (lock %s); retry after the other writer finishes" % lock_path)
            time.sleep(0.05)
    try:
        os.write(descriptor, ("pid=%d time=%s\n" % (os.getpid(), utc_now())).encode("utf-8"))
        os.close(descriptor)
        descriptor = None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def append_audit(store, operation, targets):
    entry = {
        "schema_version": 1,
        "timestamp": utc_now(),
        "operation": operation,
        "targets": targets,
        "approval_asserted": True,
    }
    audit_path = store / "audit.jsonl"
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(entry) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def iter_records(store, include_archived=False):
    directory = store / "experiences"
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("xp-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RSIError("invalid record %s: %s" % (path, exc))
        if include_archived or record.get("status", "active") == "active":
            yield record


def iter_trashed_records(store):
    directory = store / "trash"
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("xp-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RSIError("invalid trashed record %s: %s" % (path, exc))
        record = dict(record)
        record["status"] = "trashed"
        yield record


def make_record(candidate, created_at, suffix=0):
    fingerprint = candidate_fingerprint(candidate)
    identifier = "xp-%s-%s" % (compact_timestamp(created_at), fingerprint[:8])
    if suffix:
        identifier += "-%d" % suffix
    record = {
        "schema_version": 1,
        "id": identifier,
        **candidate,
        "status": "active",
        "created_at": created_at,
        "updated_at": created_at,
        "fingerprint": fingerprint,
        "provenance": {"approved_by": "user", "approved_at": created_at},
        "outcomes": {"uses": 0, "successes": 0, "failures": 0, "last_outcome_at": None},
    }
    return record


def command_init(args):
    ensure_approved(args)
    store = args.store
    with store_lock(store):
        (store / "experiences").mkdir(parents=True, exist_ok=True)
        (store / "trash").mkdir(parents=True, exist_ok=True)
        (store / "generated-skills").mkdir(parents=True, exist_ok=True)
        readme = store / "README.md"
        if not readme.exists():
            readme.write_text(
                "# RSI store\n\nThis directory contains user-approved derived memory and experience.\n",
                encoding="utf-8",
            )
        append_audit(store, "init", [str(store)])
    print("Initialized RSI store: %s" % store)


def command_preview_experience(args):
    candidates = [validate_experience(item) for item in load_json_input(args.input)]
    for index, item in enumerate(candidates, 1):
        print("E%d · experience · %s · %s" % (index, item["kind"], item["scope"]))
        print("Title: %s" % item["title"])
        print("Lesson: %s" % item["lesson"])
        print("Applies when: %s" % "; ".join(item["applicability"]))
        if item.get("avoid"):
            print("Avoid: %s" % item["avoid"])
        print("Evidence: %s" % item["evidence"])
        print("Confidence: %.2f" % item["confidence"])
        if index != len(candidates):
            print()


def command_save_experience(args):
    ensure_approved(args)
    candidates = [validate_experience(item) for item in load_json_input(args.input)]
    fingerprints = [candidate_fingerprint(item) for item in candidates]
    if len(set(fingerprints)) != len(fingerprints):
        raise RSIError("input contains duplicate experience candidates")

    store = args.store
    created_at = utc_now()
    saved = []
    with store_lock(store):
        existing = list(iter_records(store, include_archived=True)) + list(iter_trashed_records(store))
        existing_fingerprints = {record.get("fingerprint") for record in existing}
        duplicates = [fp for fp in fingerprints if fp in existing_fingerprints]
        if duplicates:
            raise RSIError("duplicate experience already exists; no records were saved")

        used_ids = {record.get("id") for record in existing}
        for candidate in candidates:
            suffix = 0
            record = make_record(candidate, created_at, suffix)
            while record["id"] in used_ids:
                suffix += 1
                record = make_record(candidate, created_at, suffix)
            used_ids.add(record["id"])
            destination = store / "experiences" / (record["id"] + ".json")
            atomic_write_json(destination, record)
            saved.append((record["id"], destination))
        append_audit(store, "save-experience", [item[0] for item in saved])

    for identifier, destination in saved:
        print("Saved %s -> %s" % (identifier, destination))


def memory_key(candidate):
    return "%s\0%s" % (candidate["scope"].casefold(), normalize_space(candidate["statement"]).casefold())


def command_save_memory(args):
    ensure_approved(args)
    candidates = [validate_memory(item) for item in load_json_input(args.input)]
    keys = [memory_key(item) for item in candidates]
    if len(keys) != len(set(keys)):
        raise RSIError("input contains duplicate memory candidates")

    store = args.store
    saved = []
    with store_lock(store):
        memory_path = store / "memory.md"
        existing = memory_path.read_text(encoding="utf-8") if memory_path.exists() else ""
        for candidate in candidates:
            marker = "<!-- rsi-memory:%s -->" % hashlib.sha256(memory_key(candidate).encode("utf-8")).hexdigest()[:16]
            if marker in existing:
                continue
            block = (
                "\n%s\n- **%s** — %s\n  - Evidence: %s\n"
                % (marker, candidate["scope"], candidate["statement"], candidate["evidence"])
            )
            existing += block
            saved.append(marker)
        if saved:
            if not existing.startswith("# Approved RSI memory"):
                existing = "# Approved RSI memory\n" + existing
            memory_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = memory_path.with_name(".memory.md.tmp-%d" % os.getpid())
            try:
                temporary.write_text(existing, encoding="utf-8")
                os.replace(str(temporary), str(memory_path))
            finally:
                if temporary.exists():
                    temporary.unlink()
            append_audit(store, "save-memory", saved)
    print("Saved %d memory item(s) -> %s" % (len(saved), store / "memory.md"))


def tokenize(text):
    normalized = unicodedata.normalize("NFKC", str(text)).casefold()
    words = re.findall(r"[a-z0-9]+", normalized)
    cjk = [char for char in normalized if "\u3400" <= char <= "\u9fff"]
    tokens = words + cjk
    tokens.extend(cjk[index] + cjk[index + 1] for index in range(len(cjk) - 1))
    return tokens


SEARCH_FIELDS = (
    ("title", 4.0),
    ("tags", 4.0),
    ("task_types", 3.5),
    ("applicability", 2.2),
    ("scope", 1.4),
    ("lesson", 1.2),
    ("avoid", 0.8),
    ("evidence", 0.35),
)


def field_text(record, field):
    value = record.get(field, "")
    return " ".join(str(item) for item in value) if isinstance(value, list) else str(value)


def score_records(records, query):
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    document_tokens = []
    for record in records:
        combined = []
        for field, _weight in SEARCH_FIELDS:
            combined.extend(tokenize(field_text(record, field)))
        document_tokens.append(combined)
    frequencies = {}
    for tokens in document_tokens:
        for token in set(tokens):
            frequencies[token] = frequencies.get(token, 0) + 1

    total = len(records)
    results = []
    query_phrase = normalize_space(query).casefold()
    for record in records:
        score = 0.0
        for field, weight in SEARCH_FIELDS:
            tokens = tokenize(field_text(record, field))
            counts = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            for token in query_tokens:
                if token in counts:
                    inverse_frequency = math.log(1.0 + (total + 1.0) / (frequencies.get(token, 0) + 1.0))
                    score += weight * inverse_frequency * (1.0 + math.log(counts[token]))
        searchable = " ".join(field_text(record, field) for field, _weight in SEARCH_FIELDS).casefold()
        if len(query_phrase) >= 5 and query_phrase in searchable:
            score += 6.0
        confidence = float(record.get("confidence", 0.5))
        outcomes = record.get("outcomes", {})
        successes = int(outcomes.get("successes", 0) or 0)
        failures = int(outcomes.get("failures", 0) or 0)
        observed = successes + failures
        reliability = 1.0 if not observed else 0.85 + 0.3 * ((successes + 1.0) / (observed + 2.0))
        score *= (0.7 + 0.3 * confidence) * reliability
        if score > 0:
            results.append((score, record))
    return sorted(results, key=lambda item: (-item[0], item[1].get("id", "")))


def search_experiences(records, query, limit=5, scope=None, task_type=None):
    filtered = []
    for record in records:
        if record.get("status", "active") != "active":
            continue
        if scope and record.get("scope") not in {scope, "global"}:
            continue
        if task_type and task_type.casefold() not in {str(item).casefold() for item in record.get("task_types", [])}:
            continue
        filtered.append(record)
    return score_records(filtered, query)[:limit]


def command_query(args):
    records = list(iter_records(args.store))
    results = search_experiences(records, args.query, args.limit, args.scope, args.task_type)
    if args.json:
        payload = [{"score": round(score, 6), "record": record} for score, record in results]
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if not results:
        print("No relevant RSI experience found.")
        return
    for index, (score, record) in enumerate(results, 1):
        print("%d. %s  score=%.3f  confidence=%.2f" % (index, record["id"], score, record["confidence"]))
        print("   %s: %s" % (record["title"], record["lesson"]))
        print("   Applies: %s" % "; ".join(record.get("applicability", [])))


def command_list(args):
    records = list(iter_records(args.store, include_archived=args.all))
    if args.kind:
        records = [record for record in records if record.get("kind") == args.kind]
    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if not records:
        print("No RSI experience records.")
        return
    for record in records:
        print("%s\t%s\t%s\t%s" % (record["id"], record.get("status"), record.get("kind"), record.get("title")))


def records_for_status(store, status):
    stored = list(iter_records(store, include_archived=True))
    trashed = list(iter_trashed_records(store))
    if status == "active":
        return [record for record in stored if record.get("status", "active") == "active"]
    if status == "archived":
        return [record for record in stored if record.get("status") == "archived"]
    if status == "trashed":
        return trashed
    if status == "stored":
        return stored
    return stored + trashed


def library_counts(store):
    stored = list(iter_records(store, include_archived=True))
    trashed = list(iter_trashed_records(store))
    return {
        "active": sum(record.get("status", "active") == "active" for record in stored),
        "archived": sum(record.get("status") == "archived" for record in stored),
        "trashed": len(trashed),
    }


def compact_cell(value, maximum=48):
    clean = normalize_space(str(value)).replace("|", "\\|")
    return clean if len(clean) <= maximum else clean[: maximum - 1] + "…"


def outcome_label(record):
    outcomes = record.get("outcomes", {})
    uses = int(outcomes.get("uses", 0) or 0)
    successes = int(outcomes.get("successes", 0) or 0)
    failures = int(outcomes.get("failures", 0) or 0)
    return "%d✓/%d✗/%d" % (successes, failures, uses)


def view_entries(records):
    ordered = sorted(
        records,
        key=lambda record: (record.get("updated_at", record.get("created_at", "")), record.get("id", "")),
        reverse=True,
    )
    return [{"ref": "R%d" % index, "record": record} for index, record in enumerate(ordered, 1)]


def render_markdown_catalog(entries, counts):
    lines = [
        "RSI Library · active=%d · archived=%d · trash=%d · showing=%d"
        % (counts["active"], counts["archived"], counts["trashed"], len(entries)),
        "",
        "| Ref | Record ID | Title | Kind | Scope | Confidence | Outcomes | Status |",
        "|---|---|---|---|---|---:|---:|---|",
    ]
    for entry in entries:
        record = entry["record"]
        lines.append(
            "| %s | `%s` | %s | %s | %s | %.2f | %s | %s |"
            % (
                entry["ref"],
                record.get("id", ""),
                compact_cell(record.get("title", "")),
                compact_cell(record.get("kind", ""), 20),
                compact_cell(record.get("scope", ""), 24),
                float(record.get("confidence", 0)),
                outcome_label(record),
                compact_cell(record.get("status", "active"), 12),
            )
        )
    if not entries:
        lines.append("| — | — | No matching experience | — | — | — | — | — |")
    lines.extend(
        [
            "",
            "Use `调用 Rn` to recall a displayed record. Archive, delete, and restore require an exact-target approval step.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_terminal_catalog(entries, counts):
    lines = [
        "RSI Library  active=%d archived=%d trash=%d showing=%d"
        % (counts["active"], counts["archived"], counts["trashed"], len(entries))
    ]
    for entry in entries:
        record = entry["record"]
        lines.append(
            "%s  %s  %-9s %-10s %.2f  %s  %s"
            % (
                entry["ref"],
                record.get("id", ""),
                record.get("status", "active"),
                record.get("kind", ""),
                float(record.get("confidence", 0)),
                outcome_label(record),
                record.get("title", ""),
            )
        )
    if not entries:
        lines.append("No matching RSI experience.")
    lines.append("Use: $rsi recall Rn · lifecycle mutations require approval")
    return "\n".join(lines) + "\n"


def render_html_catalog(entries, counts):
    rows = []
    for entry in entries:
        record = entry["record"]
        searchable = " ".join(
            str(record.get(field, ""))
            for field in ("id", "title", "kind", "scope", "lesson", "tags", "task_types", "status")
        ).casefold()
        identifier = record.get("id", "")
        status = record.get("status", "active")
        if status == "trashed":
            primary_command = "$rsi show %s from trash" % identifier
            primary_label = "Copy inspect request"
            lifecycle_command = "$rsi manage restore %s" % identifier
            lifecycle_label = "Copy restore request"
        else:
            primary_command = "$rsi recall %s%s" % (
                identifier,
                " including archived" if status == "archived" else "",
            )
            primary_label = "Copy recall"
            lifecycle_command = "$rsi manage delete %s" % identifier
            lifecycle_label = "Copy delete request"
        rows.append(
            """<tr data-search=\"{search}\" data-status=\"{status}\" data-kind=\"{kind}\">
<td><strong>{ref}</strong></td><td><code>{identifier}</code></td><td><strong>{title}</strong><br><small>{lesson}</small></td>
<td>{kind}</td><td>{scope}</td><td>{confidence:.2f}</td><td>{outcomes}</td><td><span class=\"pill {status}\">{status}</span></td>
<td><button data-copy=\"{primary}\">{primary_label}</button> <button data-copy=\"{lifecycle}\">{lifecycle_label}</button></td></tr>""".format(
                search=html.escape(searchable, quote=True),
                status=html.escape(str(record.get("status", "active")), quote=True),
                kind=html.escape(str(record.get("kind", "")), quote=True),
                ref=html.escape(entry["ref"]),
                identifier=html.escape(str(record.get("id", ""))),
                title=html.escape(str(record.get("title", ""))),
                lesson=html.escape(str(record.get("lesson", ""))),
                scope=html.escape(str(record.get("scope", ""))),
                confidence=float(record.get("confidence", 0)),
                outcomes=html.escape(outcome_label(record)),
                primary=html.escape(primary_command, quote=True),
                primary_label=html.escape(primary_label),
                lifecycle=html.escape(lifecycle_command, quote=True),
                lifecycle_label=html.escape(lifecycle_label),
            )
        )
    return """<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>RSI Experience Library</title><style>
:root{{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui;background:#0b1020;color:#dbeafe}}body{{margin:0;padding:32px}}
h1{{margin:0 0 8px}}.muted,small{{color:#94a3b8}}.cards{{display:flex;gap:12px;margin:24px 0}}.card{{background:#121a2c;border:1px solid #263451;border-radius:12px;padding:14px 20px}}
.card b{{display:block;font-size:26px}}.toolbar{{display:flex;gap:10px;margin:16px 0}}input,select,button{{color:#dbeafe;background:#16213a;border:1px solid #334466;border-radius:7px;padding:8px}}
input{{min-width:320px}}table{{border-collapse:collapse;width:100%;background:#121a2c}}th,td{{padding:10px;border-bottom:1px solid #263451;text-align:left;vertical-align:top}}code{{color:#a7f3d0}}.pill{{padding:3px 7px;border-radius:999px;background:#263451}}.active{{color:#a7f3d0}}.archived{{color:#fde68a}}.trashed{{color:#fda4af}}
</style></head><body><h1>RSI Experience Library</h1><p class=\"muted\">Read-only dashboard. Actions copy an RSI request; they do not mutate the store.</p>
<div class=\"cards\"><div class=\"card\"><b>{active}</b>active</div><div class=\"card\"><b>{archived}</b>archived</div><div class=\"card\"><b>{trashed}</b>trash</div><div class=\"card\"><b>{showing}</b>showing</div></div>
<div class=\"toolbar\"><input id=\"search\" placeholder=\"Search title, lesson, tags, scope...\"><select id=\"status\"><option value=\"\">all statuses</option><option>active</option><option>archived</option><option>trashed</option></select><select id=\"kind\"><option value=\"\">all kinds</option>{kind_options}</select></div>
<table><thead><tr><th>Ref</th><th>ID</th><th>Experience</th><th>Kind</th><th>Scope</th><th>Confidence</th><th>✓/✗/uses</th><th>Status</th><th>Actions</th></tr></thead><tbody>{rows}</tbody></table>
<script>const rows=[...document.querySelectorAll('tbody tr')];function filter(){{const q=document.querySelector('#search').value.toLowerCase(),s=document.querySelector('#status').value,k=document.querySelector('#kind').value;for(const r of rows)r.hidden=!(r.dataset.search.includes(q)&&(!s||r.dataset.status===s)&&(!k||r.dataset.kind===k));}}document.querySelectorAll('input,select').forEach(x=>x.addEventListener('input',filter));document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',async()=>{{try{{await navigator.clipboard.writeText(b.dataset.copy);b.textContent='Copied';}}catch(e){{window.prompt('Copy this RSI request:',b.dataset.copy);}}}}));</script>
</body></html>""".format(
        active=counts["active"],
        archived=counts["archived"],
        trashed=counts["trashed"],
        showing=len(entries),
        kind_options="".join(
            "<option>%s</option>" % html.escape(kind) for kind in sorted({entry["record"].get("kind", "") for entry in entries})
        ),
        rows="".join(rows),
    )


def write_new_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise RSIError("output already exists; refusing to overwrite: %s" % path)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def command_visualize(args):
    counts = library_counts(args.store)
    records = records_for_status(args.store, args.status)
    if args.kind:
        records = [record for record in records if record.get("kind") == args.kind]
    if args.scope:
        records = [record for record in records if record.get("scope") == args.scope]
    if args.query:
        records = [record for _score, record in score_records(records, args.query)]
        entries = [{"ref": "R%d" % index, "record": record} for index, record in enumerate(records, 1)]
    else:
        entries = view_entries(records)
    entries = entries[: args.limit]

    if args.format == "json":
        rendered = json.dumps(
            {"summary": counts, "showing": len(entries), "entries": entries},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
    elif args.format == "html":
        rendered = render_html_catalog(entries, counts)
    elif args.format == "terminal":
        rendered = render_terminal_catalog(entries, counts)
    else:
        rendered = render_markdown_catalog(entries, counts)

    if args.output:
        write_new_text(args.output, rendered)
        print("Wrote read-only RSI %s view -> %s" % (args.format, args.output))
    else:
        print(rendered, end="")


def find_record_path(store, identifier):
    if not ID_RE.match(identifier):
        raise RSIError("invalid experience ID")
    return store / "experiences" / (identifier + ".json")


def find_trash_path(store, identifier):
    if not ID_RE.match(identifier):
        raise RSIError("invalid experience ID")
    return store / "trash" / (identifier + ".json")


def load_record_path(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RSIError("experience record does not exist: %s" % path.stem)
    except json.JSONDecodeError as exc:
        raise RSIError("experience record is invalid JSON: %s" % exc)


def command_show(args):
    path = find_record_path(args.store, args.identifier)
    if not path.exists() and args.include_trash:
        path = find_trash_path(args.store, args.identifier)
    record = load_record_path(path)
    if path.parent.name == "trash":
        record["status"] = "trashed"
    print(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True))


def command_recall(args):
    records = []
    for identifier in args.identifiers:
        path = find_record_path(args.store, identifier)
        if not path.exists():
            if find_trash_path(args.store, identifier).exists():
                raise RSIError("experience is in trash; restore it before recall: %s" % identifier)
            raise RSIError("experience record does not exist: %s" % identifier)
        record = load_record_path(path)
        if record.get("status") == "archived" and not args.include_archived:
            raise RSIError("experience is archived; pass --include-archived to call it explicitly: %s" % identifier)
        records.append(record)
    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True))
        return
    for index, record in enumerate(records, 1):
        print("%d. %s  confidence=%.2f  scope=%s" % (index, record["id"], record["confidence"], record["scope"]))
        print("   %s: %s" % (record["title"], record["lesson"]))
        print("   Applies: %s" % "; ".join(record.get("applicability", [])))
        if record.get("avoid"):
            print("   Avoid: %s" % record["avoid"])


def command_feedback(args):
    ensure_approved(args)
    if args.outcome not in OUTCOMES:
        raise RSIError("unsupported outcome")
    store = args.store
    with store_lock(store):
        path = find_record_path(store, args.identifier)
        record = load_record_path(path)
        outcomes = record.setdefault("outcomes", {})
        outcomes["uses"] = int(outcomes.get("uses", 0) or 0) + 1
        if args.outcome == "success":
            outcomes["successes"] = int(outcomes.get("successes", 0) or 0) + 1
        elif args.outcome == "failure":
            outcomes["failures"] = int(outcomes.get("failures", 0) or 0) + 1
        outcomes["last_outcome_at"] = utc_now()
        record["updated_at"] = outcomes["last_outcome_at"]
        atomic_write_json(path, record)
        append_audit(store, "feedback:%s" % args.outcome, [args.identifier])
    print("Recorded %s feedback for %s" % (args.outcome, args.identifier))


def command_archive(args):
    ensure_approved(args)
    store = args.store
    with store_lock(store):
        path = find_record_path(store, args.identifier)
        record = load_record_path(path)
        if record.get("status") == "archived":
            print("Already archived: %s" % args.identifier)
            return
        record["status"] = "archived"
        record["updated_at"] = utc_now()
        atomic_write_json(path, record)
        append_audit(store, "archive", [args.identifier])
    print("Archived %s" % args.identifier)


def command_delete(args):
    ensure_approved(args)
    store = args.store
    with store_lock(store):
        source = find_record_path(store, args.identifier)
        record = load_record_path(source)
        destination = find_trash_path(store, args.identifier)
        if destination.exists():
            raise RSIError("trash already contains record: %s" % args.identifier)
        destination.parent.mkdir(parents=True, exist_ok=True)
        previous_status = record.get("status", "active")
        os.replace(str(source), str(destination))
        record["status"] = "trashed"
        record["updated_at"] = utc_now()
        record["trash"] = {
            "deleted_at": record["updated_at"],
            "previous_status": previous_status,
            "recoverable": True,
        }
        atomic_write_json(destination, record)
        append_audit(store, "delete-to-trash", [args.identifier])
    print("Moved %s -> %s (recoverable)" % (args.identifier, destination))


def command_restore(args):
    ensure_approved(args)
    store = args.store
    with store_lock(store):
        source = find_trash_path(store, args.identifier)
        record = load_record_path(source)
        destination = find_record_path(store, args.identifier)
        if destination.exists():
            raise RSIError("experience directory already contains record: %s" % args.identifier)
        trash_metadata = record.get("trash", {})
        previous_status = trash_metadata.get("previous_status", "active")
        if previous_status not in {"active", "archived"}:
            previous_status = "active"
        record["status"] = previous_status
        record["updated_at"] = utc_now()
        record.pop("trash", None)
        atomic_write_json(source, record)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(str(source), str(destination))
        append_audit(store, "restore", [args.identifier])
    print("Restored %s -> %s (status=%s)" % (args.identifier, destination, previous_status))


def validate_stored_record(record, path, location="experiences"):
    errors = []
    if record.get("schema_version") != 1:
        errors.append("unsupported schema_version")
    if not ID_RE.match(str(record.get("id", ""))):
        errors.append("invalid id")
    if path.stem != record.get("id"):
        errors.append("filename/id mismatch")
    candidate = {key: record[key] for key in REQUIRED_EXPERIENCE_FIELDS if key in record}
    for key in OPTIONAL_EXPERIENCE_FIELDS:
        if key in record:
            candidate[key] = record[key]
    try:
        validated = validate_experience(candidate)
        if record.get("fingerprint") != candidate_fingerprint(validated):
            errors.append("fingerprint mismatch")
    except RSIError as exc:
        errors.append(str(exc))
    allowed_statuses = {"trashed"} if location == "trash" else {"active", "archived"}
    if record.get("status") not in allowed_statuses:
        errors.append("invalid status for %s" % location)
    if location == "trash" and not record.get("trash", {}).get("recoverable"):
        errors.append("missing recoverable trash metadata")
    return errors


def command_doctor(args):
    store = args.store
    if not store.exists():
        print("RSI store does not exist: %s" % store)
        return
    failures = []
    seen_fingerprints = {}
    count = 0
    trash_count = 0
    for location in ("experiences", "trash"):
        directory = store / location
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            count += 1
            if location == "trash":
                trash_count += 1
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                failures.append("%s: %s" % (path, exc))
                continue
            for error in validate_stored_record(record, path, location):
                failures.append("%s: %s" % (path, error))
            fingerprint = record.get("fingerprint")
            if fingerprint in seen_fingerprints:
                failures.append("%s: duplicate of %s" % (path, seen_fingerprints[fingerprint]))
            seen_fingerprints[fingerprint] = path
    if failures:
        print("RSI store check failed (%d record(s), %d issue(s)):" % (count, len(failures)))
        for failure in failures:
            print("- %s" % failure)
        raise RSIError("store integrity check failed")
    print("RSI store OK: %d experience record(s), %d in trash" % (count, trash_count))


def command_stats(args):
    records = list(iter_records(args.store, include_archived=True))
    trashed = list(iter_trashed_records(args.store))
    payload = {
        "records": len(records) + len(trashed),
        "active": sum(record.get("status", "active") == "active" for record in records),
        "archived": sum(record.get("status") == "archived" for record in records),
        "trashed": len(trashed),
        "uses": sum(int(record.get("outcomes", {}).get("uses", 0) or 0) for record in records),
        "successes": sum(int(record.get("outcomes", {}).get("successes", 0) or 0) for record in records),
        "failures": sum(int(record.get("outcomes", {}).get("failures", 0) or 0) for record in records),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(" ".join("%s=%s" % item for item in payload.items()))


def build_parser():
    parser = argparse.ArgumentParser(description="Approval-gated RSI experience store")
    parser.add_argument("--store", type=Path, default=Path(os.environ.get("RSI_STORE", ".rsi")))
    parser.add_argument("--version", action="version", version="%(prog)s " + VERSION)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="initialize an empty store")
    init_parser.add_argument("--approved", action="store_true")
    init_parser.set_defaults(handler=command_init)

    preview_parser = subparsers.add_parser("preview-experience", help="validate and render candidates without writing")
    preview_parser.add_argument("--input", required=True, help="JSON file or - for stdin")
    preview_parser.set_defaults(handler=command_preview_experience)

    save_parser = subparsers.add_parser("save-experience", help="save user-approved experience")
    save_parser.add_argument("--approved", action="store_true")
    save_parser.add_argument("--input", required=True, help="JSON file or - for stdin")
    save_parser.set_defaults(handler=command_save_experience)

    memory_parser = subparsers.add_parser("save-memory", help="append user-approved fallback memory")
    memory_parser.add_argument("--approved", action="store_true")
    memory_parser.add_argument("--input", required=True, help="JSON file or - for stdin")
    memory_parser.set_defaults(handler=command_save_memory)

    query_parser = subparsers.add_parser("query", help="rank relevant active experience")
    query_parser.add_argument("query")
    query_parser.add_argument("--limit", type=int, default=5)
    query_parser.add_argument("--scope")
    query_parser.add_argument("--task-type")
    query_parser.add_argument("--json", action="store_true")
    query_parser.set_defaults(handler=command_query)

    visualize_parser = subparsers.add_parser("visualize", help="render a browsable experience catalog")
    visualize_parser.add_argument("--format", choices=("markdown", "terminal", "json", "html"), default="markdown")
    visualize_parser.add_argument(
        "--status", choices=("active", "archived", "trashed", "stored", "all"), default="stored"
    )
    visualize_parser.add_argument("--kind", choices=sorted(KINDS))
    visualize_parser.add_argument("--scope")
    visualize_parser.add_argument("--query")
    visualize_parser.add_argument("--limit", type=int, default=100)
    visualize_parser.add_argument("--output", type=Path, help="write a new view file; existing files are never overwritten")
    visualize_parser.set_defaults(handler=command_visualize)

    list_parser = subparsers.add_parser("list", help="list experience records")
    list_parser.add_argument("--kind", choices=sorted(KINDS))
    list_parser.add_argument("--all", action="store_true", help="include archived records")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(handler=command_list)

    show_parser = subparsers.add_parser("show", help="show one record")
    show_parser.add_argument("identifier")
    show_parser.add_argument("--include-trash", action="store_true")
    show_parser.set_defaults(handler=command_show)

    recall_parser = subparsers.add_parser("recall", help="call exact experience records as task context")
    recall_parser.add_argument("identifiers", nargs="+")
    recall_parser.add_argument("--include-archived", action="store_true")
    recall_parser.add_argument("--json", action="store_true")
    recall_parser.set_defaults(handler=command_recall)

    feedback_parser = subparsers.add_parser("feedback", help="record an approved outcome")
    feedback_parser.add_argument("--approved", action="store_true")
    feedback_parser.add_argument("identifier")
    feedback_parser.add_argument("outcome", choices=sorted(OUTCOMES))
    feedback_parser.set_defaults(handler=command_feedback)

    archive_parser = subparsers.add_parser("archive", help="archive an approved record")
    archive_parser.add_argument("--approved", action="store_true")
    archive_parser.add_argument("identifier")
    archive_parser.set_defaults(handler=command_archive)

    delete_parser = subparsers.add_parser("delete", help="move an approved record to recoverable trash")
    delete_parser.add_argument("--approved", action="store_true")
    delete_parser.add_argument("identifier")
    delete_parser.set_defaults(handler=command_delete)

    restore_parser = subparsers.add_parser("restore", help="restore an approved record from trash")
    restore_parser.add_argument("--approved", action="store_true")
    restore_parser.add_argument("identifier")
    restore_parser.set_defaults(handler=command_restore)

    doctor_parser = subparsers.add_parser("doctor", help="check store integrity")
    doctor_parser.set_defaults(handler=command_doctor)

    stats_parser = subparsers.add_parser("stats", help="summarize the store")
    stats_parser.add_argument("--json", action="store_true")
    stats_parser.set_defaults(handler=command_stats)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "limit") and args.limit < 1:
        parser.error("--limit must be at least 1")
    try:
        args.handler(args)
    except RSIError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
