# Store and record schema

## Portable layout

```text
.rsi/
├── experiences/
│   └── xp-<timestamp>-<hash>.json
├── trash/
│   └── xp-<timestamp>-<hash>.json
├── generated-skills/
├── memory.md
└── audit.jsonl
```

The helper creates files lazily on the first approved write. `experiences/` contains one human-readable JSON record per item. `memory.md` is a minimal fallback for hosts without native memory. `audit.jsonl` records mutation metadata, never raw conversations.

The `.rsi/` store contains user-approved derived data and may still be sensitive. Keep a personal store outside version control, or intentionally commit a sanitized team store. A useful `.gitignore` default is `.rsi/`.

## Experience record

The normative machine-readable definition is `schemas/experience.schema.json`. Required semantic fields are:

| Field | Meaning |
|---|---|
| `kind` | `preference`, `procedure`, `pitfall`, `constraint`, `decision`, or `tooling` |
| `title` | Short retrieval label |
| `lesson` | The reusable decision or behavior |
| `scope` | `global`, `workspace`, or a narrower caller-defined scope |
| `task_types` | Stable task categories, not one-off ticket IDs |
| `applicability` | Conditions that must be true before applying the lesson |
| `evidence` | Concise observable support; no chain-of-thought or full transcript |
| `confidence` | Number from 0 to 1 |
| `tags` | Searchable technical/domain terms |

Optional `avoid` states a known anti-pattern and `source_task` gives a non-sensitive provenance label. The helper adds identity, timestamps, approval provenance, lifecycle state, and outcome counters.

## Memory input

`save-memory` accepts one object or a list with:

```json
{
  "statement": "Prefer concise completion summaries with test evidence.",
  "scope": "global",
  "evidence": "Explicitly requested after task T-17."
}
```

Memory statements must be durable user preferences, not inferred personality traits.

## Lifecycle

- New records start `active` with zero outcome observations.
- Recall is read-only.
- `feedback --approved ID success|failure|neutral` records an approved observed outcome.
- `archive --approved ID` makes a record unavailable to normal retrieval without deleting history.
- `delete --approved ID` moves a record to `.rsi/trash/`, records its previous status, and excludes it from recall.
- `restore --approved ID` returns a trashed record to `experiences/` with its previous status.
- Prefer a new superseding record or an explicit merge over silently rewriting evidence.

The bundled helper intentionally has no permanent purge or wildcard delete. Permanent erasure is a host-level destructive operation requiring exact targets and an explicit recovery-impact warning.

## Concurrency and integrity

The helper uses an exclusive lock plus same-directory atomic replacement for record changes. This prevents two local agents from partially writing one file. All agents sharing a store must use the helper or implement equivalent locking. Network filesystems may have weaker locking semantics; for distributed deployments, place the same schema behind a transactional database or single writer service.

An audit entry proves that a helper command asserted approval; it cannot cryptographically prove that a human approved. The host agent is responsible for obtaining and retaining explicit approval in the conversation.
