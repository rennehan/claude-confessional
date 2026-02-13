"""Tests for reflection_db command functions.

Covers the DB API functions that aren't exercised by other test modules:
- cmd_record_prompt / cmd_record_response (individual recording)
- cmd_breakpoint
- cmd_get_window
- cmd_stats
- cmd_record_tool
- cmd_disable_recording / cmd_is_recording
- cmd_store_reflection / cmd_get_reflections
- cmd_record_session_context / cmd_get_session_context
- safe_int
- get_previous_breakpoint
"""

import json

import reflection_db as db


class TestSafeInt:

    def test_valid_int(self):
        assert db.safe_int(42) == 42

    def test_string_int(self):
        assert db.safe_int("7") == 7

    def test_invalid_string(self):
        assert db.safe_int("abc") == 0

    def test_none(self):
        assert db.safe_int(None) == 0

    def test_custom_default(self):
        assert db.safe_int("bad", default=-1) == -1


class TestRecordPromptResponse:

    def test_record_prompt(self, seeded_project, conn, capsys):
        db.cmd_record_prompt(seeded_project, "test prompt")
        captured = capsys.readouterr()
        prompt_id = int(captured.out.strip())
        assert prompt_id > 0

        row = conn.execute("SELECT prompt FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
        assert row[0] == "test prompt"

    def test_record_response(self, seeded_project, conn, capsys):
        db.cmd_record_prompt(seeded_project, "q")
        prompt_id = int(capsys.readouterr().out.strip())

        db.cmd_record_response(seeded_project, prompt_id, "answer text")
        row = conn.execute("SELECT response FROM responses WHERE prompt_id = ?", (prompt_id,)).fetchone()
        assert row[0] == "answer text"


class TestBreakpoint:

    def test_creates_breakpoint(self, seeded_project, conn, capsys):
        db.cmd_breakpoint(seeded_project, "test note")
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert "breakpoint_id" in result

        row = conn.execute("SELECT note FROM breakpoints WHERE id = ?", (result["breakpoint_id"],)).fetchone()
        assert row[0] == "test note"

    def test_get_previous_breakpoint(self, seeded_project, conn):
        # seeded_project already has one breakpoint
        db.cmd_breakpoint(seeded_project, "second")
        prev = db.get_previous_breakpoint(conn, seeded_project)
        assert prev is not None
        assert prev["note"] == "Initial breakpoint"

    def test_no_previous_breakpoint(self, seeded_project, conn):
        # Only one breakpoint exists
        prev = db.get_previous_breakpoint(conn, seeded_project)
        assert prev is None


class TestGetWindow:

    def test_window_with_data(self, seeded_project, conn, capsys):
        db.cmd_record_prompt(seeded_project, "in window")
        capsys.readouterr()

        db.cmd_get_window(seeded_project)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["count"] >= 1

    def test_window_no_breakpoints(self, project, capsys):
        # project without init
        db.cmd_get_window(project)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert "error" in result


class TestStats:

    def test_basic_stats(self, seeded_project, conn, capsys):
        db.cmd_record_interaction(seeded_project, json.dumps({
            "prompt": "q", "response": "a", "tools": [
                {"tool_name": "Read", "input_summary": "/x", "files_touched": "/x",
                 "is_subagent": False, "subagent_task": "", "subagent_result_summary": "",
                 "duration_ms": 0}
            ]
        }))
        capsys.readouterr()

        db.cmd_stats(seeded_project)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["prompts"] >= 1
        assert result["tool_calls"] >= 1
        assert result["project"] == seeded_project


class TestRecordTool:

    def test_records_tool(self, seeded_project, conn, capsys):
        db.cmd_record_prompt(seeded_project, "q")
        pid = int(capsys.readouterr().out.strip())

        db.cmd_record_tool(seeded_project, prompt_id=pid, tool_name="Bash",
                          tool_input_summary="ls -la", files_touched="",
                          is_subagent=False, subagent_task="", subagent_result_summary="",
                          duration_ms=100)

        row = conn.execute("SELECT tool_name, duration_ms FROM tool_usage WHERE prompt_id = ?", (pid,)).fetchone()
        assert row[0] == "Bash"
        assert row[1] == 100


class TestRecordingState:

    def test_disable_recording(self, seeded_project, conn, capsys):
        db.cmd_disable_recording(seeded_project)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["recording"] is False

        row = conn.execute("SELECT enabled FROM recording_state WHERE project = ?", (seeded_project,)).fetchone()
        assert row[0] == 0

    def test_is_recording_enabled(self, seeded_project, capsys):
        db.cmd_is_recording(seeded_project)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["recording"] is True

    def test_is_recording_disabled(self, project, capsys):
        db.cmd_is_recording(project)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["recording"] is False


class TestSessionContext:

    def test_record_and_get(self, seeded_project, capsys):
        db.cmd_record_session_context(seeded_project, model="opus-4", git_branch="main",
                                      git_commit="abc123", mcp_servers="", claude_md_hash="hash")
        capsys.readouterr()

        db.cmd_get_session_context(seeded_project)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["model"] == "opus-4"
        assert result["git_branch"] == "main"

    def test_no_context(self, project, capsys):
        db.cmd_get_session_context(project)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert "error" in result


class TestGetToolsSinceBreakpoint:

    def test_returns_tools(self, seeded_project, capsys):
        db.cmd_record_interaction(seeded_project, json.dumps({
            "prompt": "q", "response": "a", "tools": [
                {"tool_name": "Bash", "input_summary": "ls", "files_touched": "",
                 "is_subagent": False, "subagent_task": "", "subagent_result_summary": "",
                 "duration_ms": 50},
                {"tool_name": "Task", "input_summary": "explore", "files_touched": "",
                 "is_subagent": True, "subagent_task": "explore", "subagent_result_summary": "",
                 "duration_ms": 0},
            ]
        }))
        capsys.readouterr()

        db.cmd_get_tools_since_breakpoint(seeded_project)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["count"] == 2
        assert result["subagent_count"] == 1
