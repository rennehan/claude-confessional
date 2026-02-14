#!/usr/bin/env python3
"""
confessional_store — pure JSON/JSONL storage for breakpoints, reflections, and recording state.

No SQL. No database. Just files.

Storage layout:
  ~/.reflection/
    config.json                          # Recording state per project
    projects/
      <project>/
        breakpoints.jsonl                # Append-only, one entry per line
        reflections.jsonl                # Append-only, one entry per line
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

STORE_DIR = Path(os.environ.get("CONFESSIONAL_STORE_DIR", str(Path.home() / ".reflection")))
CONFIG_PATH = STORE_DIR / "config.json"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _project_dir(project):
    """Get the project-specific storage directory."""
    return STORE_DIR / "projects" / project


# --- JSONL I/O ---

def _read_jsonl(path):
    """Read all entries from a JSONL file. Returns empty list if missing."""
    path = Path(path)
    if not path.exists():
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def _append_jsonl(path, entry):
    """Append a single JSON entry to a JSONL file. Creates dirs if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, separators=(",", ":"), ensure_ascii=False) + "\n")


# --- Config I/O ---

def _read_config():
    """Read config.json. Returns empty dict if missing."""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_config(config):
    """Write config.json atomically (write to tmp, then rename)."""
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(STORE_DIR), suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, str(CONFIG_PATH))
    except Exception:
        os.unlink(tmp_path)
        raise


# --- Breakpoints ---

def add_breakpoint(project, note=""):
    """Append a breakpoint entry. Returns the new breakpoint dict."""
    bp_path = _project_dir(project) / "breakpoints.jsonl"
    existing = _read_jsonl(bp_path)
    new_id = len(existing) + 1
    entry = {
        "id": new_id,
        "timestamp": _now_iso(),
        "note": note,
    }
    _append_jsonl(bp_path, entry)
    return entry


def get_current_breakpoint(project):
    """Get the most recent breakpoint (last entry). Returns None if empty."""
    entries = _read_jsonl(_project_dir(project) / "breakpoints.jsonl")
    return entries[-1] if entries else None


def get_previous_breakpoint(project):
    """Get the second most recent breakpoint. Returns None if < 2 entries."""
    entries = _read_jsonl(_project_dir(project) / "breakpoints.jsonl")
    return entries[-2] if len(entries) >= 2 else None


def get_all_breakpoints(project):
    """Get all breakpoints for a project."""
    return _read_jsonl(_project_dir(project) / "breakpoints.jsonl")


def get_breakpoint_by_id(project, breakpoint_id):
    """Get a specific breakpoint by its integer ID. Returns None if not found."""
    entries = get_all_breakpoints(project)
    for bp in entries:
        if bp.get("id") == breakpoint_id:
            return bp
    return None


# --- Reflections ---

def store_reflection(project, reflection_text, git_summary="", prompt_count=0,
                     loops=None):
    """Append a reflection entry. Returns the new reflection dict."""
    ref_path = _project_dir(project) / "reflections.jsonl"
    existing = _read_jsonl(ref_path)
    new_id = len(existing) + 1

    current_bp = get_current_breakpoint(project)
    previous_bp = get_previous_breakpoint(project)

    entry = {
        "id": new_id,
        "timestamp": _now_iso(),
        "breakpoint_id": current_bp["id"] if current_bp else None,
        "breakpoint_start": previous_bp["timestamp"] if previous_bp else None,
        "breakpoint_end": current_bp["timestamp"] if current_bp else None,
        "reflection": reflection_text,
        "git_summary": git_summary,
        "prompt_count": prompt_count,
        "loops": loops or [],
    }
    _append_jsonl(ref_path, entry)
    return entry


def get_all_loops(project):
    """Get all methodology loops across reflections, with metadata."""
    reflections = get_reflections(project)
    loops = []
    for ref in reflections:
        for loop_text in ref.get("loops", []):
            loops.append({
                "loop": loop_text,
                "reflection_id": ref["id"],
                "timestamp": ref["timestamp"],
                "breakpoint_id": ref.get("breakpoint_id"),
            })
    return loops


def get_reflections(project):
    """Get all reflections for a project."""
    return _read_jsonl(_project_dir(project) / "reflections.jsonl")


def get_reflections_summary(project):
    """Get reflections with metadata (for cross-session comparison)."""
    return _read_jsonl(_project_dir(project) / "reflections.jsonl")


# --- Dashboard Manifest ---

def _dashboards_dir(project):
    """Get the dashboards directory for a project."""
    return _project_dir(project) / "dashboards"


def append_dashboard_manifest(project, breakpoint_id, reflection_id, html_path):
    """Append a dashboard entry to the manifest. Returns the entry dict."""
    manifest_path = _dashboards_dir(project) / "manifest.jsonl"
    entry = {
        "breakpoint_id": breakpoint_id,
        "reflection_id": reflection_id,
        "html_path": str(html_path),
        "generated_at": _now_iso(),
    }
    _append_jsonl(manifest_path, entry)
    return entry


