# Capture mode

Use this mode only after the user explicitly asks RSI to review a completed or substantially completed task.

## What to extract

Inspect the conversation, observable task result, corrections, tests, and user feedback. Prefer lessons that would change a future decision:

- `preference`: an explicitly stated, durable user choice;
- `procedure`: a repeatable sequence that improved the result;
- `pitfall`: a failed or risky approach and its diagnostic signal;
- `constraint`: a non-obvious environmental or project invariant;
- `decision`: a tradeoff and the conditions under which it was chosen;
- `tooling`: a reliable tool pattern or command with prerequisites.

Do not capture generic advice, facts already obvious from repository documentation, transient task state, praise, raw chain-of-thought, or conclusions unsupported by the observed result.

## Choose a destination

- Put stable, user-specific interaction or output preferences in `memory`.
- Put transferable task knowledge with applicability conditions in `experience`.
- Keep project-local facts at workspace scope. Use global scope only when the evidence supports portability.
- If the host has an explicit native memory API/path, use it for approved memory items. Otherwise append them to `.rsi/memory.md` through `scripts/rsi.py`.

## Produce the proposal

Use IDs `M1...` for memory and `E1...` for experience. A useful list looks like:

```text
M1 · memory · workspace
Statement: Prefer compact benchmark tables with caveats next to the metric.
Evidence: User explicitly requested this presentation in the completed evaluation.
Confidence: high

E1 · experience · task_types=[csv-import] · scope=workspace
Lesson: Read identifier columns as strings before schema inference so leading zeros survive.
Applies when: Importing customer or catalog CSVs with identifier-like columns.
Avoid: Inferring all numeric-looking columns as integers.
Evidence: The corrected importer passed the leading-zero regression test.
Confidence: 0.93
```

Consolidate duplicates before presenting them. If a proposed item conflicts with an existing record, show the conflict and propose `keep`, `replace`, `merge`, or `scope-narrow`; each is still approval-gated.

## Save after approval

Validate approved experience objects against `schemas/experience.schema.json`, then use:

```bash
python3 <rsi-skill>/scripts/rsi.py --store <store> save-experience \
  --approved --input <approved.json>
```

For fallback Markdown memory:

```bash
python3 <rsi-skill>/scripts/rsi.py --store <store> save-memory \
  --approved --input <approved-memory.json>
```

The input may be one object or a JSON list. Never pass `--approved` until the user has approved the displayed items. Temporary candidate files are working material, not part of the RSI store, and should not contain unnecessary private data.

If the user rejects everything, make no store or memory changes and say so plainly.
