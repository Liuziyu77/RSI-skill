# Synthesize mode

Use this mode when the user explicitly asks RSI to turn stored experience into a new skill.

## Select source experience

Retrieve records for the requested domain, then favor lessons that are:

- supported by multiple tasks or explicit user direction;
- stable enough to guide future decisions;
- internally consistent and scoped to a coherent job;
- procedural or domain-specific rather than merely stylistic;
- free of secrets, private examples, and machine-specific paths.

Three successful records are a useful confidence signal, not a hard threshold. If evidence is thin, state that in the proposal instead of inventing coverage. Exclude personal preferences from a portable skill unless the user explicitly asks for a personal skill.

## Propose before creating files

Do not create the skill directory yet. Present one or more `S1...` proposals containing:

- proposed skill name and one-sentence activation description;
- source RSI record IDs;
- intended users and supported requests;
- behavioral rules it will add beyond an already capable agent;
- proposed file list (`SKILL.md`, and only justified references/scripts/assets);
- storage/install destination and invocation policy;
- known limitations, conflicts, or weak evidence.

Ask the user to approve, edit, or reject individual proposals. If an edit materially changes the scope, show the revised proposal again.

## Build only the approved skill

After approval:

1. Use a lowercase hyphenated folder name under 64 characters.
2. Write a concise `SKILL.md` with `name` and a discriminating `description` in YAML frontmatter.
3. Keep common rules in `SKILL.md`; move substantial conditional procedures to linked references.
4. Add deterministic scripts only for repeated or fragile mechanics, and test them.
5. Add `agents/openai.yaml` only when the target supports it. Match the invocation policy approved by the user.
6. Validate with the target platform's skill validator when available; otherwise check frontmatter, links, executable scripts, placeholders, and directory naming.
7. Write `rsi-provenance.json` with source record IDs, synthesis time, and no private task content.

Default to `.rsi/generated-skills/<skill-name>/` if the user did not name an installation directory. Do not overwrite an existing skill; propose an update separately.

Report the exact path and validation result. The synthesized skill becomes independent: it must not require RSI at runtime unless that is part of the approved design.
