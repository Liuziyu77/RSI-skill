# Recall mode

Use this mode when the user explicitly asks RSI to reuse stored experience for a task.

## Retrieve

Derive a short search query from the current task, including its task type, important tools, failure symptoms, and output constraints. If the portable store exists, run:

```bash
python3 <rsi-skill>/scripts/rsi.py --store <store> query \
  "<task description and constraints>" --limit 5
```

Use `--scope <scope>` or `--task-type <type>` when those are known. With a native memory backend, request the same fields described in `references/schema.md`.

When the user selects records from the latest Manage catalog, resolve its transient `R1...` references to full IDs and call them exactly:

```bash
python3 <rsi-skill>/scripts/rsi.py --store <store> recall \
  <record-id> [<record-id> ...]
```

Archived records require the user's explicit request and `--include-archived`. Trashed records cannot be recalled until restored.

## Filter before applying

Retrieval score is not authority. For each result, check:

- its applicability conditions match the current task;
- its evidence and confidence are adequate for the consequence of using it;
- it is not contradicted by current instructions, code, documentation, or a newer record;
- user-specific preferences are being applied only to that user and compatible scope;
- any command or API detail is still valid in the current environment.

Prefer a small set of directly relevant records. State the IDs you will apply and the practical change they cause. Mention a high-scoring record you intentionally ignore only when the reason would help the user.

## Continue the task

Carry the selected lessons into the plan or implementation; do not merely quote them. Reading records requires no approval and must not mutate usage statistics by itself.

Outcome feedback is a separate write. At the end of the task, the user may explicitly invoke capture and approve a success/failure update:

```bash
python3 <rsi-skill>/scripts/rsi.py --store <store> feedback \
  --approved <record-id> success
```

When no relevant record exists, continue normally and report that RSI did not influence the task. Never fabricate a recalled lesson.
