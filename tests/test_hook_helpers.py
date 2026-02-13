"""Tests for confessional_hook helper functions.

Covers:
- _summarize_tool_input for all tool types
- _extract_files for all tool types
- get_project_name
- is_recording_enabled
"""

from unittest.mock import patch, MagicMock
from confessional_hook import (
    _summarize_tool_input, _extract_files, get_project_name, is_recording_enabled
)
import reflection_db as db


class TestSummarizeToolInput:

    def test_bash(self):
        assert _summarize_tool_input("Bash", {"command": "ls -la"}) == "ls -la"

    def test_bash_truncates(self):
        long_cmd = "x" * 300
        result = _summarize_tool_input("Bash", {"command": long_cmd})
        assert len(result) == 200

    def test_read(self):
        assert _summarize_tool_input("Read", {"file_path": "/tmp/x.py"}) == "/tmp/x.py"

    def test_write(self):
        assert _summarize_tool_input("Write", {"file_path": "/tmp/y.py"}) == "/tmp/y.py"

    def test_edit(self):
        assert _summarize_tool_input("Edit", {"file_path": "/tmp/z.py"}) == "/tmp/z.py"

    def test_grep(self):
        assert _summarize_tool_input("Grep", {"pattern": "TODO"}) == "pattern=TODO"

    def test_glob(self):
        assert _summarize_tool_input("Glob", {"pattern": "*.py"}) == "pattern=*.py"

    def test_websearch(self):
        assert _summarize_tool_input("WebSearch", {"query": "python sqlite"}) == "python sqlite"

    def test_webfetch(self):
        assert _summarize_tool_input("WebFetch", {"url": "https://example.com"}) == "https://example.com"

    def test_task(self):
        result = _summarize_tool_input("Task", {"prompt": "explore codebase"})
        assert result == "explore codebase"

    def test_task_truncates(self):
        long_prompt = "x" * 300
        result = _summarize_tool_input("Task", {"prompt": long_prompt})
        assert len(result) == 200

    def test_unknown_tool(self):
        result = _summarize_tool_input("CustomTool", {"foo": "bar"})
        assert "foo" in result


class TestExtractFiles:

    def test_read(self):
        assert _extract_files("Read", {"file_path": "/a.py"}) == "/a.py"

    def test_write(self):
        assert _extract_files("Write", {"file_path": "/b.py"}) == "/b.py"

    def test_edit(self):
        assert _extract_files("Edit", {"file_path": "/c.py"}) == "/c.py"

    def test_glob(self):
        assert _extract_files("Glob", {"path": "/src"}) == "/src"

    def test_grep(self):
        assert _extract_files("Grep", {"path": "/lib"}) == "/lib"

    def test_unknown(self):
        assert _extract_files("Bash", {"command": "ls"}) == ""


class TestGetProjectName:

    def test_git_repo(self, tmp_path):
        """In a git repo, returns the repo basename."""
        import subprocess
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        result = get_project_name(str(tmp_path))
        assert result == tmp_path.name

    def test_non_git_dir(self, tmp_path):
        """Outside a git repo, falls back to directory basename."""
        result = get_project_name(str(tmp_path))
        assert result == tmp_path.name


class TestIsRecordingEnabled:

    def test_enabled(self, seeded_project):
        assert is_recording_enabled(seeded_project) is True

    def test_disabled(self, project):
        assert is_recording_enabled(project) is False

    def test_no_table(self, monkeypatch):
        """If recording_state table doesn't exist, returns False."""
        import confessional_hook
        # Mock get_connection to return a DB without the table
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        monkeypatch.setattr(confessional_hook.db, "get_connection", lambda: mock_conn)
        assert is_recording_enabled("nonexistent") is False
