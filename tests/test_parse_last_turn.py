"""Tests for parse_last_turn and _extract_user_prompt_text.

Covers:
- String content user prompts (existing behavior)
- Multi-part structured user content (text blocks, images, mixed)
- Tool result cycles correctly skipped as non-prompts
- Structured user messages WITHOUT tool_result treated as real prompts
- Empty and edge cases
"""

import json
from tests.conftest import make_transcript, make_user_entry, make_assistant_entry

from confessional_hook import parse_last_turn, _extract_user_prompt_text


# --- _extract_user_prompt_text ---

class TestExtractUserPromptText:

    def test_string_content(self):
        entry = {"message": {"content": "hello world"}}
        assert _extract_user_prompt_text(entry) == "hello world"

    def test_empty_string(self):
        entry = {"message": {"content": ""}}
        assert _extract_user_prompt_text(entry) == ""

    def test_list_with_text_blocks(self):
        entry = {"message": {"content": [
            {"type": "text", "text": "first part"},
            {"type": "text", "text": "second part"},
        ]}}
        assert _extract_user_prompt_text(entry) == "first part\nsecond part"

    def test_list_with_image_block(self):
        entry = {"message": {"content": [
            {"type": "text", "text": "look at this"},
            {"type": "image", "source": {"data": "base64..."}},
        ]}}
        result = _extract_user_prompt_text(entry)
        assert "look at this" in result
        assert "[image]" in result

    def test_list_with_tool_result_returns_empty(self):
        """Tool result content should yield empty — it's not a user prompt."""
        entry = {"message": {"content": [
            {"type": "tool_result", "tool_use_id": "123", "content": "ok"},
        ]}}
        assert _extract_user_prompt_text(entry) == ""

    def test_list_with_mixed_text_and_tool_result(self):
        """If content has both text and tool_result, extract only the text."""
        entry = {"message": {"content": [
            {"type": "tool_result", "tool_use_id": "123", "content": "ok"},
            {"type": "text", "text": "and also this"},
        ]}}
        result = _extract_user_prompt_text(entry)
        assert "and also this" in result
        assert "tool_result" not in result

    def test_list_with_plain_strings(self):
        """Content list may contain plain strings."""
        entry = {"message": {"content": ["hello", "world"]}}
        assert _extract_user_prompt_text(entry) == "hello\nworld"

    def test_non_string_non_list(self):
        entry = {"message": {"content": 42}}
        assert _extract_user_prompt_text(entry) == ""

    def test_missing_message(self):
        entry = {}
        assert _extract_user_prompt_text(entry) == ""

    def test_missing_content(self):
        entry = {"message": {}}
        assert _extract_user_prompt_text(entry) == ""


# --- parse_last_turn: user prompt identification ---

