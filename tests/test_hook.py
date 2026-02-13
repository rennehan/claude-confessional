"""Tests for the slimmed confessional_hook — SessionStart only, no recording.

Covers:
- get_project_name
- handle_session_start: auto-breakpoints, recording check, error handling
- install_hooks / uninstall_hooks: only SessionStart, no Stop
"""

import json
import logging
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

import confessional_store as store


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Redirect store to temp directory."""
    monkeypatch.setattr(store, "STORE_DIR", tmp_path)
    monkeypatch.setattr(store, "CONFIG_PATH", tmp_path / "config.json")
    return tmp_path


@pytest.fixture
def project():
    return "test-project"


@pytest.fixture
def recording_project(project):
    """A project with recording enabled and a breakpoint."""
    store.enable_recording(project)
    store.add_breakpoint(project, "Initial breakpoint")
    return project


@pytest.fixture
def reset_logger():
    """Reset the confessional logger between tests."""
    yield
    logger = logging.getLogger("confessional")
    logger.handlers.clear()


class TestGetProjectName:

    def test_git_repo(self, tmp_path):
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        from confessional_hook import get_project_name
        result = get_project_name(str(tmp_path))
        assert result == tmp_path.name

    def test_non_git_dir(self, tmp_path):
        from confessional_hook import get_project_name
        result = get_project_name(str(tmp_path))
        assert result == tmp_path.name


class TestHandleSessionStart:

    def test_creates_auto_breakpoint_when_stale(self, recording_project, tmp_path,
                                                  monkeypatch):
        """Creates auto-breakpoint when last one is >4 hours old."""
        import confessional_hook
        monkeypatch.setattr(confessional_hook, "get_project_name",
                          lambda cwd: recording_project)
        from confessional_hook import handle_session_start

        # Make the existing breakpoint old
        bp_path = tmp_path / "projects" / recording_project / "breakpoints.jsonl"
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        bp_path.write_text(json.dumps({"id": 1, "timestamp": old_ts, "note": "old"}) + "\n")

        handle_session_start({"cwd": "/tmp/fake", "hook_event_name": "SessionStart"})

        bps = store.get_all_breakpoints(recording_project)
        assert len(bps) == 2
        assert "Auto-breakpoint" in bps[1]["note"]

    def test_skips_when_recent_breakpoint(self, recording_project, monkeypatch):
        """No auto-breakpoint when the last one is recent."""
        import confessional_hook
        monkeypatch.setattr(confessional_hook, "get_project_name",
                          lambda cwd: recording_project)
        from confessional_hook import handle_session_start

        handle_session_start({"cwd": "/tmp/fake", "hook_event_name": "SessionStart"})

        bps = store.get_all_breakpoints(recording_project)
        assert len(bps) == 1  # Only the initial one

    def test_skips_when_recording_disabled(self, project):
        """Does nothing if recording is not enabled."""
        from confessional_hook import handle_session_start

        handle_session_start({"cwd": "/tmp/fake", "hook_event_name": "SessionStart"})

        bps = store.get_all_breakpoints(project)
        assert len(bps) == 0

    def test_logs_errors_never_crashes(self, recording_project, tmp_path,
                                       monkeypatch, reset_logger):
        """Errors are logged but don't crash (exit 0 preserved)."""
        import confessional_hook
        monkeypatch.setattr(confessional_hook, "get_project_name",
                          lambda cwd: recording_project)
        from confessional_hook import handle_session_start, get_logger

        # Force LOG_PATH to tmp
        monkeypatch.setattr("confessional_hook.LOG_PATH", tmp_path / "hook.log")

        # Make get_current_breakpoint raise
        monkeypatch.setattr(store, "get_current_breakpoint",
                          lambda p: (_ for _ in ()).throw(RuntimeError("boom")))

        # Should not raise
        get_logger()
        handle_session_start({"cwd": "/tmp/fake", "hook_event_name": "SessionStart"})

        log_content = (tmp_path / "hook.log").read_text()
        assert "boom" in log_content


class TestInstallHooks:

    def test_installs_only_session_start(self, tmp_path, monkeypatch):
        """install_hooks only registers SessionStart, not Stop."""
        from confessional_hook import install_hooks

        settings_path = tmp_path / "settings.json"
        settings_path.write_text("{}")
        monkeypatch.setattr("confessional_hook.Path.home", lambda: tmp_path.parent)

        # Monkeypatch the settings path directly
        import confessional_hook
        monkeypatch.setattr(confessional_hook, "_settings_path",
                          lambda: settings_path)

        install_hooks()

        settings = json.loads(settings_path.read_text())
        assert "SessionStart" in settings.get("hooks", {})
        assert "Stop" not in settings.get("hooks", {})

    def test_uninstall_removes_hooks(self, tmp_path, monkeypatch):
        """uninstall_hooks removes the SessionStart hook."""
        from confessional_hook import install_hooks, uninstall_hooks
        import confessional_hook

        settings_path = tmp_path / "settings.json"
        settings_path.write_text("{}")
        monkeypatch.setattr(confessional_hook, "_settings_path",
                          lambda: settings_path)

        install_hooks()
        uninstall_hooks()

        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {})
        # Should be empty or have no confessional entries
        for event_hooks in hooks.values():
            for group in event_hooks:
                for h in group.get("hooks", []):
                    assert "confessional_hook" not in h.get("command", "")
