"""Tests for confessional_store — pure JSON/JSONL storage.

Covers:
- _read_jsonl / _append_jsonl: JSONL I/O helpers
- _read_config / _write_config: JSON config I/O
- Breakpoint operations: add, get current/previous, get all
- Reflection operations: store, get, get summary
- Recording state: enable, disable, is_recording
"""

import json
from pathlib import Path

import pytest

import confessional_store as store


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Redirect store to a temp directory for every test."""
    monkeypatch.setattr(store, "STORE_DIR", tmp_path)
    monkeypatch.setattr(store, "CONFIG_PATH", tmp_path / "config.json")
    return tmp_path


@pytest.fixture
def project():
    return "test-project"


# --- Tests: JSONL I/O ---

class TestReadJsonl:

    def test_missing_file(self, tmp_path):
        result = store._read_jsonl(tmp_path / "nonexistent.jsonl")
        assert result == []

    def test_parses_multi_line(self, tmp_path):
        path = tmp_path / "data.jsonl"
        path.write_text('{"a": 1}\n{"b": 2}\n{"c": 3}\n')
        result = store._read_jsonl(path)
        assert len(result) == 3
        assert result[0] == {"a": 1}
        assert result[2] == {"c": 3}

    def test_skips_blank_lines(self, tmp_path):
        path = tmp_path / "data.jsonl"
        path.write_text('{"a": 1}\n\n{"b": 2}\n')
        result = store._read_jsonl(path)
        assert len(result) == 2

    def test_skips_corrupt_lines(self, tmp_path):
        path = tmp_path / "data.jsonl"
        path.write_text('{"a": 1}\nnot json\n{"b": 2}\n')
        result = store._read_jsonl(path)
        assert len(result) == 2


class TestAppendJsonl:

    def test_creates_file_and_dirs(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "data.jsonl"
        store._append_jsonl(path, {"x": 1})
        assert path.exists()
        entries = store._read_jsonl(path)
        assert entries == [{"x": 1}]

    def test_appends_without_corrupting(self, tmp_path):
        path = tmp_path / "data.jsonl"
        store._append_jsonl(path, {"a": 1})
        store._append_jsonl(path, {"b": 2})
        store._append_jsonl(path, {"c": 3})
        entries = store._read_jsonl(path)
        assert len(entries) == 3
        assert entries[1] == {"b": 2}

    def test_each_entry_on_own_line(self, tmp_path):
        path = tmp_path / "data.jsonl"
        store._append_jsonl(path, {"x": 1})
        store._append_jsonl(path, {"y": 2})
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2


# --- Tests: Config I/O ---

class TestConfig:

    def test_read_missing_returns_empty(self):
        result = store._read_config()
        assert result == {}

    def test_write_and_read(self, tmp_path):
        config = {"projects": {"foo": {"enabled": True}}}
        store._write_config(config)
        result = store._read_config()
        assert result == config

    def test_atomic_write(self, tmp_path):
        """Config write doesn't corrupt on overwrite."""
        store._write_config({"a": 1})
        store._write_config({"b": 2})
        result = store._read_config()
        assert result == {"b": 2}


# --- Tests: Breakpoints ---

class TestBreakpoints:

    def test_add_breakpoint(self, project):
        bp = store.add_breakpoint(project, "First breakpoint")
        assert bp["id"] == 1
        assert bp["note"] == "First breakpoint"
        assert "timestamp" in bp

    def test_auto_incrementing_id(self, project):
        store.add_breakpoint(project, "one")
        bp2 = store.add_breakpoint(project, "two")
        bp3 = store.add_breakpoint(project, "three")
        assert bp2["id"] == 2
        assert bp3["id"] == 3

    def test_creates_project_dir(self, project, tmp_path):
        store.add_breakpoint(project, "test")
        project_dir = tmp_path / "projects" / project
        assert project_dir.exists()

    def test_get_current_breakpoint(self, project):
        store.add_breakpoint(project, "first")
        store.add_breakpoint(project, "second")
        store.add_breakpoint(project, "third")
        current = store.get_current_breakpoint(project)
        assert current["note"] == "third"
        assert current["id"] == 3

    def test_get_current_none_when_empty(self, project):
        assert store.get_current_breakpoint(project) is None

    def test_get_previous_breakpoint(self, project):
        store.add_breakpoint(project, "first")
        store.add_breakpoint(project, "second")
        store.add_breakpoint(project, "third")
        prev = store.get_previous_breakpoint(project)
        assert prev["note"] == "second"
        assert prev["id"] == 2

    def test_get_previous_none_with_one(self, project):
        store.add_breakpoint(project, "only one")
        assert store.get_previous_breakpoint(project) is None

    def test_get_previous_none_when_empty(self, project):
        assert store.get_previous_breakpoint(project) is None

    def test_get_all_breakpoints(self, project):
        store.add_breakpoint(project, "a")
        store.add_breakpoint(project, "b")
        all_bps = store.get_all_breakpoints(project)
        assert len(all_bps) == 2
        assert all_bps[0]["note"] == "a"
        assert all_bps[1]["note"] == "b"

    def test_get_all_empty(self, project):
        assert store.get_all_breakpoints(project) == []


# --- Tests: Reflections ---

class TestReflections:

    def test_store_reflection(self, project):
        store.add_breakpoint(project, "start")
        store.add_breakpoint(project, "end")
        ref = store.store_reflection(project, "You think in loops.", "3 commits", 15)
        assert ref["id"] == 1
        assert ref["reflection"] == "You think in loops."
        assert ref["git_summary"] == "3 commits"
        assert ref["prompt_count"] == 15
        assert "breakpoint_start" in ref
        assert "breakpoint_end" in ref

    def test_get_reflections(self, project):
        store.add_breakpoint(project, "bp")
        store.store_reflection(project, "First reflection")
        store.store_reflection(project, "Second reflection")
        refs = store.get_reflections(project)
        assert len(refs) == 2
        assert refs[0]["reflection"] == "First reflection"
        assert refs[1]["reflection"] == "Second reflection"

    def test_get_reflections_empty(self, project):
        assert store.get_reflections(project) == []

    def test_get_reflections_summary(self, project):
        store.add_breakpoint(project, "bp")
        store.store_reflection(project, "Deep analysis here", "5 commits", 20)
        summary = store.get_reflections_summary(project)
        assert len(summary) == 1
        assert summary[0]["prompt_count"] == 20
        assert "timestamp" in summary[0]


# --- Tests: Recording State ---

class TestRecordingState:

    def test_enable_creates_config(self, project):
        store.enable_recording(project)
        assert store.is_recording(project) is True

    def test_disable(self, project):
        store.enable_recording(project)
        store.disable_recording(project)
        assert store.is_recording(project) is False

    def test_is_recording_false_for_unknown(self, project):
        assert store.is_recording("unknown-project") is False

    def test_multiple_projects(self):
        store.enable_recording("project-a")
        store.enable_recording("project-b")
        store.disable_recording("project-a")
        assert store.is_recording("project-a") is False
        assert store.is_recording("project-b") is True

    def test_config_missing_returns_false(self, project):
        """No config.json at all → not recording."""
        assert store.is_recording(project) is False