def get_dashboard_manifest(project):
    """Read all dashboard manifest entries for a project."""
    return _read_jsonl(_dashboards_dir(project) / "manifest.jsonl")


# --- Recording State ---

def enable_recording(project):
    """Enable recording for a project in config.json."""
    config = _read_config()
    projects = config.setdefault("projects", {})
    projects[project] = {
        "enabled": True,
        "enabled_at": _now_iso(),
    }
    _write_config(config)


def disable_recording(project):
    """Disable recording for a project in config.json."""
    config = _read_config()
    projects = config.setdefault("projects", {})
    projects[project] = {
        "enabled": False,
        "disabled_at": _now_iso(),
    }
    _write_config(config)


def is_recording(project):
    """Check if recording is enabled for a project."""
    config = _read_config()
    projects = config.get("projects", {})
    proj = projects.get(project, {})
    return proj.get("enabled", False)


# --- CLI ---

def main():
    if len(sys.argv) < 3:
        print("Usage: confessional_store.py <command> <project> [args...] [--stdin]")
        print("Commands: breakpoint, get_current_breakpoint, get_previous_breakpoint,")
        print("          get_all_breakpoints, get_breakpoint_by_id,")
        print("          store_reflection, get_reflections, get_reflections_summary,")
        print("          enable_recording, disable_recording, is_recording, init")
        sys.exit(1)

    use_stdin = "--stdin" in sys.argv
    # Extract --loops value if present
    loops_value = None
    filtered_argv = []
    skip_next = False
    for i, a in enumerate(sys.argv):
        if skip_next:
            skip_next = False
            continue
        if a == "--loops" and i + 1 < len(sys.argv):
            loops_value = json.loads(sys.argv[i + 1])
            skip_next = True
        elif a == "--stdin":
            continue
        else:
            filtered_argv.append(a)
    argv = filtered_argv

    command = argv[1]
    project = argv[2]

    def arg(index, default=""):
        return argv[index] if len(argv) > index else default

    stdin_text = sys.stdin.read() if use_stdin else None

    if command == "init":
        # Ensure project dir exists, create initial breakpoint if needed
        if not get_current_breakpoint(project):
            add_breakpoint(project, "Initial breakpoint")
        enable_recording(project)
        print(json.dumps({"project": project, "initialized": True}))

    elif command == "breakpoint":
        bp = add_breakpoint(project, arg(3, ""))
        print(json.dumps(bp))

    elif command == "get_current_breakpoint":
        bp = get_current_breakpoint(project)
        if bp:
            print(json.dumps(bp))
        else:
            print(json.dumps({"error": "No breakpoints found."}))

    elif command == "get_previous_breakpoint":
        bp = get_previous_breakpoint(project)
        if bp:
            print(json.dumps(bp))
        else:
            print(json.dumps({"error": "No previous breakpoint."}))

    elif command == "get_all_breakpoints":
        bps = get_all_breakpoints(project)
        print(json.dumps(bps, indent=2))

    elif command == "get_breakpoint_by_id":
        bp_id = int(arg(3, "0"))
        bp = get_breakpoint_by_id(project, bp_id)
        if bp:
            print(json.dumps(bp))
        else:
            print(json.dumps({"error": f"No breakpoint with id {bp_id}."}))

    elif command == "store_reflection":
        if use_stdin:
            ref = store_reflection(project, stdin_text, arg(3, ""), int(arg(4, "0")),
                                   loops=loops_value)
        else:
            ref = store_reflection(project, arg(3), arg(4, ""), int(arg(5, "0")),
                                   loops=loops_value)
        print(json.dumps({"id": ref["id"], "stored": True}))

    elif command == "get_reflections":
        refs = get_reflections(project)
        print(json.dumps(refs, indent=2))

    elif command == "get_reflections_summary":
        summary = get_reflections_summary(project)
        print(json.dumps(summary, indent=2))

    elif command == "enable_recording":
        enable_recording(project)
        print(json.dumps({"project": project, "recording": True}))

    elif command == "disable_recording":
        disable_recording(project)
        print(json.dumps({"project": project, "recording": False}))

    elif command == "is_recording":
        enabled = is_recording(project)
        print(json.dumps({"project": project, "recording": enabled}))

    elif command == "append_dashboard_manifest":
        entry = append_dashboard_manifest(
            project, int(arg(3)), int(arg(4)), arg(5))
        print(json.dumps(entry))

    elif command == "get_all_loops":
        loops = get_all_loops(project)
        print(json.dumps(loops, indent=2))

    elif command == "get_dashboard_manifest":
        manifest = get_dashboard_manifest(project)
        print(json.dumps(manifest, indent=2))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
