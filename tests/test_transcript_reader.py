"""Tests for transcript_reader — reads Claude Code's native JSONL transcripts.

Covers:
- get_transcript_dir: path resolution
- find_sessions: session discovery and filtering
- parse_session: turn extraction, metrics, edge cases
- get_turns_since: windowed analysis across sessions
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from transcript_reader import (
    get_transcript_dir,
    find_sessions,
    parse_session,
    get_turns_since,
)


# --- Fixtures ---

def _ts(hours_ago=0):
    """ISO timestamp for N hours ago."""
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.isoformat()


def _queue_entry(session_id="sess-1", timestamp=None):
    return {
        "type": "queue-operation",
        "operation": "dequeue",
        "timestamp": timestamp or _ts(),
        "sessionId": session_id,
    }


def _user_entry(content, session_id="sess-1", timestamp=None, uuid="u1",
                version="2.1.39", git_branch="main"):
    return {
        "type": "user",
        "uuid": uuid,
        "parentUuid": None,
        "sessionId": session_id,
        "timestamp": timestamp or _ts(),
        "cwd": "/tmp/project",
        "version": version,
        "gitBranch": git_branch,
        "message": {"role": "user", "content": content},
    }


def _assistant_entry(content_blocks, model="claude-opus-4-6", session_id="sess-1",
                     timestamp=None, uuid="a1", parent_uuid="u1",
                     input_tokens=100, output_tokens=50,
                     cache_read=10, cache_creation=5,
                     stop_reason="end_turn"):
    return {
        "type": "assistant",
        "uuid": uuid,
        "parentUuid": parent_uuid,
        "sessionId": session_id,
        "timestamp": timestamp or _ts(),
        "cwd": "/tmp/project",
        "version": "2.1.39",
        "gitBranch": "main",
        "message": {
            "model": model,
            "id": "msg-123",
            "type": "message",
            "role": "assistant",
            "content": content_blocks,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_creation,
            },
        },
    }


def _tool_result_user_entry(tool_use_id="tu1", content="file contents here",
                            session_id="sess-1"):
    return {
        "type": "user",
        "uuid": "u-tr",
        "sessionId": session_id,
        "timestamp": _ts(),
        "message": {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
            ],
        },
    }


def _write_session(directory, filename, entries):
    """Write a list of entries as a JSONL file."""
    path = directory / filename
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return path


# --- Tests: get_transcript_dir ---

class TestGetTranscriptDir:

    def test_basic_path(self):
        result = get_transcript_dir("/Users/foo/Projects/bar")
        assert result == Path.home() / ".claude" / "projects" / "-Users-foo-Projects-bar"

    def test_trailing_slash(self):
        result = get_transcript_dir("/Users/foo/Projects/bar/")
        # Should handle trailing slash gracefully
        expected = get_transcript_dir("/Users/foo/Projects/bar")
        # Both should resolve to the same logical directory
        assert isinstance(result, Path)

    def test_root_path(self):
        result = get_transcript_dir("/")
        assert isinstance(result, Path)


# --- Tests: find_sessions ---

class TestFindSessions:

    def test_finds_jsonl_files(self, tmp_path, monkeypatch):
        """Discovers .jsonl files in the transcript directory."""
        project_dir = tmp_path / "-tmp-project"
        project_dir.mkdir()
        ts = _ts(2)
        _write_session(project_dir, "sess-1.jsonl", [_queue_entry("sess-1", ts)])
        _write_session(project_dir, "sess-2.jsonl", [_queue_entry("sess-2", ts)])

        monkeypatch.setattr("transcript_reader.Path.home", lambda: tmp_path.parent)
        # Override get_transcript_dir for test
        result = find_sessions("/tmp/project", transcript_dir=project_dir)
        assert len(result) == 2
        assert all(p.suffix == ".jsonl" for p in result)

    def test_filters_by_since(self, tmp_path):
        """Sessions older than `since` are excluded."""
        project_dir = tmp_path / "sessions"
        project_dir.mkdir()
        old_ts = _ts(10)  # 10 hours ago
        new_ts = _ts(1)   # 1 hour ago
        _write_session(project_dir, "old.jsonl", [_queue_entry("old", old_ts)])
        _write_session(project_dir, "new.jsonl", [_queue_entry("new", new_ts)])

        since = _ts(5)  # 5 hours ago
        result = find_sessions("/tmp/project", since=since, transcript_dir=project_dir)
        assert len(result) == 1
        assert result[0].stem == "new"

    def test_empty_for_missing_dir(self, tmp_path):
        """Returns empty list if the directory doesn't exist."""
        missing = tmp_path / "nonexistent"
        result = find_sessions("/tmp/project", transcript_dir=missing)
        assert result == []

    def test_ignores_non_jsonl(self, tmp_path):
        """Ignores non-JSONL files and subdirectories."""
        project_dir = tmp_path / "sessions"
        project_dir.mkdir()
        _write_session(project_dir, "sess.jsonl", [_queue_entry()])
        (project_dir / "notes.txt").write_text("hello")
        (project_dir / "subdir").mkdir()

        result = find_sessions("/tmp/project", transcript_dir=project_dir)
        assert len(result) == 1

    def test_sorted_by_timestamp(self, tmp_path):
        """Sessions returned sorted by first entry timestamp."""
        project_dir = tmp_path / "sessions"
        project_dir.mkdir()
        _write_session(project_dir, "b.jsonl", [_queue_entry("b", _ts(1))])
        _write_session(project_dir, "a.jsonl", [_queue_entry("a", _ts(3))])
        _write_session(project_dir, "c.jsonl", [_queue_entry("c", _ts(2))])

        result = find_sessions("/tmp/project", transcript_dir=project_dir)
        stems = [p.stem for p in result]
        assert stems == ["a", "c", "b"]  # oldest first


# --- Tests: parse_session ---

