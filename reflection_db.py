#!/usr/bin/env python3
"""
Reflection DB — stores prompts, responses, and breakpoints for Claude Code sessions.
Database location: ~/.reflection/history.db
"""

import sqlite3
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

DB_DIR = Path.home() / ".reflection"
DB_PATH = DB_DIR / "history.db"
VERBOSE = False


def get_connection():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS breakpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            breakpoint_id INTEGER,
            timestamp TEXT NOT NULL,
            prompt TEXT NOT NULL,
            transcript_offset INTEGER,
            FOREIGN KEY (breakpoint_id) REFERENCES breakpoints(id)
        );

        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_id INTEGER NOT NULL,
            project TEXT NOT NULL,
            breakpoint_id INTEGER,
            timestamp TEXT NOT NULL,
            response TEXT NOT NULL,
            FOREIGN KEY (prompt_id) REFERENCES prompts(id),
            FOREIGN KEY (breakpoint_id) REFERENCES breakpoints(id)
        );

        CREATE TABLE IF NOT EXISTS session_context (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            breakpoint_id INTEGER,
            timestamp TEXT NOT NULL,
            model TEXT,
            git_branch TEXT,
            git_commit TEXT,
            mcp_servers TEXT,
            claude_md_hash TEXT,
            FOREIGN KEY (breakpoint_id) REFERENCES breakpoints(id)
        );

        CREATE TABLE IF NOT EXISTS tool_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_id INTEGER NOT NULL,
            project TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            tool_input_summary TEXT,
            files_touched TEXT,
            is_subagent INTEGER DEFAULT 0,
            subagent_task TEXT,
            subagent_result_summary TEXT,
            duration_ms INTEGER,
            FOREIGN KEY (prompt_id) REFERENCES prompts(id)
        );

        CREATE TABLE IF NOT EXISTS reflections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            breakpoint_start_id INTEGER,
            breakpoint_end_id INTEGER,
            timestamp TEXT NOT NULL,
            reflection TEXT NOT NULL,
            git_summary TEXT,
            prompt_count INTEGER,
            FOREIGN KEY (breakpoint_start_id) REFERENCES breakpoints(id),
            FOREIGN KEY (breakpoint_end_id) REFERENCES breakpoints(id)
        );

        CREATE INDEX IF NOT EXISTS idx_prompts_project ON prompts(project);
        CREATE INDEX IF NOT EXISTS idx_prompts_breakpoint ON prompts(breakpoint_id);
        CREATE INDEX IF NOT EXISTS idx_responses_prompt ON responses(prompt_id);
        CREATE INDEX IF NOT EXISTS idx_responses_breakpoint ON responses(breakpoint_id);
        CREATE INDEX IF NOT EXISTS idx_breakpoints_project ON breakpoints(project);
        CREATE INDEX IF NOT EXISTS idx_reflections_project ON reflections(project);
        CREATE INDEX IF NOT EXISTS idx_session_context_project ON session_context(project);
        CREATE INDEX IF NOT EXISTS idx_session_context_breakpoint ON session_context(breakpoint_id);
        CREATE INDEX IF NOT EXISTS idx_tool_usage_prompt ON tool_usage(prompt_id);
        CREATE INDEX IF NOT EXISTS idx_tool_usage_project ON tool_usage(project);

        CREATE TABLE IF NOT EXISTS recording_state (
            project TEXT PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            enabled_at TEXT,
            disabled_at TEXT
        );

        CREATE TABLE IF NOT EXISTS turn_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_id INTEGER NOT NULL,
            project TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            block_type TEXT NOT NULL,
            content TEXT,
            tool_name TEXT,
            FOREIGN KEY (prompt_id) REFERENCES prompts(id)
        );
        CREATE INDEX IF NOT EXISTS idx_turn_blocks_prompt ON turn_blocks(prompt_id);
    """)
    conn.commit()
    conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def safe_int(value, default=0):
    """Safely convert a value to int, returning default on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def get_current_breakpoint(conn, project):
    """Get the most recent breakpoint for this project."""
    row = conn.execute(
        "SELECT id, timestamp, note FROM breakpoints WHERE project = ? ORDER BY id DESC LIMIT 1",
        (project,)
    ).fetchone()
    return dict(row) if row else None


