"""Tests for turn_blocks table and ordered recording.

Covers:
- turn_blocks table exists after init
- parse_last_turn returns blocks in sequence
- record_interaction inserts blocks alongside existing tool_usage/responses
- get_turn_blocks retrieves ordered blocks grouped by prompt_id
"""

import json

import reflection_db as db
from confessional_hook import parse_last_turn
from tests.conftest import make_transcript, make_user_entry, make_assistant_entry


class TestTurnBlocksSchema:

    def test_table_exists(self, conn):
        """turn_blocks table should exist after init_db."""
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='turn_blocks'"
        ).fetchone()
        assert row is not None

    def test_table_columns(self, conn):
        """turn_blocks should have the expected columns."""
        cursor = conn.execute("PRAGMA table_info(turn_blocks)")
        columns = {row[1] for row in cursor.fetchall()}
        assert columns == {"id", "prompt_id", "project", "sequence", "block_type", "content", "tool_name"}


class TestParseLastTurnBlocks:

    def test_simple_text_response(self, tmp_path):
        """Single text response should produce one text block."""
        transcript = make_transcript(tmp_path, [
            make_user_entry("Hello"),
            make_assistant_entry([{"type": "text", "text": "Hi there."}]),
        ])
        result = parse_last_turn(transcript)
        assert "blocks" in result
        assert len(result["blocks"]) == 1
        assert result["blocks"][0] == {"sequence": 0, "type": "text", "content": "Hi there."}

    def test_interleaved_text_and_tool(self, tmp_path):
        """Text, tool_use, tool_result, text should produce 4 blocks in order."""
        transcript = make_transcript(tmp_path, [
            make_user_entry("Check and fix"),
            make_assistant_entry([
                {"type": "text", "text": "Let me check."},
            ], msg_id="a1"),
            make_assistant_entry([
                {"type": "tool_use", "id": "t1", "name": "Read",
                 "input": {"file_path": "/tmp/x.py"}},
            ], msg_id="a1"),
            make_user_entry([
                {"type": "tool_result", "tool_use_id": "t1", "content": "file contents"},
            ]),
            make_assistant_entry([
                {"type": "text", "text": "I see the issue."},
            ], msg_id="a2"),
        ])
        result = parse_last_turn(transcript)
        blocks = result["blocks"]
        assert len(blocks) == 4
        assert blocks[0] == {"sequence": 0, "type": "text", "content": "Let me check."}
        assert blocks[1] == {"sequence": 1, "type": "tool_use", "content": "/tmp/x.py", "tool_name": "Read"}
        assert blocks[2] == {"sequence": 2, "type": "tool_result", "content": "file contents", "tool_name": "Read"}
        assert blocks[3] == {"sequence": 3, "type": "text", "content": "I see the issue."}

    def test_multiple_tools_in_sequence(self, tmp_path):
        """Multiple tool_use/result pairs should be sequenced correctly."""
        transcript = make_transcript(tmp_path, [
            make_user_entry("Read two files"),
            make_assistant_entry([
                {"type": "tool_use", "id": "t1", "name": "Read",
                 "input": {"file_path": "/a.py"}},
            ]),
            make_user_entry([
                {"type": "tool_result", "tool_use_id": "t1", "content": "a contents"},
            ]),
            make_assistant_entry([
                {"type": "tool_use", "id": "t2", "name": "Read",
                 "input": {"file_path": "/b.py"}},
            ]),
            make_user_entry([
                {"type": "tool_result", "tool_use_id": "t2", "content": "b contents"},
            ]),
            make_assistant_entry([
                {"type": "text", "text": "Done."},
            ]),
        ])
        result = parse_last_turn(transcript)
        blocks = result["blocks"]
        assert len(blocks) == 5
        # Verify sequence ordering
        for i, block in enumerate(blocks):
            assert block["sequence"] == i
        # Verify types
        types = [b["type"] for b in blocks]
        assert types == ["tool_use", "tool_result", "tool_use", "tool_result", "text"]

    def test_tool_only_turn_has_blocks(self, tmp_path):
        """Tool-only turn should still produce blocks."""
        transcript = make_transcript(tmp_path, [
            make_user_entry("Fix it"),
            make_assistant_entry([
                {"type": "tool_use", "id": "t1", "name": "Edit",
                 "input": {"file_path": "/x.py", "old_string": "a", "new_string": "b"}},
            ]),
            make_user_entry([
                {"type": "tool_result", "tool_use_id": "t1", "content": "ok"},
            ]),
        ])
        result = parse_last_turn(transcript)
        assert len(result["blocks"]) == 2
        assert result["blocks"][0]["type"] == "tool_use"
        assert result["blocks"][1]["type"] == "tool_result"


