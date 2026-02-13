"""Tests for transcript_reader — reads Claude Code's native JSONL transcripts.

Covers:
- get_transcript_dir: path resolution
- find_sessions: session discovery and filtering
- parse_session: turn extraction, metrics, edge cases
- get_turns_since: windowed analysis across sessions
"""

import json
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