def get_previous_breakpoint(conn, project):
    """Get the second most recent breakpoint (start of current window)."""
    rows = conn.execute(
        "SELECT id, timestamp, note FROM breakpoints WHERE project = ? ORDER BY id DESC LIMIT 2",
        (project,)
    ).fetchall()
    if len(rows) >= 2:
        return dict(rows[1])
    return None


def cmd_init(project):
    """Initialize DB and optionally create first breakpoint."""
    init_db()
    conn = get_connection()
    bp = get_current_breakpoint(conn, project)
    if bp is None:
        conn.execute(
            "INSERT INTO breakpoints (project, timestamp, note) VALUES (?, ?, ?)",
            (project, now_iso(), "Initial breakpoint")
        )
        conn.commit()
        if VERBOSE:
            print("Initialized reflection DB with first breakpoint.")
    else:
        if VERBOSE:
            print("Reflection DB already initialized.")
    conn.close()


def cmd_record_prompt(project, prompt_text):
    """Record a user prompt."""
    init_db()
    conn = get_connection()
    bp = get_current_breakpoint(conn, project)
    bp_id = bp["id"] if bp else None
    cursor = conn.execute(
        "INSERT INTO prompts (project, breakpoint_id, timestamp, prompt) VALUES (?, ?, ?, ?)",
        (project, bp_id, now_iso(), prompt_text)
    )
    prompt_id = cursor.lastrowid
    conn.commit()
    conn.close()
    if VERBOSE:
        print(json.dumps({"prompt_id": prompt_id}))
    else:
        print(prompt_id)


def cmd_record_response(project, prompt_id, response_text):
    """Record Claude's full response."""
    init_db()
    conn = get_connection()
    bp = get_current_breakpoint(conn, project)
    bp_id = bp["id"] if bp else None
    conn.execute(
        "INSERT INTO responses (prompt_id, project, breakpoint_id, timestamp, response) VALUES (?, ?, ?, ?, ?)",
        (safe_int(prompt_id), project, bp_id, now_iso(), response_text)
    )
    conn.commit()
    conn.close()
    if VERBOSE:
        print("Response recorded.")


def cmd_breakpoint(project, note=""):
    """Create a new breakpoint."""
    init_db()
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO breakpoints (project, timestamp, note) VALUES (?, ?, ?)",
        (project, now_iso(), note)
    )
    bp_id = cursor.lastrowid
    conn.commit()
    conn.close()
    print(json.dumps({"breakpoint_id": bp_id, "timestamp": now_iso()}))


def cmd_get_window(project):
    """Get all prompts and responses between the last two breakpoints (the current window)."""
    init_db()
    conn = get_connection()
    current_bp = get_current_breakpoint(conn, project)
    previous_bp = get_previous_breakpoint(conn, project)

    if current_bp is None:
        print(json.dumps({"error": "No breakpoints found. Run /breakpoint first."}))
        conn.close()
        return

    # Get prompts in the current window
    if previous_bp:
        prompts = conn.execute(
            """SELECT p.id, p.timestamp, p.prompt, r.response
               FROM prompts p
               LEFT JOIN responses r ON r.prompt_id = p.id
               WHERE p.project = ? AND p.breakpoint_id = ?
               ORDER BY p.id ASC""",
            (project, current_bp["id"])
        ).fetchall()
    else:
        # No previous breakpoint — get everything
        prompts = conn.execute(
            """SELECT p.id, p.timestamp, p.prompt, r.response
               FROM prompts p
               LEFT JOIN responses r ON r.prompt_id = p.id
               WHERE p.project = ?
               ORDER BY p.id ASC""",
            (project,)
        ).fetchall()

    window = {
        "breakpoint_start": previous_bp,
        "breakpoint_end": current_bp,
        "interactions": [
            {
                "prompt_id": dict(p)["id"],
                "timestamp": dict(p)["timestamp"],
                "prompt": dict(p)["prompt"],
                "response": dict(p)["response"]
            }
            for p in prompts
        ],
        "count": len(prompts)
    }
    print(json.dumps(window, indent=2))
    conn.close()


