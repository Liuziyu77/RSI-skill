---
name: rsi
description: Explicitly capture approved lessons and user preferences, visualize or manage stored experience, recall it for a new task, or synthesize it into a reusable skill. Use only when the user invokes RSI; do not use for automatic background memory collection.
metadata:
  short-description: Review, reuse, and promote approved experience
---

# RSI

Turn completed work into reviewable, reusable experience without silently building a user profile. This skill has four modes: **capture**, **manage**, **recall**, and **synthesize**.

## Non-negotiable rules

- Run only after an explicit user invocation of RSI. Never initiate background capture or recall.
- Treat invocation as permission to analyze, not permission to persist. Show a numbered proposal first and wait for approval before every new memory item, experience record, or generated skill.
- Accept partial approval, edits, or rejection by proposal ID. Approval given before the proposal does not approve unseen content.
- Do not persist secrets, credentials, private keys, authentication material, raw private data, or a full conversation transcript. Generalize the minimum useful lesson.
- Separate durable user preferences from task techniques. A preference belongs in memory only when the user stated it or repeatedly confirmed it; a one-off choice stays scoped to the task.
- Preserve evidence and uncertainty. Do not convert a single success into a universal rule.
- Recall is advisory. Current user instructions, repository rules, verified facts, and safety constraints take precedence over stored experience.
- Treat deletion as a separate destructive proposal. Resolve and display exact record IDs and titles, wait for approval, then move approved records to the recoverable RSI trash; do not permanently purge them.
- On every write, report the exact saved IDs and destinations. Never claim a save succeeded without verifying it.

## Select a mode

Infer the mode from the explicit invocation. If it is genuinely ambiguous, show the four choices without writing anything.

- **Capture** — after a task, propose useful preferences, procedures, pitfalls, constraints, or decisions. Read [references/capture.md](references/capture.md).
- **Manage** — visualize the experience library, inspect or explicitly recall records, archive them, move them to recoverable trash, or restore them. Read [references/manage.md](references/manage.md).
- **Recall** — retrieve approved records relevant to a new task and explain which ones will influence the plan. Read [references/recall.md](references/recall.md).
- **Synthesize** — consolidate selected, approved experience into a proposed standalone skill. Read [references/synthesis.md](references/synthesis.md).

Read [references/schema.md](references/schema.md) when validating records, choosing scope, changing lifecycle state, or writing the RSI store. Read [references/adapters.md](references/adapters.md) only when installing RSI in a new agent architecture or coordinating multiple agents.

## Storage and tools

Use the configured store when the host provides one. Otherwise use `.rsi/` at the workspace root. The portable layout is described in [references/schema.md](references/schema.md).

When Python and a filesystem are available, prefer `scripts/rsi.py` for validation, atomic persistence, lexical retrieval, feedback, and audit entries. The script uses only the Python standard library. If it cannot run, follow the same schema and two-phase approval protocol through the host's native memory and skill APIs.

Do not create a store merely to perform recall. An absent store means that no local RSI experience is available.

## Proposal contract

Before a write, present a compact numbered list. Every item must include:

1. proposal ID;
2. action and destination;
3. proposed content or skill behavior;
4. scope and applicability;
5. evidence, confidence, and any important risk or conflict.

Use `M1/E1/S1` for new memory, experience, or skills; `A1/D1/U1` for archive, delete-to-trash, or restore proposals. Reserve `R1...` for transient rows in a visualized catalog. End with a direct approval request such as: `Approve all, approve E1/M1, edit an item, or reject.` Do not perform the mutation in the same turn as this first proposal unless the user responds to the displayed proposal with explicit approval.

After approval, save only the approved version. If the user's edit materially changes meaning, show the revised item again before saving.

## Completion report

For capture, report saved and skipped IDs plus destinations. For manage, report records displayed or exact lifecycle changes and recovery location. For recall, cite record IDs used and briefly state how each changed the work. For synthesis, report the generated skill path, source experience IDs, validation performed, and invocation policy.