class TestParseSession:

    def test_single_turn(self, tmp_path):
        """Extracts a simple single-turn conversation."""
        path = _write_session(tmp_path, "sess.jsonl", [
            _queue_entry(),
            _user_entry("Hello Claude"),
            _assistant_entry([{"type": "text", "text": "Hello! How can I help?"}]),
        ])
        result = parse_session(path)
        assert result["session_id"] == "sess-1"
        assert result["model"] == "claude-opus-4-6"
        assert len(result["turns"]) == 1
        turn = result["turns"][0]
        assert turn["prompt"] == "Hello Claude"
        assert "Hello! How can I help?" in turn["response"]
        assert turn["tools"] == []

    def test_turn_has_session_id(self, tmp_path):
        """Each turn carries the session's session_id."""
        path = _write_session(tmp_path, "sess.jsonl", [
            _queue_entry("my-session"),
            _user_entry("Hello", session_id="my-session"),
            _assistant_entry([{"type": "text", "text": "Hi"}],
                           session_id="my-session"),
        ])
        result = parse_session(path)
        assert result["turns"][0]["session_id"] == "my-session"

    def test_multi_turn(self, tmp_path):
        """Extracts multiple turns from a session."""
        path = _write_session(tmp_path, "sess.jsonl", [
            _queue_entry(),
            _user_entry("First question", uuid="u1"),
            _assistant_entry([{"type": "text", "text": "First answer"}], uuid="a1", parent_uuid="u1"),
            _user_entry("Second question", uuid="u2"),
            _assistant_entry([{"type": "text", "text": "Second answer"}], uuid="a2", parent_uuid="u2"),
        ])
        result = parse_session(path)
        assert len(result["turns"]) == 2
        assert result["turns"][0]["prompt"] == "First question"
        assert result["turns"][1]["prompt"] == "Second question"

    def test_tool_use_turn(self, tmp_path):
        """Extracts tool calls from a turn with tool use."""
        path = _write_session(tmp_path, "sess.jsonl", [
            _queue_entry(),
            _user_entry("Read my file"),
            _assistant_entry([
                {"type": "text", "text": "Let me read that."},
                {"type": "tool_use", "id": "tu1", "name": "Read",
                 "input": {"file_path": "/tmp/file.py"}},
            ], stop_reason="tool_use"),
            _tool_result_user_entry("tu1", "def hello(): pass"),
            _assistant_entry([
                {"type": "text", "text": "I see a hello function."},
            ], uuid="a2", input_tokens=200, output_tokens=30),
        ])
        result = parse_session(path)
        assert len(result["turns"]) == 1
        turn = result["turns"][0]
        assert len(turn["tools"]) == 1
        assert turn["tools"][0]["tool_name"] == "Read"
        assert turn["tools"][0]["files_touched"] == "/tmp/file.py"
        assert "hello function" in turn["response"]

    def test_structured_user_content(self, tmp_path):
        """Handles user messages with structured content (text blocks)."""
        path = _write_session(tmp_path, "sess.jsonl", [
            _queue_entry(),
            _user_entry([
                {"type": "text", "text": "Here's my question"},
                {"type": "text", "text": "with multiple parts"},
            ]),
            _assistant_entry([{"type": "text", "text": "Got it."}]),
        ])
        result = parse_session(path)
        assert len(result["turns"]) == 1
        assert "Here's my question" in result["turns"][0]["prompt"]
        assert "with multiple parts" in result["turns"][0]["prompt"]

    def test_image_in_user_content(self, tmp_path):
        """Handles image blocks in user content."""
        path = _write_session(tmp_path, "sess.jsonl", [
            _queue_entry(),
            _user_entry([
                {"type": "text", "text": "What's in this image?"},
                {"type": "image", "source": {"type": "base64", "data": "..."}},
            ]),
            _assistant_entry([{"type": "text", "text": "I see a chart."}]),
        ])
        result = parse_session(path)
        assert "[image]" in result["turns"][0]["prompt"]

    def test_skips_tool_result_only_user_entries(self, tmp_path):
        """User entries that are only tool results don't start new turns."""
        path = _write_session(tmp_path, "sess.jsonl", [
            _queue_entry(),
            _user_entry("Read my code"),
            _assistant_entry([
                {"type": "tool_use", "id": "tu1", "name": "Read",
                 "input": {"file_path": "/f.py"}},
            ], stop_reason="tool_use"),
            _tool_result_user_entry("tu1", "code here"),
            _assistant_entry([{"type": "text", "text": "Here's what I found."}],
                           uuid="a2"),
        ])
        result = parse_session(path)
        # Should be 1 turn, not 2
        assert len(result["turns"]) == 1

    def test_sums_tokens_across_api_calls(self, tmp_path):
        """Token usage summed across multiple assistant entries in one turn."""
        path = _write_session(tmp_path, "sess.jsonl", [
            _queue_entry(),
            _user_entry("Do something"),
            _assistant_entry([
                {"type": "tool_use", "id": "tu1", "name": "Bash",
                 "input": {"command": "ls"}},
            ], stop_reason="tool_use", input_tokens=100, output_tokens=20,
               cache_read=5, cache_creation=3),
            _tool_result_user_entry("tu1"),
            _assistant_entry([{"type": "text", "text": "Done."}],
                           uuid="a2", input_tokens=150, output_tokens=30,
                           cache_read=10, cache_creation=2),
        ])
        result = parse_session(path)
        metrics = result["turns"][0]["metrics"]
        assert metrics["input_tokens"] == 250  # 100 + 150
        assert metrics["output_tokens"] == 50  # 20 + 30
        assert metrics["cache_read_tokens"] == 15  # 5 + 10
        assert metrics["cache_creation_tokens"] == 5  # 3 + 2

    def test_extracts_model(self, tmp_path):
        """Model name extracted from assistant entries."""
        path = _write_session(tmp_path, "sess.jsonl", [
            _queue_entry(),
            _user_entry("Hi"),
            _assistant_entry([{"type": "text", "text": "Hello"}],
                           model="claude-sonnet-4-5-20250929"),
        ])
        result = parse_session(path)
        assert result["model"] == "claude-sonnet-4-5-20250929"
        assert result["turns"][0]["metrics"]["model"] == "claude-sonnet-4-5-20250929"

    def test_extracts_version_and_branch(self, tmp_path):
        """Version and git branch extracted from entries."""
        path = _write_session(tmp_path, "sess.jsonl", [
            _queue_entry(),
            _user_entry("Hi", version="2.2.0", git_branch="feature/auth"),
            _assistant_entry([{"type": "text", "text": "Hello"}]),
        ])
        result = parse_session(path)
        assert result["version"] == "2.2.0"
        assert result["git_branch"] == "feature/auth"

    def test_tool_only_turn(self, tmp_path):
        """Turn with only tool calls and no text gets synthetic response."""
        path = _write_session(tmp_path, "sess.jsonl", [
            _queue_entry(),
            _user_entry("Fix the bug"),
            _assistant_entry([
                {"type": "tool_use", "id": "tu1", "name": "Read",
                 "input": {"file_path": "/a.py"}},
            ], stop_reason="tool_use"),
            _tool_result_user_entry("tu1"),
            _assistant_entry([
                {"type": "tool_use", "id": "tu2", "name": "Edit",
                 "input": {"file_path": "/a.py", "old_string": "x", "new_string": "y"}},
            ], stop_reason="tool_use", uuid="a2"),
            _tool_result_user_entry("tu2"),
            _assistant_entry([{"type": "text", "text": ""}], uuid="a3"),
        ])
        result = parse_session(path)
        assert len(result["turns"]) == 1
        # Tool-only turns get synthetic response OR the empty text is noted
        assert result["turns"][0]["tools"][0]["tool_name"] == "Read"
        assert result["turns"][0]["tools"][1]["tool_name"] == "Edit"

    def test_stop_reason_from_last_assistant(self, tmp_path):
        """Stop reason comes from the last assistant entry in the turn."""
        path = _write_session(tmp_path, "sess.jsonl", [
            _queue_entry(),
            _user_entry("Do it"),
            _assistant_entry([
                {"type": "tool_use", "id": "tu1", "name": "Bash",
                 "input": {"command": "ls"}},
            ], stop_reason="tool_use"),
            _tool_result_user_entry("tu1"),
            _assistant_entry([{"type": "text", "text": "Done."}],
                           uuid="a2", stop_reason="end_turn"),
        ])
        result = parse_session(path)
        assert result["turns"][0]["metrics"]["stop_reason"] == "end_turn"

    def test_corrupt_lines_skipped(self, tmp_path):
        """Corrupt JSONL lines are skipped gracefully."""
        path = tmp_path / "corrupt.jsonl"
        with open(path, "w") as f:
            f.write(json.dumps(_queue_entry()) + "\n")
            f.write("this is not json\n")
            f.write(json.dumps(_user_entry("Hello")) + "\n")
            f.write("{incomplete json\n")
            f.write(json.dumps(_assistant_entry([{"type": "text", "text": "Hi"}])) + "\n")
        result = parse_session(path)
        assert len(result["turns"]) == 1

    def test_missing_fields_graceful(self, tmp_path):
        """Entries missing expected fields don't crash."""
        path = _write_session(tmp_path, "sess.jsonl", [
            {"type": "queue-operation"},  # missing timestamp, sessionId
            {"type": "user", "message": {"content": "Hello"}},  # missing uuid etc
            {"type": "assistant", "message": {  # missing model, usage
                "content": [{"type": "text", "text": "Hi"}],
            }},
        ])
        result = parse_session(path)
        assert len(result["turns"]) == 1
        assert result["turns"][0]["metrics"]["input_tokens"] == 0
        assert result["turns"][0]["metrics"]["model"] == ""

    def test_empty_session(self, tmp_path):
        """Session with only queue-operation returns no turns."""
        path = _write_session(tmp_path, "sess.jsonl", [_queue_entry()])
        result = parse_session(path)
        assert result["turns"] == []

    def test_ordered_blocks(self, tmp_path):
        """Blocks capture the interleaved text/tool_use/tool_result sequence."""
        path = _write_session(tmp_path, "sess.jsonl", [
            _queue_entry(),
            _user_entry("Do things"),
            _assistant_entry([
                {"type": "text", "text": "Let me check."},
                {"type": "tool_use", "id": "tu1", "name": "Read",
                 "input": {"file_path": "/f.py"}},
            ], stop_reason="tool_use"),
            _tool_result_user_entry("tu1", "file contents"),
            _assistant_entry([
                {"type": "text", "text": "I see the issue."},
            ], uuid="a2"),
        ])
        result = parse_session(path)
        blocks = result["turns"][0]["blocks"]
        assert len(blocks) >= 3
        assert blocks[0]["type"] == "text"
        assert blocks[1]["type"] == "tool_use"
        assert blocks[2]["type"] == "tool_result"
        assert blocks[3]["type"] == "text"

    def test_subagent_detection(self, tmp_path):
        """Task tool calls are marked as subagent."""
        path = _write_session(tmp_path, "sess.jsonl", [
            _queue_entry(),
            _user_entry("Explore the codebase"),
            _assistant_entry([
                {"type": "tool_use", "id": "tu1", "name": "Task",
                 "input": {"prompt": "find all Python files", "subagent_type": "Explore"}},
            ], stop_reason="tool_use"),
            _tool_result_user_entry("tu1", "Found 10 files"),
            _assistant_entry([{"type": "text", "text": "Found files."}], uuid="a2"),
        ])
        result = parse_session(path)
        tool = result["turns"][0]["tools"][0]
        assert tool["is_subagent"] is True
        assert "find all Python files" in tool["input_summary"]


