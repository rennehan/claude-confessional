#!/usr/bin/env python3
"""
confessional_hook.py — Claude Code hook handler for claude-confessional.

Handles Stop and SessionStart events to automatically record interactions
when recording is enabled for the current project.

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
from pathlib import Path
from collections import OrderedDict

LOG_PATH = Path.home() / ".reflection" / "hook.log"


def get_logger():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("confessional")
    if not logger.handlers:
        handler = logging.FileHandler(str(LOG_PATH))
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
    return logger

# Import reflection_db from the same directory
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import reflection_db as db


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


def is_recording_enabled(project):
    """Check if recording is enabled for this project."""
    try:
        conn = db.get_connection()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='recording_state'"
        ).fetchone()
        if not row:
            conn.close()
            return False
        row = conn.execute(
            "SELECT enabled FROM recording_state WHERE project = ?", (project,)
        ).fetchone()
        conn.close()
        return bool(row and row[0])
    except Exception:
        return False


def _extract_user_prompt_text(entry):
    """Extract the user's prompt text from a transcript user entry."""
    content = entry.get("message", {}).get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_result":
                    continue
                elif block.get("type") == "image":
                    parts.append("[image]")
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts) if parts else ""
    return ""


def _summarize_tool_input(tool_name, tool_input):
    """Create a brief summary of a tool call."""
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return cmd[:200]
    elif tool_name in ("Read", "Write", "Edit"):
        return tool_input.get("file_path", "")
    elif tool_name == "Grep":
        return f"pattern={tool_input.get('pattern', '')}"
    elif tool_name == "Glob":
        return f"pattern={tool_input.get('pattern', '')}"
    elif tool_name == "WebSearch":
        return tool_input.get("query", "")
    elif tool_name == "WebFetch":
        return tool_input.get("url", "")
    elif tool_name == "Task":
        return tool_input.get("prompt", "")[:200]
    return str(tool_input)[:200]


def _extract_files(tool_name, tool_input):
    """Extract file paths touched by a tool call."""
    if tool_name in ("Read", "Write", "Edit"):
        return tool_input.get("file_path", "")
    elif tool_name == "Glob":
        return tool_input.get("path", "")
    elif tool_name == "Grep":
        return tool_input.get("path", "")
    return ""


def parse_last_turn(transcript_path):
    """Parse transcript JSONL to extract the last complete user-assistant turn.

    The transcript format:
    - type="user" with string content = real user prompt
    - type="user" with list content containing tool_result = tool result (not a prompt)
    - type="assistant" lines each have exactly one content block
    - Multiple assistant lines with the same message.id form one API response
    - A turn = user prompt -> one or more API calls (with tool use/result cycles) -> final text

    Returns dict with {prompt, response, tools} matching record_interaction format,
    or None if no complete turn found.
    """
    lines = []
    with open(transcript_path, "r") as f:
        for line_str in f:
            line_str = line_str.strip()
            if line_str:
                try:
                    lines.append(json.loads(line_str))
                except json.JSONDecodeError:
                    continue

    # Find the last real user prompt (string content or structured content
    # that isn't purely tool_result blocks)
    last_user_idx = None
    for i in range(len(lines) - 1, -1, -1):
        entry = lines[i]
        if entry.get("type") == "user":
            content = entry.get("message", {}).get("content", "")
            if isinstance(content, str) and content.strip():
                last_user_idx = i
                break
            if isinstance(content, list):
                # If all blocks are tool_result, this is a tool cycle, not a prompt
                has_non_tool_result = any(
                    (isinstance(b, dict) and b.get("type") != "tool_result")
                    or isinstance(b, str)
                    for b in content
                )
                if has_non_tool_result:
                    last_user_idx = i
                    break

    if last_user_idx is None:
        return None

    prompt_text = _extract_user_prompt_text(lines[last_user_idx])

    # Collect all assistant content blocks after the user prompt.
    # Each transcript line has exactly one content block.
    # Group by message.id to identify distinct API calls, but collect all blocks.
    response_texts = []
    tools = []

    for i in range(last_user_idx + 1, len(lines)):
        entry = lines[i]
        if entry.get("type") != "assistant":
            continue

        content = entry.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue

            if block.get("type") == "text":
                text = block.get("text", "").strip()
                if text:
                    response_texts.append(text)
            elif block.get("type") == "tool_use":
                tool_input = block.get("input", {})
                tool_name = block.get("name", "")
                tools.append({
                    "tool_name": tool_name,
                    "input_summary": _summarize_tool_input(tool_name, tool_input),
                    "files_touched": _extract_files(tool_name, tool_input),
                    "is_subagent": tool_name == "Task",
                    "subagent_task": tool_input.get("prompt", "")[:200] if tool_name == "Task" else "",
                    "subagent_result_summary": "",
                    "duration_ms": 0,
                })

    if not response_texts and not tools:
        return None

    # Synthesize a response summary for tool-only turns
    response = "\n\n".join(response_texts)
    if not response and tools:
        tool_names = ", ".join(t["tool_name"] for t in tools)
        response = f"[tool-only turn: {tool_names}]"

    return {
        "prompt": prompt_text,
        "response": response,
        "tools": tools,
    }


def handle_stop(input_data):
    """Handle Stop hook: record the last turn to the DB."""
    cwd = input_data.get("cwd", os.getcwd())
    project = get_project_name(cwd)

    if not is_recording_enabled(project):
        return

    try:
        transcript_path = input_data.get("transcript_path", "")
        if not transcript_path or not os.path.exists(transcript_path):
            return

        turn = parse_last_turn(transcript_path)
        if turn is None:
            return

        db.cmd_record_interaction(project, json.dumps(turn))
    except Exception as e:
        get_logger().error("handle_stop failed: %s", e, exc_info=True)


def handle_session_start(input_data):
    """Handle SessionStart hook: init DB and record session context."""
    cwd = input_data.get("cwd", os.getcwd())
    project = get_project_name(cwd)

    if not is_recording_enabled(project):
        return

    try:
        db.cmd_init(project)

        git_branch = ""
        git_commit = ""
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, cwd=cwd, timeout=5
            )
            if result.returncode == 0:
                git_branch = result.stdout.strip()
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, cwd=cwd, timeout=5
            )
            if result.returncode == 0:
                git_commit = result.stdout.strip()
        except Exception:
            pass

        # Model info isn't in SessionStart payload, record what we can
        db.cmd_record_session_context(
            project, model="", git_branch=git_branch, git_commit=git_commit
        )
    except Exception as e:
        get_logger().error("handle_session_start failed: %s", e, exc_info=True)


# --- Install / Uninstall ---

HOOK_COMMAND = "python3 $HOME/.claude/scripts/confessional_hook.py"
HOOK_EVENTS = ("Stop", "SessionStart")


def _make_hook_entry():
    return {"hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 10}]}


def install_hooks():
    """Add confessional hooks to ~/.claude/settings.json."""
    settings_path = Path.home() / ".claude" / "settings.json"
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
    settings_path = Path.home() / ".claude" / "settings.json"
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
    # Handle --install / --uninstall as CLI flags
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

    if event == "Stop":
        handle_stop(input_data)
    elif event == "SessionStart":
        handle_session_start(input_data)

    sys.exit(0)


if __name__ == "__main__":
    main()
