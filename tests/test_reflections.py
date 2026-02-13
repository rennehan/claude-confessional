"""Tests for reflection improvements.

Covers:
- get_turn_blocks CLI command returns JSON
- get_reflections_summary returns all reflections with metadata
- get_all_since_breakpoint includes block data
- Cross-session reflection data availability
"""

import json
from io import StringIO
from unittest.mock import patch

import reflection_db as db


class TestGetTurnBlocksCLI:

    def test_returns_json(self, seeded_project, conn, capsys):
        """get_turn_blocks as CLI should print JSON."""
        interaction = {
            "prompt": "hello",
            "response": "hi",
            "tools": [],
            "blocks": [{"sequence": 0, "type": "text", "content": "hi"}],
        }
        db.cmd_record_interaction(seeded_project, json.dumps(interaction))
        capsys.readouterr()  # clear record_interaction output

        db.cmd_get_turn_blocks_print(seeded_project)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert len(result) == 1
        assert result[0]["blocks"][0]["block_type"] == "text"

    def test_empty_project(self, seeded_project, capsys):
        """Empty project should return empty JSON list."""
        db.cmd_get_turn_blocks_print(seeded_project)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result == []


class TestGetReflectionsSummary:

    def test_returns_all_reflections(self, seeded_project, conn):
        """get_reflections_summary should return all reflections with metadata."""
        db.cmd_store_reflection(seeded_project, "First reflection", "git log 1", 5)
        db.cmd_breakpoint(seeded_project, "end of session 1")
        db.cmd_store_reflection(seeded_project, "Second reflection", "git log 2", 3)

        result = db.cmd_get_reflections_summary(seeded_project)
        assert len(result) == 2
        assert result[0]["reflection"] == "First reflection"
        assert result[0]["prompt_count"] == 5
        assert result[1]["reflection"] == "Second reflection"

    def test_empty_project(self, seeded_project):
        """No reflections should return empty list."""
        result = db.cmd_get_reflections_summary(seeded_project)
        assert result == []

    def test_includes_timestamps(self, seeded_project, conn):
        """Each reflection should have a timestamp."""
        db.cmd_store_reflection(seeded_project, "A reflection", "", 1)
        result = db.cmd_get_reflections_summary(seeded_project)
        assert "timestamp" in result[0]


class TestGetAllSinceBreakpointWithBlocks:

    def test_includes_blocks_in_output(self, seeded_project, conn, capsys):
        """get_all_since_breakpoint should include turn_blocks data."""
        interaction = {
            "prompt": "check file",
            "response": "Done.",
            "tools": [{"tool_name": "Read", "input_summary": "/x.py",
                       "files_touched": "/x.py", "is_subagent": False,
                       "subagent_task": "", "subagent_result_summary": "",
                       "duration_ms": 0}],
            "blocks": [
                {"sequence": 0, "type": "text", "content": "Let me check."},
                {"sequence": 1, "type": "tool_use", "content": "/x.py", "tool_name": "Read"},
                {"sequence": 2, "type": "text", "content": "Done."},
            ],
        }
        db.cmd_record_interaction(seeded_project, json.dumps(interaction))
        # Clear the prompt_id output from record_interaction
        capsys.readouterr()

        db.cmd_get_all_since_breakpoint(seeded_project)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert "turn_blocks" in result
        assert len(result["turn_blocks"]) == 1
        assert len(result["turn_blocks"][0]["blocks"]) == 3