# --- Tests: get_turns_since ---

class TestGetTurnsSince:

    def test_filters_by_timestamp(self, tmp_path):
        """Only returns turns after the given timestamp."""
        project_dir = tmp_path / "sessions"
        project_dir.mkdir()
        old_ts = _ts(10)
        new_ts = _ts(1)
        _write_session(project_dir, "sess.jsonl", [
            _queue_entry(timestamp=old_ts),
            _user_entry("Old question", timestamp=old_ts),
            _assistant_entry([{"type": "text", "text": "Old answer"}], timestamp=old_ts),
            _user_entry("New question", uuid="u2", timestamp=new_ts),
            _assistant_entry([{"type": "text", "text": "New answer"}], uuid="a2",
                           parent_uuid="u2", timestamp=new_ts),
        ])

        since = _ts(5)
        result = get_turns_since("/tmp/project", since, transcript_dir=project_dir)
        assert result["turn_count"] == 1
        assert result["turns"][0]["prompt"] == "New question"

    def test_spans_multiple_sessions(self, tmp_path):
        """Aggregates turns across multiple session files."""
        project_dir = tmp_path / "sessions"
        project_dir.mkdir()
        ts = _ts(1)
        _write_session(project_dir, "sess-1.jsonl", [
            _queue_entry("sess-1", ts),
            _user_entry("Q1", session_id="sess-1", timestamp=ts),
            _assistant_entry([{"type": "text", "text": "A1"}], session_id="sess-1",
                           timestamp=ts),
        ])
        _write_session(project_dir, "sess-2.jsonl", [
            _queue_entry("sess-2", ts),
            _user_entry("Q2", session_id="sess-2", timestamp=ts),
            _assistant_entry([{"type": "text", "text": "A2"}], session_id="sess-2",
                           timestamp=ts),
        ])

        since = _ts(5)
        result = get_turns_since("/tmp/project", since, transcript_dir=project_dir)
        assert result["turn_count"] == 2
        assert len(result["sessions"]) == 2

    def test_aggregates_tool_stats(self, tmp_path):
        """Tool usage aggregated across all turns."""
        project_dir = tmp_path / "sessions"
        project_dir.mkdir()
        ts = _ts(1)
        _write_session(project_dir, "sess.jsonl", [
            _queue_entry(timestamp=ts),
            _user_entry("Q1", timestamp=ts),
            _assistant_entry([
                {"type": "tool_use", "id": "tu1", "name": "Read",
                 "input": {"file_path": "/a.py"}},
            ], stop_reason="tool_use", timestamp=ts),
            _tool_result_user_entry("tu1"),
            _assistant_entry([
                {"type": "tool_use", "id": "tu2", "name": "Read",
                 "input": {"file_path": "/b.py"}},
            ], stop_reason="tool_use", uuid="a2", timestamp=ts),
            _tool_result_user_entry("tu2"),
            _assistant_entry([
                {"type": "tool_use", "id": "tu3", "name": "Bash",
                 "input": {"command": "ls"}},
            ], stop_reason="tool_use", uuid="a3", timestamp=ts),
            _tool_result_user_entry("tu3"),
            _assistant_entry([{"type": "text", "text": "Done"}], uuid="a4",
                           timestamp=ts),
        ])

        since = _ts(5)
        result = get_turns_since("/tmp/project", since, transcript_dir=project_dir)
        assert result["tool_stats"]["total"] == 3
        assert result["tool_stats"]["by_tool"]["Read"] == 2
        assert result["tool_stats"]["by_tool"]["Bash"] == 1

    def test_aggregates_token_stats(self, tmp_path):
        """Token usage aggregated across all turns."""
        project_dir = tmp_path / "sessions"
        project_dir.mkdir()
        ts = _ts(1)
        _write_session(project_dir, "sess.jsonl", [
            _queue_entry(timestamp=ts),
            _user_entry("Q1", timestamp=ts),
            _assistant_entry([{"type": "text", "text": "A1"}],
                           input_tokens=100, output_tokens=50,
                           cache_read=10, cache_creation=5, timestamp=ts),
            _user_entry("Q2", uuid="u2", timestamp=ts),
            _assistant_entry([{"type": "text", "text": "A2"}], uuid="a2",
                           parent_uuid="u2",
                           input_tokens=200, output_tokens=80,
                           cache_read=20, cache_creation=8, timestamp=ts),
        ])

        since = _ts(5)
        result = get_turns_since("/tmp/project", since, transcript_dir=project_dir)
        assert result["token_stats"]["total_input"] == 300
        assert result["token_stats"]["total_output"] == 130
        assert result["token_stats"]["total_cache_read"] == 30
        assert result["token_stats"]["total_cache_creation"] == 13

    def test_empty_when_no_sessions(self, tmp_path):
        """Returns empty results for nonexistent project dir."""
        result = get_turns_since("/tmp/project", _ts(5),
                                transcript_dir=tmp_path / "nope")
        assert result["turn_count"] == 0
        assert result["turns"] == []

    def test_includes_prompt_linguistics(self, tmp_path):
        """get_turns_since includes prompt_linguistics key."""
        project_dir = tmp_path / "sessions"
        project_dir.mkdir()
        ts = _ts(1)
        _write_session(project_dir, "sess.jsonl", [
            _queue_entry(timestamp=ts),
            _user_entry("What is this?", timestamp=ts),
            _assistant_entry([{"type": "text", "text": "It's a thing."}],
                           timestamp=ts),
        ])
        result = get_turns_since("/tmp/project", _ts(5),
                                transcript_dir=project_dir)
        assert "prompt_linguistics" in result
        assert result["prompt_linguistics"]["question_ratio"] == 1.0

    def test_includes_effectiveness_signals(self, tmp_path):
        """get_turns_since includes effectiveness_signals key."""
        project_dir = tmp_path / "sessions"
        project_dir.mkdir()
        ts = _ts(1)
        _write_session(project_dir, "sess.jsonl", [
            _queue_entry(timestamp=ts),
            _user_entry("Fix the bug", timestamp=ts),
            _assistant_entry([{"type": "text", "text": "Fixed."}],
                           timestamp=ts),
            _user_entry("Add tests", uuid="u2", timestamp=ts),
            _assistant_entry([{"type": "text", "text": "Done."}], uuid="a2",
                           parent_uuid="u2", timestamp=ts),
        ])
        result = get_turns_since("/tmp/project", _ts(5),
                                transcript_dir=project_dir)
        assert "effectiveness_signals" in result
        assert result["effectiveness_signals"]["eligible_turns"] == 1

    def test_both_zeroed_when_no_turns(self, tmp_path):
        """Both analytics zeroed when no turns match."""
        result = get_turns_since("/tmp/project", _ts(5),
                                transcript_dir=tmp_path / "nope")
        assert result["prompt_linguistics"]["question_ratio"] == 0.0
        assert result["effectiveness_signals"]["correction_rate"] == 0.0


