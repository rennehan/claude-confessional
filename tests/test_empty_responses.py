"""Tests for tool-only turns (no text blocks in response).

Currently, parse_last_turn returns None when there are tools but no text.
After fix: should return a synthetic response summarizing the tools used.
"""

from tests.conftest import make_transcript, make_user_entry, make_assistant_entry

from confessional_hook import parse_last_turn


class TestToolOnlyTurns:

    def test_single_tool_no_text(self, tmp_path):
        """Turn with one tool call and no text should still be recorded."""
        transcript = make_transcript(tmp_path, [
            make_user_entry("Fix the bug"),
            make_assistant_entry([
                {"type": "tool_use", "id": "t1", "name": "Edit",
                 "input": {"file_path": "/tmp/x.py", "old_string": "a", "new_string": "b"}},
            ]),
            make_user_entry([
                {"type": "tool_result", "tool_use_id": "t1", "content": "ok"},
            ]),
        ])
        result = parse_last_turn(transcript)
        assert result is not None
        assert result["prompt"] == "Fix the bug"
        assert len(result["tools"]) == 1
        assert "[tool-only turn: Edit]" in result["response"]

    def test_multiple_tools_no_text(self, tmp_path):
        """Multiple tools, no text — synthetic response lists all tool names."""
        transcript = make_transcript(tmp_path, [
            make_user_entry("Read and edit"),
            make_assistant_entry([
                {"type": "tool_use", "id": "t1", "name": "Read",
                 "input": {"file_path": "/tmp/a.py"}},
            ]),
            make_user_entry([
                {"type": "tool_result", "tool_use_id": "t1", "content": "contents"},
            ]),
            make_assistant_entry([
                {"type": "tool_use", "id": "t2", "name": "Edit",
                 "input": {"file_path": "/tmp/a.py", "old_string": "x", "new_string": "y"}},
            ]),
            make_user_entry([
                {"type": "tool_result", "tool_use_id": "t2", "content": "ok"},
            ]),
        ])
        result = parse_last_turn(transcript)
        assert result is not None
        assert "[tool-only turn: Read, Edit]" in result["response"]

    def test_tools_with_text_not_affected(self, tmp_path):
        """Normal turn with both tools and text should not get synthetic response."""
        transcript = make_transcript(tmp_path, [
            make_user_entry("Check file"),
            make_assistant_entry([
                {"type": "tool_use", "id": "t1", "name": "Read",
                 "input": {"file_path": "/tmp/a.py"}},
            ]),
            make_user_entry([
                {"type": "tool_result", "tool_use_id": "t1", "content": "contents"},
            ]),
            make_assistant_entry([
                {"type": "text", "text": "The file looks good."},
            ]),
        ])
        result = parse_last_turn(transcript)
        assert result is not None
        assert result["response"] == "The file looks good."
        assert "[tool-only turn" not in result["response"]

    def test_subagent_only_turn(self, tmp_path):
        """Subagent-only turn should also get recorded."""
        transcript = make_transcript(tmp_path, [
            make_user_entry("Explore the project"),
            make_assistant_entry([
                {"type": "tool_use", "id": "t1", "name": "Task",
                 "input": {"prompt": "explore structure", "subagent_type": "Explore"}},
            ]),
            make_user_entry([
                {"type": "tool_result", "tool_use_id": "t1", "content": "done"},
            ]),
        ])
        result = parse_last_turn(transcript)
        assert result is not None
        assert "[tool-only turn: Task]" in result["response"]
