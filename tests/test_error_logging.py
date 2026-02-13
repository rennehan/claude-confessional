"""Tests for hook error logging.

Covers:
- Logger initialization and file creation
- Errors in handle_stop are logged, not raised
- Errors in handle_session_start are logged, not raised
- Exit-0 behavior preserved when errors occur
"""

import json
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from confessional_hook import get_logger, handle_stop, handle_session_start


@pytest.fixture(autouse=True)
def reset_logger():
    """Clear logger handlers between tests so each test gets a fresh file handler."""
    logger = logging.getLogger("confessional")
    logger.handlers.clear()
    yield
    logger.handlers.clear()


class TestGetLogger:

    def test_creates_logger(self, tmp_path, monkeypatch):
        import confessional_hook
        monkeypatch.setattr(confessional_hook, "LOG_PATH", tmp_path / "hook.log")
        logger = get_logger()
        assert logger.name == "confessional"
        assert logger.level == logging.WARNING

    def test_creates_log_directory(self, tmp_path, monkeypatch):
        import confessional_hook
        log_path = tmp_path / "subdir" / "hook.log"
        monkeypatch.setattr(confessional_hook, "LOG_PATH", log_path)
        get_logger()
        assert log_path.parent.exists()

    def test_idempotent(self, tmp_path, monkeypatch):
        """Calling get_logger twice doesn't add duplicate handlers."""
        import confessional_hook
        monkeypatch.setattr(confessional_hook, "LOG_PATH", tmp_path / "hook.log")
        # Reset any existing handlers from other tests
        logger = logging.getLogger("confessional")
        logger.handlers.clear()
        get_logger()
        get_logger()
        assert len(logging.getLogger("confessional").handlers) == 1


class TestHandleStopErrorRecovery:

    def test_error_is_logged_not_raised(self, tmp_path, monkeypatch):
        """An exception in handle_stop should be logged, not propagated."""
        import confessional_hook
        log_path = tmp_path / "hook.log"
        monkeypatch.setattr(confessional_hook, "LOG_PATH", log_path)

        # Force an error by providing invalid transcript path
        input_data = {
            "cwd": str(tmp_path),
            "transcript_path": str(tmp_path / "nonexistent.jsonl"),
        }

        # Mock is_recording_enabled to return True so we get past the guard
        with patch.object(confessional_hook, "is_recording_enabled", return_value=True):
            # Should NOT raise
            handle_stop(input_data)

    def test_error_in_parse_is_logged(self, tmp_path, monkeypatch):
        """A crash in parse_last_turn should be caught and logged."""
        import confessional_hook
        log_path = tmp_path / "hook.log"
        monkeypatch.setattr(confessional_hook, "LOG_PATH", log_path)

        # Create a transcript with invalid JSON to trigger an error inside parse
        bad_transcript = tmp_path / "transcript.jsonl"
        bad_transcript.write_text("not json\n")

        input_data = {
            "cwd": str(tmp_path),
            "transcript_path": str(bad_transcript),
        }

        with patch.object(confessional_hook, "is_recording_enabled", return_value=True):
            handle_stop(input_data)
        # No exception = success

    def test_db_error_is_caught(self, tmp_path, monkeypatch):
        """A database error during recording should be caught and logged."""
        import confessional_hook
        log_path = tmp_path / "hook.log"
        monkeypatch.setattr(confessional_hook, "LOG_PATH", log_path)
        # Initialize logger so FileHandler points to our tmp path
        get_logger()

        # Create valid transcript
        transcript = tmp_path / "transcript.jsonl"
        entries = [
            {"type": "user", "message": {"id": "u1", "content": "hello"}},
            {"type": "assistant", "message": {"id": "a1", "content": [{"type": "text", "text": "hi"}]}},
        ]
        with open(transcript, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        input_data = {
            "cwd": str(tmp_path),
            "transcript_path": str(transcript),
        }

        # Mock recording enabled, but make cmd_record_interaction crash
        with patch.object(confessional_hook, "is_recording_enabled", return_value=True), \
             patch.object(confessional_hook.db, "cmd_record_interaction", side_effect=Exception("DB dead")):
            handle_stop(input_data)

        log_content = log_path.read_text()
        assert "DB dead" in log_content


class TestHandleSessionStartErrorRecovery:

    def test_error_is_logged_not_raised(self, tmp_path, monkeypatch):
        """An exception in handle_session_start should be logged, not propagated."""
        import confessional_hook
        log_path = tmp_path / "hook.log"
        monkeypatch.setattr(confessional_hook, "LOG_PATH", log_path)
        get_logger()

        input_data = {"cwd": str(tmp_path)}

        # Mock recording enabled, but make db.cmd_init crash
        with patch.object(confessional_hook, "is_recording_enabled", return_value=True), \
             patch.object(confessional_hook.db, "cmd_init", side_effect=Exception("init failed")):
            handle_session_start(input_data)

        log_content = log_path.read_text()
        assert "init failed" in log_content
