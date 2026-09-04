#!/usr/bin/env python3
"""Reproducible synthetic retrieval benchmark for RSI.

This measures intended-record retrieval, not downstream agent task quality.
"""

import argparse
import datetime as dt
import importlib.util
import json
from pathlib import Path
import random


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rsi", ROOT / "scripts" / "rsi.py")
RSI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RSI)


def flat_lesson_rank(records, query):
    query_tokens = set(RSI.tokenize(query))
    ranked = []
    for record in records:
        note = " ".join(str(record.get(field, "")) for field in ("lesson", "avoid", "evidence"))
        note_tokens = set(RSI.tokenize(note))
        union = query_tokens | note_tokens
        score = len(query_tokens & note_tokens) / float(len(union) or 1)
        if score:
            ranked.append((score, record["id"]))
    return [identifier for _score, identifier in sorted(ranked, key=lambda item: (-item[0], item[1]))]


def rsi_rank(records, query):
    return [record["id"] for _score, record in RSI.search_experiences(records, query, limit=len(records))]


def reciprocal_rank(ranking, relevant):
    for index, identifier in enumerate(ranking, 1):
        if identifier in relevant:
            return 1.0 / index
    return 0.0


def evaluate(rankings, queries):
    rows = []
    for ranking, case in zip(rankings, queries):
        relevant = set(case["relevant"])
        rows.append(
            {
                "recall_at_1": float(any(identifier in relevant for identifier in ranking[:1])),
                "recall_at_3": float(any(identifier in relevant for identifier in ranking[:3])),
                "mrr": reciprocal_rank(ranking, relevant),
            }
        )
    return {
        metric: sum(row[metric] for row in rows) / len(rows)
        for metric in ("recall_at_1", "recall_at_3", "mrr")
    }, rows


def percentile(values, probability):
    values = sorted(values)
    position = int(round((len(values) - 1) * probability))
    return values[position]


def paired_bootstrap(left_rows, right_rows, metric, iterations=10000, seed=20260904):
    generator = random.Random(seed)
    count = len(left_rows)
    differences = []
    for _ in range(iterations):
        indices = [generator.randrange(count) for _item in range(count)]
        difference = sum(left_rows[index][metric] - right_rows[index][metric] for index in indices) / count
        differences.append(difference)
    return [percentile(differences, 0.025), percentile(differences, 0.975)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data", type=Path, default=ROOT / "experiments" / "fixtures" / "retrieval_cases.json"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    fixture = json.loads(args.data.read_text(encoding="utf-8"))
    records = fixture["records"]
    queries = fixture["queries"]
    rankings = {
        "no_recall": [[] for _case in queries],
        "recency_top3": [[record["id"] for record in reversed(records)][0:3] for _case in queries],
        "lesson_only_overlap": [flat_lesson_rank(records, case["query"]) for case in queries],
        "rsi_structured": [rsi_rank(records, case["query"]) for case in queries],
    }

    metrics = {}
    detail = {}
    for name, method_rankings in rankings.items():
        metrics[name], detail[name] = evaluate(method_rankings, queries)

    confidence_interval = paired_bootstrap(
        detail["rsi_structured"], detail["recency_top3"], "recall_at_3"
    )
    result = {
        "benchmark_type": "synthetic intended-record retrieval; not end-to-end task quality",
        "dataset": str(args.data.relative_to(ROOT)),
        "records": len(records),
        "queries": len(queries),
        "metrics": metrics,
        "rsi_minus_recency_recall_at_3_95pct_paired_bootstrap": confidence_interval,
        "bootstrap_iterations": 10000,
        "bootstrap_seed": 20260904,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
