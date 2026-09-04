# Manage mode

Use this mode when the user explicitly asks RSI to list, visualize, inspect, call, archive, delete, or restore stored experience.

## Visualize the library

Default to a compact Markdown catalog in the conversation. Show a summary and a stable-in-this-message reference for each result:

```text
RSI Library · active=12 · archived=2 · trash=1

| Ref | Title | Kind | Scope | Confidence | Outcomes | Status |
|---|---|---|---|---:|---:|---|
| R1 | Preserve CSV identifiers | procedure | workspace | 0.93 | 3/3 | active |
| R2 | Honor Retry-After | procedure | global | 0.91 | 2/3 | active |
```

Use the helper for deterministic rendering:

```bash
python3 <rsi-skill>/scripts/rsi.py --store <store> visualize \
  --format markdown --status stored
```

Support filters when requested: `--query`, `--kind`, `--scope`, and `--status active|archived|trashed|stored|all`. Use `--format html --output <path>` only when the user asks for a standalone interactive dashboard. Warn that the HTML contains experience text and should not be placed in a public directory.

`R1...` is a transient display reference, valid only for the most recently displayed catalog in the conversation. Translate it to the full `xp-...` ID before any command and repeat the full ID and title in every mutation proposal.

## Inspect or call experience

Inspection and recall are read-only and need no approval. When the user says `调用 R2` or names full IDs, retrieve those exact active records:

```bash
python3 <rsi-skill>/scripts/rsi.py --store <store> recall <record-id> [<record-id> ...]
```

State which records were called and how they will affect the current task. Do not increment outcomes automatically. Archived records require an explicit request and `--include-archived`; trashed records cannot be recalled until restored.

## Archive

Archiving hides a record from normal recall without treating it as deleted. Resolve the target, then show:

```text
A1 · archive
Record: xp-... · Preserve CSV identifiers
Effect: status becomes archived; record remains in experiences/ and can be inspected.
```

Wait for approval, then run `archive --approved <id>`.

## Delete to recoverable trash

Never interpret a filter, search phrase, or transient reference without resolving it to exact records. Show one numbered item per target:

```text
D1 · delete-to-trash
Record: xp-... · Preserve CSV identifiers
Effect: removed from visualization's stored view and all recall; moved to .rsi/trash/.
Recovery: can be restored with RSI manage.
```

Wait for approval. Move only approved IDs:

```bash
python3 <rsi-skill>/scripts/rsi.py --store <store> delete \
  --approved <record-id>
```

This is a recoverable delete, not permanent erasure. Do not offer bulk wildcard deletion or permanent purge through the bundled helper.

## Restore

Display trashed records first, resolve the exact ID, and show a `U1...` restore proposal with its former status. (`R1...` remains reserved for catalog rows.) After approval:

```bash
python3 <rsi-skill>/scripts/rsi.py --store <store> restore \
  --approved <record-id>
```

Report the restored status and path. If an experience with the same ID already exists, stop rather than overwrite it.