class TestRecordInteractionBlocks:

    def test_blocks_inserted_to_db(self, seeded_project, conn):
        """record_interaction should insert blocks into turn_blocks table."""
        interaction = {
            "prompt": "hello",
            "response": "hi",
            "tools": [],
            "blocks": [
                {"sequence": 0, "type": "text", "content": "hi"},
            ],
        }
        db.cmd_record_interaction(seeded_project, json.dumps(interaction))

        rows = conn.execute("SELECT * FROM turn_blocks ORDER BY sequence").fetchall()
        assert len(rows) == 1
        row = dict(rows[0])
        assert row["block_type"] == "text"
        assert row["content"] == "hi"
        assert row["sequence"] == 0
        assert row["project"] == seeded_project

    def test_multiple_blocks_inserted(self, seeded_project, conn):
        """Multiple blocks should all be inserted with correct sequencing."""
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
                {"sequence": 2, "type": "tool_result", "content": "file data", "tool_name": "Read"},
                {"sequence": 3, "type": "text", "content": "Done."},
            ],
        }
        db.cmd_record_interaction(seeded_project, json.dumps(interaction))

        rows = conn.execute("SELECT * FROM turn_blocks ORDER BY sequence").fetchall()
        assert len(rows) == 4
        assert [dict(r)["block_type"] for r in rows] == ["text", "tool_use", "tool_result", "text"]

    def test_blocks_linked_to_prompt(self, seeded_project, conn):
        """Blocks should have the correct prompt_id foreign key."""
        interaction = {
            "prompt": "test",
            "response": "ok",
            "tools": [],
            "blocks": [{"sequence": 0, "type": "text", "content": "ok"}],
        }
        db.cmd_record_interaction(seeded_project, json.dumps(interaction))

        prompt_row = conn.execute("SELECT id FROM prompts WHERE project = ?", (seeded_project,)).fetchone()
        block_row = conn.execute("SELECT prompt_id FROM turn_blocks").fetchone()
        assert block_row[0] == prompt_row[0]

    def test_no_blocks_key_graceful(self, seeded_project, conn):
        """Interaction without blocks key should still work (backward compat)."""
        interaction = {
            "prompt": "hello",
            "response": "hi",
            "tools": [],
        }
        db.cmd_record_interaction(seeded_project, json.dumps(interaction))

        rows = conn.execute("SELECT * FROM turn_blocks").fetchall()
        assert len(rows) == 0

        # But prompt and response should still be recorded
        prompt_row = conn.execute("SELECT id FROM prompts").fetchone()
        assert prompt_row is not None


class TestGetTurnBlocks:

    def test_retrieves_blocks_since_breakpoint(self, seeded_project, conn):
        """get_turn_blocks should return blocks grouped by prompt_id."""
        interaction = {
            "prompt": "check",
            "response": "done",
            "tools": [],
            "blocks": [
                {"sequence": 0, "type": "text", "content": "Let me check."},
                {"sequence": 1, "type": "tool_use", "content": "/x.py", "tool_name": "Read"},
                {"sequence": 2, "type": "text", "content": "Done."},
            ],
        }
        db.cmd_record_interaction(seeded_project, json.dumps(interaction))

        result = db.cmd_get_turn_blocks(seeded_project)
        assert len(result) == 1  # One turn
        turn_blocks = result[0]["blocks"]
        assert len(turn_blocks) == 3
        assert turn_blocks[0]["block_type"] == "text"
        assert turn_blocks[1]["block_type"] == "tool_use"
        assert turn_blocks[2]["block_type"] == "text"

    def test_multiple_turns(self, seeded_project, conn):
        """Multiple turns should each have their own block group."""
        for prompt in ["first", "second"]:
            interaction = {
                "prompt": prompt,
                "response": f"re: {prompt}",
                "tools": [],
                "blocks": [{"sequence": 0, "type": "text", "content": f"re: {prompt}"}],
            }
            db.cmd_record_interaction(seeded_project, json.dumps(interaction))

        result = db.cmd_get_turn_blocks(seeded_project)
        assert len(result) == 2

    def test_empty_when_no_blocks(self, seeded_project, conn):
        """Returns empty list when no blocks recorded."""
        result = db.cmd_get_turn_blocks(seeded_project)
        assert result == []
