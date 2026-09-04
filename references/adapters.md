# Agent architecture adapters

RSI is a protocol plus a portable store; it does not depend on one model vendor. An adapter needs four capabilities:

1. an explicit invocation mechanism;
2. access to relevant task artifacts or conversation context;
3. a channel that can display numbered proposals and receive user approval;
4. a persistence backend for approved memory, experience, and generated skills.

Python is optional. When unavailable, implement the JSON schema, proposal gate, atomic/transactional writes, and audit metadata natively.

## Single interactive agent

Map `$rsi capture`, `$rsi manage`, `$rsi recall`, and `$rsi synthesize` to this `SKILL.md`. Set implicit invocation off. Use a workspace-local `.rsi/` store unless the user chooses a personal store.

## Planner/executor/reviewer systems

The coordinator owns the approval gate and is the only writer. Workers may return candidate lessons or retrieval queries, but must not persist them. A safe flow is:

```text
workers ──candidate facts──> coordinator ──numbered proposal──> user
                                  │                              │
                                  └────write approved subset <───┘
```

This prevents duplicate writes and avoids treating an internal agent vote as human approval.

## Shared multi-agent store

- Give each workspace a stable `scope` and each task a non-sensitive `source_task`.
- Use the helper as the single local persistence interface, or provide a transactional service with the same operations.
- Retrieve a bounded top-k set and send only those records to workers that need them.
- Do not copy global personal preferences into team or tenant stores.
- Resolve contradictory records at the coordinator and propose a merge, replacement, or narrower scope to the user.

## Event-driven / API integration

Expose three events or endpoints:

- `rsi.propose`: read-only analysis returning proposal objects;
- `rsi.browse` and `rsi.recall`: read-only catalog and exact-record retrieval;
- `rsi.approve`: a user-authenticated decision over proposal IDs;
- `rsi.commit`: validates the approval token and atomically persists the approved subset.

For stronger guarantees than the bundled local CLI, bind the approval to a hash of the displayed proposal. Reject commits when the content hash changes after approval.

## Native memory and skill registries

Native backends may replace `.rsi/memory.md` and `.rsi/generated-skills/`. Keep RSI experience records distinct so they retain applicability, evidence, confidence, and outcome data. Record the native destination identifier in the completion report; do not duplicate the same preference across backends unless the user requests it.