class TestParseLastTurnPromptDetection:

    def test_simple_string_prompt(self, tmp_path):
        transcript = make_transcript(tmp_path, [
            make_user_entry("What is 2+2?"),
            make_assistant_entry([{"type": "text", "text": "4"}]),
        ])
        result = parse_last_turn(transcript)
        assert result is not None
        assert result["prompt"] == "What is 2+2?"
        assert result["response"] == "4"

    def test_structured_text_prompt(self, tmp_path):
        """A user entry with list content containing text blocks is a real prompt."""
        transcript = make_transcript(tmp_path, [
            make_user_entry([
                {"type": "text", "text": "Please help"},
                {"type": "text", "text": "with this code"},
            ]),
            make_assistant_entry([{"type": "text", "text": "Sure."}]),
        ])
        result = parse_last_turn(transcript)
        assert result is not None
        assert "Please help" in result["prompt"]
        assert "with this code" in result["prompt"]

    def test_tool_result_cycle_skipped(self, tmp_path):
        """User entries with only tool_result content are not real prompts."""
        transcript = make_transcript(tmp_path, [
            make_user_entry("Read this file"),
            make_assistant_entry([
                {"type": "tool_use", "id": "t1", "name": "Read",
                 "input": {"file_path": "/tmp/x.py"}},
            ]),
            # This is a tool result cycle — NOT a user prompt
            make_user_entry([
                {"type": "tool_result", "tool_use_id": "t1", "content": "file contents"},
            ]),
            make_assistant_entry([{"type": "text", "text": "I see the file."}]),
        ])
        result = parse_last_turn(transcript)
        assert result is not None
        # Should pick up the original prompt, not the tool_result
        assert result["prompt"] == "Read this file"
        assert "I see the file" in result["response"]

    def test_structured_prompt_with_image(self, tmp_path):
        """User sends an image — should be recognized as a real prompt."""
        transcript = make_transcript(tmp_path, [
            make_user_entry([
                {"type": "text", "text": "What is in this image?"},
                {"type": "image", "source": {"data": "base64data"}},
            ]),
            make_assistant_entry([{"type": "text", "text": "It shows a cat."}]),
        ])
        result = parse_last_turn(transcript)
        assert result is not None
        assert "What is in this image?" in result["prompt"]

    def test_empty_transcript(self, tmp_path):
        transcript = make_transcript(tmp_path, [])
        result = parse_last_turn(transcript)
        assert result is None

    def test_no_assistant_response(self, tmp_path):
        transcript = make_transcript(tmp_path, [
            make_user_entry("Hello"),
        ])
        result = parse_last_turn(transcript)
        assert result is None

    def test_multiple_turns_gets_last(self, tmp_path):
        transcript = make_transcript(tmp_path, [
            make_user_entry("first", msg_id="u1"),
            make_assistant_entry([{"type": "text", "text": "resp1"}], msg_id="a1"),
            make_user_entry("second", msg_id="u2"),
            make_assistant_entry([{"type": "text", "text": "resp2"}], msg_id="a2"),
        ])
        result = parse_last_turn(transcript)
        assert result["prompt"] == "second"
        assert result["response"] == "resp2"


# --- parse_last_turn: tool extraction ---

class TestParseLastTurnToolExtraction:

    def test_tool_use_extracted(self, tmp_path):
        transcript = make_transcript(tmp_path, [
            make_user_entry("Check the file"),
            make_assistant_entry([
                {"type": "tool_use", "id": "t1", "name": "Read",
                 "input": {"file_path": "/tmp/foo.py"}},
            ]),
            make_user_entry([
                {"type": "tool_result", "tool_use_id": "t1", "content": "contents"},
            ]),
            make_assistant_entry([{"type": "text", "text": "Done."}]),
        ])
        result = parse_last_turn(transcript)
        assert len(result["tools"]) == 1
        assert result["tools"][0]["tool_name"] == "Read"
        assert "/tmp/foo.py" in result["tools"][0]["input_summary"]

    def test_multiple_tools(self, tmp_path):
        transcript = make_transcript(tmp_path, [
            make_user_entry("Do multiple things"),
            make_assistant_entry([
                {"type": "tool_use", "id": "t1", "name": "Read",
                 "input": {"file_path": "/a.py"}},
            ]),
            make_user_entry([
                {"type": "tool_result", "tool_use_id": "t1", "content": "a"},
            ]),
            make_assistant_entry([
                {"type": "tool_use", "id": "t2", "name": "Bash",
                 "input": {"command": "ls -la"}},
            ]),
            make_user_entry([
                {"type": "tool_result", "tool_use_id": "t2", "content": "b"},
            ]),
            make_assistant_entry([{"type": "text", "text": "All done."}]),
        ])
        result = parse_last_turn(transcript)
        assert len(result["tools"]) == 2
        tool_names = [t["tool_name"] for t in result["tools"]]
        assert "Read" in tool_names
        assert "Bash" in tool_names

    def test_subagent_detected(self, tmp_path):
        transcript = make_transcript(tmp_path, [
            make_user_entry("Explore the codebase"),
            make_assistant_entry([
                {"type": "tool_use", "id": "t1", "name": "Task",
                 "input": {"prompt": "explore structure", "subagent_type": "Explore"}},
            ]),
            make_user_entry([
                {"type": "tool_result", "tool_use_id": "t1", "content": "result"},
            ]),
            make_assistant_entry([{"type": "text", "text": "Found it."}]),
        ])
        result = parse_last_turn(transcript)
        assert result["tools"][0]["is_subagent"] is True
        assert "explore structure" in result["tools"][0]["subagent_task"]