def cmd_get_all_since_breakpoint(project):
    """Get all prompts and responses since the most recent breakpoint."""
    init_db()
    conn = get_connection()
    current_bp = get_current_breakpoint(conn, project)

    if current_bp is None:
        print(json.dumps({"error": "No breakpoints found."}))
        conn.close()
        return

    prompts = conn.execute(
        """SELECT p.id, p.timestamp, p.prompt, r.response
           FROM prompts p
           LEFT JOIN responses r ON r.prompt_id = p.id
           WHERE p.project = ? AND p.breakpoint_id = ?
           ORDER BY p.id ASC""",
        (project, current_bp["id"])
    ).fetchall()

    result = {
        "breakpoint": current_bp,
        "interactions": [
            {
                "prompt_id": dict(p)["id"],
                "timestamp": dict(p)["timestamp"],
                "prompt": dict(p)["prompt"],
                "response": dict(p)["response"]
            }
            for p in prompts
        ],
        "count": len(prompts)
    }
    print(json.dumps(result, indent=2))
    conn.close()


def cmd_store_reflection(project, reflection_text, git_summary="", prompt_count=0):
    """Store a reflection."""
    init_db()
    conn = get_connection()
    current_bp = get_current_breakpoint(conn, project)
    previous_bp = get_previous_breakpoint(conn, project)

    conn.execute(
        """INSERT INTO reflections
           (project, breakpoint_start_id, breakpoint_end_id, timestamp, reflection, git_summary, prompt_count)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            project,
            previous_bp["id"] if previous_bp else None,
            current_bp["id"] if current_bp else None,
            now_iso(),
            reflection_text,
            git_summary,
            safe_int(prompt_count)
        )
    )
    conn.commit()
    conn.close()
    if VERBOSE:
        print("Reflection stored.")


def cmd_get_reflections(project):
    """Get all reflections for a project."""
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM reflections WHERE project = ? ORDER BY id ASC",
        (project,)
    ).fetchall()
    result = [dict(r) for r in rows]
    print(json.dumps(result, indent=2))
    conn.close()


def cmd_stats(project):
    """Get stats for a project."""
    init_db()
    conn = get_connection()
    bp_count = conn.execute("SELECT COUNT(*) FROM breakpoints WHERE project = ?", (project,)).fetchone()[0]
    prompt_count = conn.execute("SELECT COUNT(*) FROM prompts WHERE project = ?", (project,)).fetchone()[0]
    response_count = conn.execute("SELECT COUNT(*) FROM responses WHERE project = ?", (project,)).fetchone()[0]
    reflection_count = conn.execute("SELECT COUNT(*) FROM reflections WHERE project = ?", (project,)).fetchone()[0]
    tool_count = conn.execute("SELECT COUNT(*) FROM tool_usage WHERE project = ?", (project,)).fetchone()[0]
    subagent_count = conn.execute("SELECT COUNT(*) FROM tool_usage WHERE project = ? AND is_subagent = 1", (project,)).fetchone()[0]
    print(json.dumps({
        "project": project,
        "breakpoints": bp_count,
        "prompts": prompt_count,
        "responses": response_count,
        "reflections": reflection_count,
        "tool_calls": tool_count,
        "subagent_spawns": subagent_count
    }, indent=2))
    conn.close()


def cmd_record_session_context(project, model="", git_branch="", git_commit="", mcp_servers="", claude_md_hash=""):
    """Record session context at the start of a session or breakpoint."""
    init_db()
    conn = get_connection()
    bp = get_current_breakpoint(conn, project)
    bp_id = bp["id"] if bp else None
    conn.execute(
        """INSERT INTO session_context
           (project, breakpoint_id, timestamp, model, git_branch, git_commit, mcp_servers, claude_md_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (project, bp_id, now_iso(), model, git_branch, git_commit, mcp_servers, claude_md_hash)
    )
    conn.commit()
    conn.close()
    if VERBOSE:
        print("Session context recorded.")


def cmd_record_tool(project, prompt_id, tool_name, tool_input_summary="", files_touched="",
                    is_subagent=False, subagent_task="", subagent_result_summary="", duration_ms=0):
    """Record a tool usage event."""
    init_db()
    conn = get_connection()
    conn.execute(
        """INSERT INTO tool_usage
           (prompt_id, project, timestamp, tool_name, tool_input_summary, files_touched,
            is_subagent, subagent_task, subagent_result_summary, duration_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (safe_int(prompt_id), project, now_iso(), tool_name, tool_input_summary, files_touched,
         1 if is_subagent else 0, subagent_task, subagent_result_summary, safe_int(duration_ms))
    )
    conn.commit()
    conn.close()
    if VERBOSE:
        print("Tool usage recorded.")


def cmd_record_interaction(project, json_text):
    """Record a complete interaction: prompt + tools + response in one batch."""
    init_db()
    conn = get_connection()

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}), file=sys.stderr)
        sys.exit(1)

    bp = get_current_breakpoint(conn, project)
    bp_id = bp["id"] if bp else None
    ts = now_iso()

    # Check for duplicate via transcript_offset
    t_offset = data.get("transcript_offset")
    if t_offset is not None:
        dup = conn.execute(
            "SELECT 1 FROM prompts WHERE project = ? AND transcript_offset = ?",
            (project, t_offset)
        ).fetchone()
        if dup:
            conn.close()
            return

    # 1. Insert prompt
    cursor = conn.execute(
        "INSERT INTO prompts (project, breakpoint_id, timestamp, prompt, transcript_offset) VALUES (?, ?, ?, ?, ?)",
        (project, bp_id, ts, data.get("prompt", ""), t_offset)
    )
    prompt_id = cursor.lastrowid

    # 2. Insert tool usage
    for tool in data.get("tools", []):
        conn.execute(
            """INSERT INTO tool_usage
               (prompt_id, project, timestamp, tool_name, tool_input_summary, files_touched,
                is_subagent, subagent_task, subagent_result_summary, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                prompt_id, project, ts,
                tool.get("tool_name", ""),
                tool.get("input_summary", ""),
                tool.get("files_touched", ""),
                1 if tool.get("is_subagent", False) else 0,
                tool.get("subagent_task", ""),
                tool.get("subagent_result_summary", ""),
                safe_int(tool.get("duration_ms", 0))
            )
        )

    # 3. Insert response
    conn.execute(
        "INSERT INTO responses (prompt_id, project, breakpoint_id, timestamp, response) VALUES (?, ?, ?, ?, ?)",
        (prompt_id, project, bp_id, ts, data.get("response", ""))
    )

    # 4. Insert turn blocks (if present)
    for block in data.get("blocks", []):
        conn.execute(
            """INSERT INTO turn_blocks
               (prompt_id, project, sequence, block_type, content, tool_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                prompt_id, project,
                safe_int(block.get("sequence", 0)),
                block.get("type", ""),
                block.get("content", ""),
                block.get("tool_name"),
            )
        )

    conn.commit()
    conn.close()

    if VERBOSE:
        print(json.dumps({"prompt_id": prompt_id}))
    else:
        print(prompt_id)


def cmd_get_turn_blocks(project):
    """Get ordered turn blocks since the last breakpoint, grouped by prompt_id.

    Returns a list of dicts, each with prompt_id and blocks list.
    """
    init_db()
    conn = get_connection()
    bp = get_current_breakpoint(conn, project)
    if bp is None:
        conn.close()
        return []

    rows = conn.execute(
        """SELECT tb.prompt_id, tb.sequence, tb.block_type, tb.content, tb.tool_name
           FROM turn_blocks tb
           JOIN prompts p ON tb.prompt_id = p.id
           WHERE p.project = ? AND p.breakpoint_id = ?
           ORDER BY tb.prompt_id ASC, tb.sequence ASC""",
        (project, bp["id"])
    ).fetchall()
    conn.close()

    # Group by prompt_id
    turns = {}
    for row in rows:
        r = dict(row)
        pid = r["prompt_id"]
        if pid not in turns:
            turns[pid] = {"prompt_id": pid, "blocks": []}
        turns[pid]["blocks"].append({
            "sequence": r["sequence"],
            "block_type": r["block_type"],
            "content": r["content"],
            "tool_name": r["tool_name"],
        })

    return list(turns.values())


def cmd_get_tools_since_breakpoint(project):
    """Get all tool usage since the last breakpoint."""
    init_db()
    conn = get_connection()
    bp = get_current_breakpoint(conn, project)
    if bp is None:
        print(json.dumps({"error": "No breakpoints found."}))
        conn.close()
        return

    # Get prompt IDs in current breakpoint window
    rows = conn.execute(
        """SELECT t.* FROM tool_usage t
           JOIN prompts p ON t.prompt_id = p.id
           WHERE p.project = ? AND p.breakpoint_id = ?
           ORDER BY t.id ASC""",
        (project, bp["id"])
    ).fetchall()

    result = {
        "breakpoint": bp,
        "tool_calls": [dict(r) for r in rows],
        "count": len(rows),
        "subagent_count": sum(1 for r in rows if dict(r)["is_subagent"])
    }
    print(json.dumps(result, indent=2))
    conn.close()


def cmd_get_session_context(project):
    """Get the most recent session context for a project."""
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM session_context WHERE project = ? ORDER BY id DESC LIMIT 1",
        (project,)
    ).fetchone()
    if row:
        print(json.dumps(dict(row), indent=2))
    else:
        print(json.dumps({"error": "No session context found."}))
    conn.close()


def cmd_enable_recording(project):
    """Enable automatic hook-based recording for a project."""
    init_db()
    conn = get_connection()
    conn.execute(
        """INSERT INTO recording_state (project, enabled, enabled_at)
           VALUES (?, 1, ?)
           ON CONFLICT(project) DO UPDATE SET enabled = 1, enabled_at = ?""",
        (project, now_iso(), now_iso())
    )
    conn.commit()
    conn.close()
    print(json.dumps({"project": project, "recording": True}))


def cmd_disable_recording(project):
    """Disable automatic hook-based recording for a project."""
    init_db()
    conn = get_connection()
    conn.execute(
        """INSERT INTO recording_state (project, enabled, disabled_at)
           VALUES (?, 0, ?)
           ON CONFLICT(project) DO UPDATE SET enabled = 0, disabled_at = ?""",
        (project, now_iso(), now_iso())
    )
    conn.commit()
    conn.close()
    print(json.dumps({"project": project, "recording": False}))


def cmd_is_recording(project):
    """Check if recording is enabled for a project."""
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT enabled FROM recording_state WHERE project = ?", (project,)
    ).fetchone()
    conn.close()
    enabled = bool(row and row[0])
    print(json.dumps({"project": project, "recording": enabled}))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: reflection_db.py <command> <project> [args...] [--stdin] [--verbose]")
        print("Commands: init, record_prompt, record_response, breakpoint, get_window,")
        print("          get_all_since_breakpoint, store_reflection, get_reflections, stats,")
        print("          record_session_context, record_tool, get_tools_since_breakpoint,")
        print("          get_session_context, record_interaction,")
        print("          enable_recording, disable_recording, is_recording")
        print()
        print("Use --stdin to read the primary text payload from stdin instead of argv.")
        print("This avoids shell escaping issues with quotes, newlines, and special characters.")
        print("Use --verbose to print confirmation messages for mutation commands.")
        sys.exit(1)

    # Strip flags from argv, note whether they were present
    use_stdin = "--stdin" in sys.argv
    argv = [a for a in sys.argv if a != "--stdin"]
    VERBOSE = "--verbose" in argv
    argv = [a for a in argv if a != "--verbose"]

    command = argv[1]
    project = argv[2]

    def arg(index, default=""):
        """Safely get a positional arg with a default."""
        return argv[index] if len(argv) > index else default

    stdin_text = sys.stdin.read() if use_stdin else None

    if command == "init":
        cmd_init(project)
    elif command == "record_prompt":
        # Without --stdin: record_prompt <project> <prompt_text>
        # With --stdin:    record_prompt <project> --stdin  (prompt_text from stdin)
        prompt_text = stdin_text if use_stdin else arg(3)
        cmd_record_prompt(project, prompt_text)
    elif command == "record_response":
        # Without --stdin: record_response <project> <prompt_id> <response_text>
        # With --stdin:    record_response <project> <prompt_id> --stdin  (response_text from stdin)
        response_text = stdin_text if use_stdin else arg(4)
        cmd_record_response(project, arg(3), response_text)
    elif command == "breakpoint":
        cmd_breakpoint(project, arg(3, ""))
    elif command == "get_window":
        cmd_get_window(project)
    elif command == "get_all_since_breakpoint":
        cmd_get_all_since_breakpoint(project)
    elif command == "store_reflection":
        # Without --stdin: store_reflection <project> <reflection_text> <git_summary> <prompt_count>
        # With --stdin:    store_reflection <project> <git_summary> <prompt_count> --stdin  (reflection_text from stdin)
        if use_stdin:
            cmd_store_reflection(project, stdin_text, arg(3, ""), arg(4, 0))
        else:
            cmd_store_reflection(project, arg(3), arg(4, ""), arg(5, 0))
    elif command == "get_reflections":
        cmd_get_reflections(project)
    elif command == "stats":
        cmd_stats(project)
    elif command == "record_session_context":
        cmd_record_session_context(
            project,
            model=arg(3, ""),
            git_branch=arg(4, ""),
            git_commit=arg(5, ""),
            mcp_servers=arg(6, ""),
            claude_md_hash=arg(7, "")
        )
    elif command == "record_tool":
        # Without --stdin: record_tool <project> <prompt_id> <tool_name> <tool_input_summary> <files_touched> ...
        # With --stdin:    record_tool <project> <prompt_id> <tool_name> <files_touched> ... --stdin  (tool_input_summary from stdin)
        if use_stdin:
            cmd_record_tool(
                project,
                prompt_id=arg(3),
                tool_name=arg(4),
                tool_input_summary=stdin_text,
                files_touched=arg(5, ""),
                is_subagent=arg(6, "false").lower() == "true",
                subagent_task=arg(7, ""),
                subagent_result_summary=arg(8, ""),
                duration_ms=arg(9, 0)
            )
        else:
            cmd_record_tool(
                project,
                prompt_id=arg(3),
                tool_name=arg(4),
                tool_input_summary=arg(5, ""),
                files_touched=arg(6, ""),
                is_subagent=arg(7, "false").lower() == "true",
                subagent_task=arg(8, ""),
                subagent_result_summary=arg(9, ""),
                duration_ms=arg(10, 0)
            )
    elif command == "record_interaction":
        interaction_text = stdin_text if use_stdin else arg(3)
        cmd_record_interaction(project, interaction_text)
    elif command == "get_tools_since_breakpoint":
        cmd_get_tools_since_breakpoint(project)
    elif command == "get_session_context":
        cmd_get_session_context(project)
    elif command == "enable_recording":
        cmd_enable_recording(project)
    elif command == "disable_recording":
        cmd_disable_recording(project)
    elif command == "is_recording":
        cmd_is_recording(project)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
