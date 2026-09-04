#!/usr/bin/env python3
"""Install RSI into Codex, Claude Code, or OpenClaw skill roots.

The installer never overwrites an existing path. Its default "auto" mode uses
links where the documented loader accepts them without extra configuration,
and a copy for OpenClaw workspace installs.
"""

from __future__ import print_function

import argparse
import json
import os
from pathlib import Path
import shutil
import sys


VERSION = "0.1.0"
AGENTS = ("codex", "claude-code", "openclaw")


class InstallError(Exception):
    """A safe, user-correctable installation error."""


def is_within(path, parent):
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def validate_source(source):
    source = source.resolve()
    skill_file = source / "SKILL.md"
    if not skill_file.is_file():
        raise InstallError("source does not contain SKILL.md: %s" % source)
    text = skill_file.read_text(encoding="utf-8")
    if "\nname: rsi\n" not in "\n" + text:
        raise InstallError("source SKILL.md does not declare name: rsi")
    return source


def destination_for(agent, scope, home, project_dir=None, environment=None):
    environment = environment if environment is not None else os.environ
    if scope == "project" and project_dir is None:
        raise InstallError("--project-dir is required for project scope")
    if scope == "project":
        project = project_dir.resolve()
        if agent == "codex":
            return project / ".agents" / "skills" / "rsi"
        if agent == "claude-code":
            return project / ".claude" / "skills" / "rsi"
        return project / "skills" / "rsi"

    if agent == "codex":
        return home / ".agents" / "skills" / "rsi"
    if agent == "claude-code":
        return home / ".claude" / "skills" / "rsi"
    state_value = environment.get("OPENCLAW_STATE_DIR")
    state_dir = Path(state_value).expanduser() if state_value else home / ".openclaw"
    return state_dir / "skills" / "rsi"


def mode_for(agent, scope, requested):
    if requested != "auto":
        if agent == "openclaw" and scope == "project" and requested == "link":
            raise InstallError(
                "OpenClaw workspace links to external repositories require skills.load.allowSymlinkTargets; "
                "use --mode copy or the native `openclaw skills install` command"
            )
        return requested
    return "copy" if agent == "openclaw" and scope == "project" else "link"


def ignored_copy_names(_directory, names):
    excluded = {".git", ".rsi", "__pycache__", ".pytest_cache", ".mypy_cache"}
    return [name for name in names if name in excluded or name.endswith(".pyc")]


def preflight(source, plans):
    destinations = set()
    for plan in plans:
        destination = plan["destination"]
        if destination.is_symlink():
            try:
                if destination.resolve() == source:
                    plan["state"] = "already-installed"
                    continue
            except OSError:
                pass
            raise InstallError("destination is an existing symlink; refusing to replace it: %s" % destination)
        normalized = str(destination.resolve())
        if normalized in destinations:
            raise InstallError("multiple targets resolve to the same path: %s" % destination)
        destinations.add(normalized)
        if is_within(destination, source):
            raise InstallError("destination cannot be inside the RSI source repository: %s" % destination)
        if destination.exists():
            raise InstallError("destination already exists; refusing to overwrite it: %s" % destination)
        plan["state"] = "pending"


def install_plan(source, plan):
    destination = plan["destination"]
    if plan["state"] == "already-installed":
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if plan["mode"] == "link":
        destination.symlink_to(source, target_is_directory=True)
    else:
        shutil.copytree(str(source), str(destination), ignore=ignored_copy_names)
    if not (destination / "SKILL.md").is_file():
        raise InstallError("installation verification failed: %s" % destination)
    plan["state"] = "installed"


def render_plan(plans, dry_run=False, as_json=False):
    payload = [
        {
            "agent": plan["agent"],
            "scope": plan["scope"],
            "mode": plan["mode"],
            "destination": str(plan["destination"]),
            "state": "dry-run" if dry_run and plan["state"] == "pending" else plan["state"],
            "invoke": "$rsi" if plan["agent"] == "codex" else "/rsi",
        }
        for plan in plans
    ]
    if as_json:
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    lines = []
    for item in payload:
        lines.append(
            "{agent}: {state} ({mode}, {scope}) -> {destination} · invoke {invoke}".format(**item)
        )
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(description="Install the RSI skill without overwriting existing skills")
    parser.add_argument("--agent", choices=AGENTS + ("all",), required=True)
    parser.add_argument("--scope", choices=("user", "project"), default="user")
    parser.add_argument("--mode", choices=("auto", "link", "copy"), default="auto")
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--version", action="version", version="%(prog)s " + VERSION)
    return parser


def main(argv=None, home=None, environment=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    environment = environment if environment is not None else os.environ
    home = home if home is not None else Path.home()
    try:
        source = validate_source(args.source)
        selected = AGENTS if args.agent == "all" else (args.agent,)
        plans = [
            {
                "agent": agent,
                "scope": args.scope,
                "mode": mode_for(agent, args.scope, args.mode),
                "destination": destination_for(agent, args.scope, home, args.project_dir, environment),
            }
            for agent in selected
        ]
        preflight(source, plans)
        if not args.dry_run:
            for plan in plans:
                install_plan(source, plan)
        print(render_plan(plans, dry_run=args.dry_run, as_json=args.json))
    except (InstallError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