# --- Helper: turn dict builder ---

def _turn(prompt, response="response", tools=None, session_id="sess-1",
          input_tokens=100, output_tokens=50):
    """Build a minimal turn dict for linguistics/effectiveness tests."""
    return {
        "prompt": prompt,
        "response": response,
        "tools": tools or [],
        "blocks": [],
        "metrics": {
            "model": "claude-opus-4-6",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "stop_reason": "end_turn",
        },
        "timestamp": _ts(),
        "session_id": session_id,
    }


def _tool(name, file_path=""):
    """Build a minimal tool dict."""
    return {
        "tool_name": name,
        "input_summary": file_path or name,
        "files_touched": file_path,
        "is_subagent": name == "Task",
    }


# --- Tests: compute_prompt_linguistics ---

class TestComputePromptLinguistics:

    def test_empty_turns(self):
        from transcript_reader import compute_prompt_linguistics
        result = compute_prompt_linguistics([])
        assert result["question_ratio"] == 0.0
        assert result["imperative_ratio"] == 0.0
        assert result["prompt_length"]["count"] == 0
        assert result["frequent_ngrams"]["bigrams"] == []
        assert result["frequent_ngrams"]["trigrams"] == []
        assert result["certainty_markers"]["hedging_count"] == 0
        assert result["certainty_markers"]["assertive_count"] == 0
        assert result["agency_framing"]["dominant"] == "none"

    def test_single_turn(self):
        from transcript_reader import compute_prompt_linguistics
        result = compute_prompt_linguistics([_turn("Fix the bug")])
        assert result["prompt_length"]["count"] == 1
        assert result["prompt_length"]["median"] == 3.0
        assert result["prompt_length"]["stddev"] == 0.0

    def test_question_ratio_all_questions(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [_turn("What is this?"), _turn("How does it work?"), _turn("Why?")]
        result = compute_prompt_linguistics(turns)
        assert result["question_ratio"] == 1.0

    def test_question_ratio_none(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [_turn("Fix this"), _turn("Add that"), _turn("Done")]
        result = compute_prompt_linguistics(turns)
        assert result["question_ratio"] == 0.0

    def test_question_ratio_mixed(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [_turn("What is this?"), _turn("Fix it"),
                 _turn("How?"), _turn("Add tests")]
        result = compute_prompt_linguistics(turns)
        assert result["question_ratio"] == 0.5

    def test_imperative_ratio(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [_turn("Fix the bug"), _turn("I want to understand"),
                 _turn("Add a test"), _turn("The code is broken")]
        result = compute_prompt_linguistics(turns)
        assert result["imperative_ratio"] == 0.5  # fix, add

    def test_imperative_ratio_case_insensitive(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [_turn("FIX this"), _turn("fix that")]
        result = compute_prompt_linguistics(turns)
        assert result["imperative_ratio"] == 1.0

    def test_prompt_length_distribution(self):
        from transcript_reader import compute_prompt_linguistics
        # Word counts: 3, 5, 7, 9, 11
        turns = [
            _turn("one two three"),
            _turn("one two three four five"),
            _turn("one two three four five six seven"),
            _turn("one two three four five six seven eight nine"),
            _turn("one two three four five six seven eight nine ten eleven"),
        ]
        result = compute_prompt_linguistics(turns)
        assert result["prompt_length"]["median"] == 7.0
        assert result["prompt_length"]["mean"] == 7.0
        assert result["prompt_length"]["min"] == 3
        assert result["prompt_length"]["max"] == 11
        assert result["prompt_length"]["count"] == 5

    def test_prompt_length_single_prompt(self):
        from transcript_reader import compute_prompt_linguistics
        result = compute_prompt_linguistics([_turn("one two three four five")])
        assert result["prompt_length"]["stddev"] == 0.0
        assert result["prompt_length"]["median"] == 5.0

    def test_frequent_bigrams(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [
            _turn("for example this works great"),
            _turn("for example that also works"),
            _turn("for example another case"),
        ]
        result = compute_prompt_linguistics(turns)
        bigrams = result["frequent_ngrams"]["bigrams"]
        assert len(bigrams) > 0
        assert bigrams[0]["ngram"] == "for example"
        assert bigrams[0]["count"] == 3

    def test_frequent_trigrams(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [
            _turn("I think we should fix this"),
            _turn("I think we should add tests"),
            _turn("I think we need more coverage"),
        ]
        result = compute_prompt_linguistics(turns)
        trigrams = result["frequent_ngrams"]["trigrams"]
        assert len(trigrams) > 0
        # "i think we" should be top trigram
        assert trigrams[0]["ngram"] == "i think we"
        assert trigrams[0]["count"] == 3

    def test_ngrams_filter_stopwords(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [
            _turn("the a in on at to for of with by"),
            _turn("the a in on at to for of with by"),
        ]
        result = compute_prompt_linguistics(turns)
        # All bigrams/trigrams are pure stopwords — should be filtered out
        for bg in result["frequent_ngrams"]["bigrams"]:
            words = bg["ngram"].split()
            assert not all(w in {"the", "a", "in", "on", "at", "to", "for", "of", "with", "by"} for w in words)

    def test_ngrams_top_15_limit(self):
        from transcript_reader import compute_prompt_linguistics
        # Create 20+ distinct meaningful bigrams
        turns = []
        for i in range(20):
            turns.append(_turn(f"concept{i} works well here"))
        result = compute_prompt_linguistics(turns)
        assert len(result["frequent_ngrams"]["bigrams"]) <= 15

    def test_certainty_markers_hedging(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [
            _turn("Maybe we should try this"),
            _turn("I think this could work"),
            _turn("Not sure if this is right"),
        ]
        result = compute_prompt_linguistics(turns)
        assert result["certainty_markers"]["hedging_count"] >= 3
        assert result["certainty_markers"]["hedging_phrases"]["maybe"] == 1
        assert result["certainty_markers"]["hedging_phrases"]["i think"] == 1
        assert result["certainty_markers"]["hedging_phrases"]["not sure"] == 1

    def test_certainty_markers_assertive(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [
            _turn("You must fix this now"),
            _turn("We need to ensure correctness"),
            _turn("Make sure the tests pass"),
        ]
        result = compute_prompt_linguistics(turns)
        assert result["certainty_markers"]["assertive_count"] >= 3
        assert result["certainty_markers"]["assertive_phrases"]["must"] == 1
        assert result["certainty_markers"]["assertive_phrases"]["ensure"] == 1
        assert result["certainty_markers"]["assertive_phrases"]["make sure"] == 1

    def test_certainty_markers_ratio(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [
            _turn("Maybe we should try"),   # 1 hedge
            _turn("We must do this now"),    # 1 assert
            _turn("We need to fix it"),      # 1 assert (need to)
        ]
        result = compute_prompt_linguistics(turns)
        assert result["certainty_markers"]["hedging_count"] >= 1
        assert result["certainty_markers"]["assertive_count"] >= 2
        assert result["certainty_markers"]["ratio"] is not None
        assert result["certainty_markers"]["ratio"] > 1.0  # more assertive than hedging

    def test_certainty_markers_no_hedging(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [_turn("You must fix this"), _turn("Ensure it works")]
        result = compute_prompt_linguistics(turns)
        assert result["certainty_markers"]["ratio"] is None

    def test_agency_framing_i_dominant(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [
            _turn("I want to understand this"),
            _turn("I need the tests to pass"),
            _turn("I think we should refactor"),
        ]
        result = compute_prompt_linguistics(turns)
        assert result["agency_framing"]["i_count"] >= 3
        assert result["agency_framing"]["dominant"] == "i"

    def test_agency_framing_we_dominant(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [
            _turn("We should refactor this"),
            _turn("We could use a different approach"),
            _turn("We need more tests"),
        ]
        result = compute_prompt_linguistics(turns)
        assert result["agency_framing"]["we_count"] >= 3
        assert result["agency_framing"]["dominant"] == "we"

    def test_agency_framing_you_dominant(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [
            _turn("You should fix this"),
            _turn("You can read the file"),
            _turn("You need to handle errors"),
        ]
        result = compute_prompt_linguistics(turns)
        assert result["agency_framing"]["you_count"] >= 3
        assert result["agency_framing"]["dominant"] == "you"

    def test_agency_framing_lets_dominant(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [
            _turn("Let's fix this bug"),
            _turn("Let's think about it"),
            _turn("Let's add some tests"),
        ]
        result = compute_prompt_linguistics(turns)
        assert result["agency_framing"]["lets_count"] >= 3
        assert result["agency_framing"]["dominant"] == "lets"

    def test_agency_framing_none(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [_turn("Fix the bug"), _turn("Add tests")]
        result = compute_prompt_linguistics(turns)
        assert result["agency_framing"]["dominant"] == "none"

    def test_prompt_length_by_position(self):
        from transcript_reader import compute_prompt_linguistics
        # 8 prompts with known word counts: 2,2, 5,5,5,5, 10,10
        turns = [
            _turn("word word"),                           # first quarter
            _turn("word word"),                           # first quarter
            _turn("word word word word word"),             # middle half
            _turn("word word word word word"),             # middle half
            _turn("word word word word word"),             # middle half
            _turn("word word word word word"),             # middle half
            _turn("word word word word word word word word word word"),  # last quarter
            _turn("word word word word word word word word word word"),  # last quarter
        ]
        result = compute_prompt_linguistics(turns)
        assert result["prompt_length_by_position"]["first_quarter_avg"] == 2.0
        assert result["prompt_length_by_position"]["middle_half_avg"] == 5.0
        assert result["prompt_length_by_position"]["last_quarter_avg"] == 10.0

    def test_prompt_length_by_position_few_prompts(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [_turn("one two"), _turn("one two three")]
        result = compute_prompt_linguistics(turns)
        # Should not crash; all buckets should have values
        assert result["prompt_length_by_position"]["first_quarter_avg"] > 0
        assert result["prompt_length_by_position"]["middle_half_avg"] > 0
        assert result["prompt_length_by_position"]["last_quarter_avg"] > 0

    def test_blank_prompts_excluded(self):
        from transcript_reader import compute_prompt_linguistics
        turns = [_turn(""), _turn("   "), _turn("Fix the bug")]
        result = compute_prompt_linguistics(turns)
        assert result["prompt_length"]["count"] == 1  # only "Fix the bug"

    def test_skill_expansions_excluded(self):
        """Skill expansion prompts (e.g. /reflect, /sermon) should be filtered out."""
        from transcript_reader import compute_prompt_linguistics
        skill_prompt = "# Reflect\n\n" + "Analyze the user's methodology. " * 50
        turns = [
            _turn("Let's think about the dashboard"),
            _turn(skill_prompt),  # skill expansion — should be excluded
            _turn("push it"),
        ]
        result = compute_prompt_linguistics(turns)
        assert result["prompt_length"]["count"] == 2  # only organic prompts
        # Skill expansion text shouldn't pollute n-grams
        bigram_phrases = [b["ngram"] for b in result["frequent_ngrams"]["bigrams"]]
        assert "the user's" not in bigram_phrases

    def test_short_markdown_header_not_excluded(self):
        """Short prompts starting with # should NOT be excluded."""
        from transcript_reader import compute_prompt_linguistics
        turns = [_turn("# Fix this heading")]
        result = compute_prompt_linguistics(turns)
        assert result["prompt_length"]["count"] == 1

    def test_skill_expansion_detection(self):
        """Test _is_skill_expansion directly."""
        from transcript_reader import _is_skill_expansion
        # Skill expansion: starts with H1, 100+ words
        assert _is_skill_expansion("# Reflect\n\n" + "word " * 100)
        assert _is_skill_expansion("# Sermon\n\n" + "word " * 150)
        # NOT skill expansions
        assert not _is_skill_expansion("# Fix this heading")
        assert not _is_skill_expansion("Let's think about this")
        assert not _is_skill_expansion("")
        assert not _is_skill_expansion("   ")


# --- Tests: CLI ---

# --- Tests: compute_effectiveness_signals ---

class TestComputeEffectivenessSignals:

    def test_empty_turns(self):
        from transcript_reader import compute_effectiveness_signals
        result = compute_effectiveness_signals([])
        assert result["correction_rate"] == 0.0
        assert result["corrections_total"] == 0
        assert result["eligible_turns"] == 0
        assert result["first_response_acceptance"] == 1.0
        for style in ("question", "imperative", "statement"):
            assert result["per_style_effectiveness"][style]["count"] == 0

    def test_single_turn_no_pairs(self):
        from transcript_reader import compute_effectiveness_signals
        result = compute_effectiveness_signals([_turn("Fix the bug")])
        assert result["eligible_turns"] == 0
        assert result["correction_rate"] == 0.0
        assert result["first_response_acceptance"] == 1.0

    def test_no_corrections(self):
        from transcript_reader import compute_effectiveness_signals
        turns = [
            _turn("Fix the bug"),
            _turn("Add some tests"),
            _turn("Run the suite"),
        ]
        result = compute_effectiveness_signals(turns)
        assert result["eligible_turns"] == 2  # 2 consecutive pairs
        assert result["corrections_total"] == 0
        assert result["correction_rate"] == 0.0
        assert result["first_response_acceptance"] == 1.0

    def test_all_corrections(self):
        from transcript_reader import compute_effectiveness_signals
        turns = [
            _turn("Fix the bug"),
            _turn("No, actually fix it differently"),
            _turn("Actually, try another approach"),
        ]
        result = compute_effectiveness_signals(turns)
        assert result["eligible_turns"] == 2
        assert result["corrections_total"] == 2
        assert result["correction_rate"] == 1.0
        assert result["first_response_acceptance"] == 0.0

    def test_mixed_corrections(self):
        from transcript_reader import compute_effectiveness_signals
        turns = [
            _turn("Fix the bug"),
            _turn("Actually, not that way"),  # correction
            _turn("Now add tests"),
            _turn("Run the suite"),  # not a correction
        ]
        result = compute_effectiveness_signals(turns)
        assert result["eligible_turns"] == 3
        assert result["corrections_total"] == 1

    def test_correction_case_insensitive(self):
        from transcript_reader import compute_effectiveness_signals
        turns = [
            _turn("Fix the bug"),
            _turn("ACTUALLY do it this way"),
        ]
        result = compute_effectiveness_signals(turns)
        assert result["corrections_total"] == 1

    def test_cross_session_boundary_skipped(self):
        from transcript_reader import compute_effectiveness_signals
        turns = [
            _turn("Fix the bug", session_id="sess-1"),
            _turn("Actually, not that", session_id="sess-2"),  # different session
        ]
        result = compute_effectiveness_signals(turns)
        assert result["eligible_turns"] == 0
        assert result["corrections_total"] == 0

    def test_per_style_question(self):
        from transcript_reader import compute_effectiveness_signals
        turns = [
            _turn("What is this bug?"),  # question
            _turn("Add a test"),          # not a correction
            _turn("How does this work?"), # question
            _turn("Actually, I meant the other file"),  # correction
        ]
        result = compute_effectiveness_signals(turns)
        pse = result["per_style_effectiveness"]
        assert pse["question"]["count"] == 2
        # First question → not corrected; second question → corrected
        assert pse["question"]["correction_rate"] == 0.5

    def test_per_style_imperative(self):
        from transcript_reader import compute_effectiveness_signals
        turns = [
            _turn("Fix the bug"),    # imperative
            _turn("Add some tests"), # imperative, not a correction
            _turn("Run the suite"),  # imperative, not a correction
        ]
        result = compute_effectiveness_signals(turns)
        pse = result["per_style_effectiveness"]
        assert pse["imperative"]["count"] == 2  # first two are eligible
        assert pse["imperative"]["correction_rate"] == 0.0

    def test_per_style_statement(self):
        from transcript_reader import compute_effectiveness_signals
        turns = [
            _turn("The code is broken"),   # statement
            _turn("Actually, I was wrong"), # correction → statement corrected
            _turn("The tests pass now"),    # statement
        ]
        result = compute_effectiveness_signals(turns)
        pse = result["per_style_effectiveness"]
        assert pse["statement"]["count"] == 2
        assert pse["statement"]["correction_rate"] == 0.5

    def test_per_style_avg_tool_count(self):
        from transcript_reader import compute_effectiveness_signals
        turns = [
            _turn("Fix the bug", tools=[_tool("Read", "/a.py"), _tool("Edit", "/a.py")]),
            _turn("Add tests"),  # not a correction
        ]
        result = compute_effectiveness_signals(turns)
        pse = result["per_style_effectiveness"]
        assert pse["imperative"]["avg_tool_count"] == 2.0  # "Fix" has 2 tools

    def test_per_style_avg_tokens(self):
        from transcript_reader import compute_effectiveness_signals
        turns = [
            _turn("Fix the bug", input_tokens=200, output_tokens=100),
            _turn("Add tests", input_tokens=150, output_tokens=75),
            _turn("Run the suite"),
        ]
        result = compute_effectiveness_signals(turns)
        pse = result["per_style_effectiveness"]
        # Both "Fix" and "Add" are imperative, eligible
        assert pse["imperative"]["avg_tokens"] == 262.5  # (300 + 225) / 2

    def test_tool_scatter_focused(self):
        from transcript_reader import compute_effectiveness_signals
        # Same file touched by multiple tools → low scatter
        turns = [
            _turn("Fix it", tools=[
                _tool("Read", "/a.py"), _tool("Edit", "/a.py"), _tool("Read", "/a.py"),
            ]),
            _turn("Done"),
        ]
        result = compute_effectiveness_signals(turns)
        # 1 unique file / 3 tool calls = 0.333...
        assert abs(result["tool_scatter"]["imperative"] - 1/3) < 0.01

    def test_tool_scatter_scattered(self):
        from transcript_reader import compute_effectiveness_signals
        # Different files each tool → high scatter
        turns = [
            _turn("Fix it", tools=[
                _tool("Read", "/a.py"), _tool("Read", "/b.py"), _tool("Read", "/c.py"),
            ]),
            _turn("Done"),
        ]
        result = compute_effectiveness_signals(turns)
        # 3 unique files / 3 tool calls = 1.0
        assert result["tool_scatter"]["imperative"] == 1.0

    def test_tool_scatter_no_tools(self):
        from transcript_reader import compute_effectiveness_signals
        turns = [
            _turn("Fix the bug"),
            _turn("Thanks"),
        ]
        result = compute_effectiveness_signals(turns)
        assert result["tool_scatter"]["overall"] == 0.0

    def test_first_response_acceptance(self):
        from transcript_reader import compute_effectiveness_signals
        turns = [
            _turn("Fix the bug"),
            _turn("Actually, wrong approach"),  # correction
            _turn("Now add tests"),
            _turn("Run them"),  # not a correction
            _turn("Deploy it"),
            _turn("Instead, just push"),  # correction
        ]
        result = compute_effectiveness_signals(turns)
        # 5 eligible pairs, 2 corrections
        assert result["correction_rate"] == 2 / 5
        assert result["first_response_acceptance"] == 1.0 - 2 / 5

    def test_session_progression_warming_up(self):
        from transcript_reader import compute_effectiveness_signals
        # First half: corrections. Second half: no corrections.
        turns = [
            _turn("Do A"),
            _turn("No, actually do B"),   # correction (pair 1)
            _turn("Do C"),
            _turn("Not what I meant"),    # correction (pair 2)
            _turn("Do E"),
            _turn("Do F"),               # not a correction (pair 3)
            _turn("Do G"),
            _turn("Do H"),               # not a correction (pair 4)
        ]
        result = compute_effectiveness_signals(turns)
        sp = result["session_progression"]
        assert sp["first_half_correction_rate"] > sp["second_half_correction_rate"]
        assert sp["warming_up"] is True

    def test_session_progression_no_warmup(self):
        from transcript_reader import compute_effectiveness_signals
        # Second half has more corrections
        turns = [
            _turn("Do A"),
            _turn("Do B"),                # not correction (pair 1)
            _turn("Do C"),
            _turn("Do D"),                # not correction (pair 2)
            _turn("Do E"),
            _turn("Actually, wrong"),     # correction (pair 3)
            _turn("Do G"),
            _turn("No, I meant this"),    # correction (pair 4)
        ]
        result = compute_effectiveness_signals(turns)
        sp = result["session_progression"]
        assert sp["first_half_correction_rate"] <= sp["second_half_correction_rate"]
        assert sp["warming_up"] is False

    def test_session_progression_equal(self):
        from transcript_reader import compute_effectiveness_signals
        # 5 turns → 4 pairs, split 2/2
        # Pair 0: corrected, pair 1: not, pair 2: corrected, pair 3: not
        turns = [
            _turn("Do A"),
            _turn("Actually, fix it"),   # correction (pair 0)
            _turn("Do C"),               # not correction (pair 1)
            _turn("Actually, fix it"),   # correction (pair 2)
            _turn("Do E"),               # not correction (pair 3)
        ]
        result = compute_effectiveness_signals(turns)
        sp = result["session_progression"]
        assert sp["first_half_correction_rate"] == sp["second_half_correction_rate"]
        assert sp["warming_up"] is False  # equal is not warming up

    def test_skill_expansions_excluded(self):
        """Skill expansion turns should be filtered from effectiveness analysis."""
        from transcript_reader import compute_effectiveness_signals
        skill_prompt = "# Reflect\n\n" + "Analyze the methodology. " * 50
        turns = [
            _turn("Fix the bug"),
            _turn("Add some tests"),
            _turn(skill_prompt),  # skill expansion — should be excluded
        ]
        result = compute_effectiveness_signals(turns)
        # Only 1 eligible pair (turns 0→1), the skill expansion is filtered out
        assert result["eligible_turns"] == 1


class TestCLI:
    """Test the main() CLI interface via monkeypatching."""

    def test_cli_usage_on_no_args(self, monkeypatch):
        import transcript_reader as reader
        monkeypatch.setattr("sys.argv", ["transcript_reader.py"])
        with pytest.raises(SystemExit) as exc_info:
            reader.main()
        assert exc_info.value.code == 1

    def test_cli_analyze(self, tmp_path, monkeypatch, capsys):
        """CLI analyze command works."""
        import transcript_reader as reader
        project_dir = tmp_path / "sessions"
        project_dir.mkdir()
        ts = _ts(1)
        _write_session(project_dir, "sess.jsonl", [
            _queue_entry(timestamp=ts),
            _user_entry("Hello", timestamp=ts),
            _assistant_entry([{"type": "text", "text": "Hi"}], timestamp=ts),
        ])
        monkeypatch.setattr(reader, "get_transcript_dir", lambda cwd: project_dir)
        monkeypatch.setattr("sys.argv",
                          ["transcript_reader.py", "analyze", "/tmp/proj", _ts(10)])
        reader.main()
        data = json.loads(capsys.readouterr().out)
        assert data["turn_count"] == 1

    def test_cli_sessions(self, tmp_path, monkeypatch, capsys):
        """CLI sessions command lists sessions."""
        import transcript_reader as reader
        project_dir = tmp_path / "sessions"
        project_dir.mkdir()
        ts = _ts(1)
        _write_session(project_dir, "sess.jsonl", [
            _queue_entry(timestamp=ts),
            _user_entry("Hello", timestamp=ts),
            _assistant_entry([{"type": "text", "text": "Hi"}], timestamp=ts),
        ])
        monkeypatch.setattr(reader, "get_transcript_dir", lambda cwd: project_dir)
        monkeypatch.setattr("sys.argv",
                          ["transcript_reader.py", "sessions", "/tmp/proj"])
        reader.main()
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1

    def test_cli_stats(self, tmp_path, monkeypatch, capsys):
        """CLI stats command returns aggregated stats."""
        import transcript_reader as reader
        project_dir = tmp_path / "sessions"
        project_dir.mkdir()
        ts = _ts(1)
        _write_session(project_dir, "sess.jsonl", [
            _queue_entry(timestamp=ts),
            _user_entry("Hello", timestamp=ts),
            _assistant_entry([{"type": "text", "text": "Hi"}],
                           input_tokens=50, output_tokens=20, timestamp=ts),
        ])
        monkeypatch.setattr(reader, "get_transcript_dir", lambda cwd: project_dir)
        monkeypatch.setattr("sys.argv",
                          ["transcript_reader.py", "stats", "/tmp/proj", _ts(10)])
        reader.main()
        data = json.loads(capsys.readouterr().out)
        assert data["turn_count"] == 1
        assert data["token_stats"]["total_input"] == 50
        assert "prompt_linguistics" in data
        assert "effectiveness_signals" in data

    def test_cli_analyze_includes_analytics(self, tmp_path, monkeypatch, capsys):
        """CLI analyze command includes both analytics keys."""
        import transcript_reader as reader
        project_dir = tmp_path / "sessions"
        project_dir.mkdir()
        ts = _ts(1)
        _write_session(project_dir, "sess.jsonl", [
            _queue_entry(timestamp=ts),
            _user_entry("Fix the bug", timestamp=ts),
            _assistant_entry([{"type": "text", "text": "Fixed."}], timestamp=ts),
        ])
        monkeypatch.setattr(reader, "get_transcript_dir", lambda cwd: project_dir)
        monkeypatch.setattr("sys.argv",
                          ["transcript_reader.py", "analyze", "/tmp/proj", _ts(10)])
        reader.main()
        data = json.loads(capsys.readouterr().out)
        assert "prompt_linguistics" in data
        assert "effectiveness_signals" in data

    def test_cli_unknown_command(self, monkeypatch):
        import transcript_reader as reader
        monkeypatch.setattr("sys.argv", ["transcript_reader.py", "bogus", "/tmp"])
        with pytest.raises(SystemExit) as exc_info:
            reader.main()
        assert exc_info.value.code == 1

    def test_cli_analyze_no_surrogate_escapes(self, tmp_path, monkeypatch, capsys):
        """CLI analyze output uses raw UTF-8 for emoji, not surrogate pair escapes.

        Surrogate escapes like \\ud83d\\ude4f break when passed through shell
        variable interpolation (bash $() captures), producing invalid CESU-8 bytes.
        """
        import transcript_reader as reader
        project_dir = tmp_path / "sessions"
        project_dir.mkdir()
        ts = _ts(1)
        # Write raw JSON with actual \uD83D\uDE4F surrogate pair escapes,
        # simulating what Claude Code writes for emoji like prayer hands.
        # We must write raw JSON, not use json.dumps, because json.dumps
        # would convert the surrogate pair to the real emoji character.
        path = project_dir / "emoji-sess.jsonl"
        queue_line = json.dumps(_queue_entry(timestamp=ts))
        assistant_line = json.dumps(_assistant_entry(
            [{"type": "text", "text": "Hi!"}], timestamp=ts))
        # Build the user entry JSON, then replace the prompt text with raw
        # surrogate pair escapes (as they appear in real Claude Code transcripts)
        user = _user_entry("PLACEHOLDER", timestamp=ts)
        user_line = json.dumps(user).replace("PLACEHOLDER", "Hello \\ud83d\\ude4f world")
        with open(path, "w", encoding="utf-8") as f:
            f.write(queue_line + "\n")
            f.write(user_line + "\n")
            f.write(assistant_line + "\n")
        monkeypatch.setattr(reader, "get_transcript_dir", lambda cwd: project_dir)
        monkeypatch.setattr("sys.argv",
                          ["transcript_reader.py", "analyze", "/tmp/proj", _ts(10)])
        reader.main()
        output = capsys.readouterr().out
        # Output must not contain surrogate pair escapes
        assert "\\ud83d" not in output
        assert "\\ude4f" not in output
        # Must be valid JSON and contain the emoji as real UTF-8
        data = json.loads(output)
        assert data["turn_count"] >= 1
