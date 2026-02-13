#!/usr/bin/env python3
"""
confessional_hook.py — Claude Code hook handler for claude-confessional.

Handles SessionStart events to automatically create breakpoints
when recording is enabled for the current project.

No recording logic — conversation data is read from native JSONL on-demand.

Receives JSON on stdin from Claude Code's hooks system.
Always exits 0 (never blocks Claude).

Install:  python3 confessional_hook.py --install
Remove:   python3 confessional_hook.py --uninstall
"""

import sys
import json
import os
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path.home() / ".reflection" / "hook.log"

# Import confessional_store from the same directory
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import confessional_store as store


def get_logger():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("confessional")
    if not logger.handlers:
        handler = logging.FileHandler(str(LOG_PATH))
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
    return logger


def get_project_name(cwd):
    """Derive project name from cwd by finding git root, or falling back to basename."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, cwd=cwd, timeout=5
        )
        if result.returncode == 0:
            return os.path.basename(result.stdout.strip())
    except Exception:
        pass
    return os.path.basename(cwd)


def handle_session_start(input_data):
    """Handle SessionStart hook: auto-breakpoint if last one is stale."""
    cwd = input_data.get("cwd", os.getcwd())
    project = get_project_name(cwd)

    if not store.is_recording(project):
        return

    try:
        bp = store.get_current_breakpoint(project)
        if bp:
            bp_time = datetime.fromisoformat(bp["timestamp"])
            age_seconds = (datetime.now(timezone.utc) - bp_time).total_seconds()
            if age_seconds > 4 * 3600:
                store.add_breakpoint(project, "Auto-breakpoint: new session")
    except Exception as e:
        get_logger().error("handle_session_start failed: %s", e, exc_info=True)


# --- Install / Uninstall ---

HOOK_COMMAND = "python3 $HOME/.claude/scripts/confessional_hook.py"
HOOK_EVENTS = ("SessionStart",)


def _settings_path():
    return Path.home() / ".claude" / "settings.json"


def _make_hook_entry():
    return {"hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 10}]}


def install_hooks():
    """Add confessional hooks to ~/.claude/settings.json."""
    settings_path = _settings_path()
    settings = {}
    if settings_path.exists():
        with open(settings_path) as f:
            settings = json.load(f)

    hooks = settings.setdefault("hooks", {})

    added = []
    for event in HOOK_EVENTS:
        event_hooks = hooks.setdefault(event, [])
        already = any(
            any("confessional_hook" in h.get("command", "") for h in group.get("hooks", []))
            for group in event_hooks
        )
        if not already:
            event_hooks.append(_make_hook_entry())
            added.append(event)

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")

    if added:
        print(f"Installed hooks for: {', '.join(added)}")
    else:
        print("Hooks already installed.")
    print("Restart Claude Code for hooks to take effect.")


def uninstall_hooks():
    """Remove confessional hooks from ~/.claude/settings.json."""
    settings_path = _settings_path()
    if not settings_path.exists():
        print("No settings.json found.")
        return

    with open(settings_path) as f:
        settings = json.load(f)

    hooks = settings.get("hooks", {})
    removed = []
    for event in HOOK_EVENTS:
        if event in hooks:
            before = len(hooks[event])
            hooks[event] = [
                group for group in hooks[event]
                if not any("confessional_hook" in h.get("command", "") for h in group.get("hooks", []))
            ]
            if len(hooks[event]) < before:
                removed.append(event)
            if not hooks[event]:
                del hooks[event]

    if not hooks:
        settings.pop("hooks", None)

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")

    if removed:
        print(f"Removed hooks for: {', '.join(removed)}")
    else:
        print("No confessional hooks found to remove.")


# --- Main ---

def main():
    if "--install" in sys.argv:
        install_hooks()
        return
    if "--uninstall" in sys.argv:
        uninstall_hooks()
        return

    # Normal hook mode: read JSON from stdin
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    event = input_data.get("hook_event_name", "")

    if event == "SessionStart":
        handle_session_start(input_data)

    sys.exit(0)


if __name__ == "__main__":
    main()
