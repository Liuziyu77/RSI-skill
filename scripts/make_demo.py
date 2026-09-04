#!/usr/bin/env python3
"""Render RSI's multi-turn README walkthroughs as animated GIFs."""

from pathlib import Path
import argparse
from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1120, 630
BACKGROUND = "#0b1020"
PANEL = "#121a2c"
TEXT = "#dbeafe"
MUTED = "#94a3b8"
USER = "#7dd3fc"
AGENT = "#a7f3d0"
APPROVAL = "#fde68a"
ACCENT = "#818cf8"


SCENARIOS = {
    "capture-recall": {
        "filename": "rsi-demo.gif",
        "title": "RSI · capture and recall",
        "footer": "Analyze → propose → user approves → persist → recall",
        "pauses": {5, 7, 10},
        "turns": [
            ("USER", "CSV importer is fixed and tests pass. $rsi capture", USER),
            ("RSI", "E1 · experience · csv-import", AGENT),
            ("RSI", "Preserve identifier columns as text before type inference.", TEXT),
            ("RSI", "Evidence: leading-zero regression passes · confidence 0.93", MUTED),
            ("RSI", "Approve all, approve E1, edit, or reject.", APPROVAL),
            ("USER", "Approve E1.", USER),
            ("RSI", "Saved E1 as xp-...-7ac91d2e in .rsi/experiences/", AGENT),
            ("USER", "New catalog import: keep SKU formatting. $rsi recall", USER),
            ("RSI", "Applied xp-...-7ac91d2e: load SKU as string before inference.", AGENT),
            ("RSI", "Result: 000184 remains 000184 ✓", APPROVAL),
        ],
    },
    "manage": {
        "filename": "rsi-manage.gif",
        "title": "RSI · visualize and manage",
        "footer": "Browse is read-only · recall is exact · delete is recoverable",
        "pauses": {4, 6, 8, 10},
        "turns": [
            ("USER", "$rsi manage — show all saved experience", USER),
            ("RSI", "Library · active=2 · archived=1 · trash=0", AGENT),
            ("RSI", "R1  Preserve CSV identifiers        0.93  active", TEXT),
            ("RSI", "R2  Honor Retry-After with jitter   0.91  active", TEXT),
            ("USER", "Call R2 for the current HTTP 429 task.", USER),
            ("RSI", "Applied xp-...-ad42c833 · library remains unchanged.", AGENT),
            ("USER", "Delete R1.", USER),
            ("RSI", "D1 · move exact record xp-...-7ac91d2e to recoverable trash?", APPROVAL),
            ("USER", "Approve D1.", USER),
            ("RSI", "Moved to .rsi/trash/ · use RSI restore to undo. ✓", AGENT),
        ],
    },
    "synthesize": {
        "filename": "rsi-synthesize.gif",
        "title": "RSI · synthesize a new skill",
        "footer": "Select evidence → propose files → approve → validate independent skill",
        "pauses": {6, 7, 10},
        "turns": [
            ("USER", "$rsi synthesize my approved CSV import experience", USER),
            ("RSI", "S1 · robust-csv-import", AGENT),
            ("RSI", "Sources: xp-...-7ac9, xp-...-01f9, xp-...-8e0c", MUTED),
            ("RSI", "Behavior: classify IDs, encoding, dates; add boundary tests.", TEXT),
            ("RSI", "Files: SKILL.md · field-types.md · profile_csv.py", TEXT),
            ("RSI", "Limit: evidence covers CSV only. Approve S1, edit, or reject.", APPROVAL),
            ("USER", "Approve S1 with explicit invocation.", USER),
            ("RSI", "Created .rsi/generated-skills/robust-csv-import/", AGENT),
            ("RSI", "Validator passed · provenance contains source IDs only.", AGENT),
            ("RSI", "New independent skill ready: $robust-csv-import ✓", APPROVAL),
        ],
    },
    "install": {
        "filename": "rsi-install.gif",
        "title": "RSI · install across agents",
        "footer": "One installer · correct scope per agent · never overwrite",
        "pauses": {5, 7, 10},
        "turns": [
            ("USER", "Install this RSI skill for all my local agents.", USER),
            ("AGENT", "Dry-run installer and check every destination first.", AGENT),
            ("AGENT", "Codex      → ~/.agents/skills/rsi", TEXT),
            ("AGENT", "Claude Code → ~/.claude/skills/rsi", TEXT),
            ("AGENT", "OpenClaw    → ~/.openclaw/skills/rsi", TEXT),
            ("AGENT", "No conflicting rsi installation found.", MUTED),
            ("AGENT", "Installed three links and verified each SKILL.md. ✓", APPROVAL),
            ("AGENT", "Codex invocation:      $rsi", AGENT),
            ("AGENT", "Claude Code/OpenClaw: /rsi", AGENT),
            ("AGENT", "Future updates flow from this repository automatically.", APPROVAL),
        ],
    },
}


def load_font(size, bold=False):
    choices = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationMono-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
    ]
    for value in choices:
        path = Path(value)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def render_frame(scenario, visible_turns, cursor=True):
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    title_font = load_font(24, bold=True)
    label_font = load_font(19, bold=True)
    body_font = load_font(19)
    small_font = load_font(15)

    draw.rounded_rectangle(
        (30, 28, WIDTH - 30, HEIGHT - 28), radius=18, fill=PANEL, outline="#263451", width=2
    )
    draw.ellipse((55, 52, 69, 66), fill="#fb7185")
    draw.ellipse((78, 52, 92, 66), fill="#fbbf24")
    draw.ellipse((101, 52, 115, 66), fill="#34d399")
    draw.text((142, 45), scenario["title"], font=title_font, fill=TEXT)
    draw.line((50, 86, WIDTH - 50, 86), fill="#263451", width=2)

    y = 112
    for role, message, color in visible_turns:
        draw.text((62, y), role, font=label_font, fill=color)
        draw.text((156, y), message, font=body_font, fill=TEXT if role == "USER" else color)
        y += 45
    if cursor:
        draw.rectangle((62, y + 4, 74, y + 27), fill=ACCENT)

    draw.text((62, HEIGHT - 61), scenario["footer"], font=small_font, fill=MUTED)
    return image


def write_scenario(scenario, output):
    frames = []
    durations = []
    turns = scenario["turns"]
    for index in range(1, len(turns) + 1):
        frames.append(render_frame(scenario, turns[:index], cursor=True))
        durations.append(1050 if index not in scenario["pauses"] else 1600)
    frames.append(render_frame(scenario, turns, cursor=False))
    durations.append(2200)
    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        str(output),
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    print("Wrote %s (%d frames)" % (output, len(frames)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=("all",) + tuple(SCENARIOS), default="all")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "docs")
    parser.add_argument("--output", type=Path, help="legacy single output; renders capture-recall")
    args = parser.parse_args()
    if args.output:
        if args.scenario not in {"all", "capture-recall"}:
            parser.error("--output can only be used with capture-recall")
        write_scenario(SCENARIOS["capture-recall"], args.output)
        return
    selected = SCENARIOS if args.scenario == "all" else {args.scenario: SCENARIOS[args.scenario]}
    for scenario in selected.values():
        write_scenario(scenario, args.output_dir / scenario["filename"])


if __name__ == "__main__":
    main()
