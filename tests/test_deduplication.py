"""Tests for deduplication via transcript offset.

Covers:
- parse_last_turn returns transcript_offset (line index of user prompt)
- transcript_offset column exists in prompts table
- handle_stop skips recording when offset already recorded
- Different offsets are recorded normally
"""

import json
from unittest.mock import patch

import reflection_db as db
from confessional_hook import parse_last_turn, handle_stop, is_recording_enabled
from tests.conftest import make_transcript, make_user_entry, make_assistant_entry


class TestParseLastTurnOffset:

    def test_returns_transcript_offset(self, tmp_path):
        """parse_last_turn should return the line index of the user prompt."""
        transcript = make_transcript(tmp_path, [
            make_user_entry("first"),
            make_assistant_entry([{"type": "text", "text": "r1"}]),
            make_user_entry("second"),
            make_assistant_entry([{"type": "text", "text": "r2"}]),
        ])
        result = parse_last_turn(transcript)
        assert "transcript_offset" in result
        # "second" is at line index 2 (0-indexed)
        assert result["transcript_offset"] == 2

    def test_offset_for_single_turn(self, tmp_path):
        transcript = make_transcript(tmp_path, [
            make_user_entry("only prompt"),
            make_assistant_entry([{"type": "text", "text": "resp"}]),
        ])
        result = parse_last_turn(transcript)
        assert result["transcript_offset"] == 0


class TestPromptsTableOffset:

    def test_column_exists(self, conn):
        """prompts table should have transcript_offset column."""
        cursor = conn.execute("PRAGMA table_info(prompts)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "transcript_offset" in columns


class TestHandleStopDeduplication:

    def _make_input(self, tmp_path, transcript_path):
        return {
            "cwd": str(tmp_path),
            "transcript_path": transcript_path,
        }

    def test_first_recording_works(self, tmp_path, seeded_project, conn, monkeypatch):
        """First time seeing an offset should record normally."""
        import confessional_hook
        monkeypatch.setattr(confessional_hook, "LOG_PATH", tmp_path / "hook.log")

        transcript = make_transcript(tmp_path, [
            make_user_entry("hello"),
            make_assistant_entry([{"type": "text", "text": "hi"}]),
        ])

        with patch.object(confessional_hook, "get_project_name", return_value=seeded_project), \
             patch.object(confessional_hook, "is_recording_enabled", return_value=True):
            handle_stop(self._make_input(tmp_path, transcript))

        count = conn.execute("SELECT COUNT(*) FROM prompts WHERE project = ?", (seeded_project,)).fetchone()[0]
        assert count == 1

    def test_duplicate_offset_skipped(self, tmp_path, seeded_project, conn, monkeypatch):
        """Same transcript offset should not be recorded twice."""
        import confessional_hook
        monkeypatch.setattr(confessional_hook, "LOG_PATH", tmp_path / "hook.log")

        transcript = make_transcript(tmp_path, [
            make_user_entry("hello"),
            make_assistant_entry([{"type": "text", "text": "hi"}]),
        ])

        with patch.object(confessional_hook, "get_project_name", return_value=seeded_project), \
             patch.object(confessional_hook, "is_recording_enabled", return_value=True):
            handle_stop(self._make_input(tmp_path, transcript))
            handle_stop(self._make_input(tmp_path, transcript))

        count = conn.execute("SELECT COUNT(*) FROM prompts WHERE project = ?", (seeded_project,)).fetchone()[0]
        assert count == 1

    def test_different_offsets_both_recorded(self, tmp_path, seeded_project, conn, monkeypatch):
        """Different offsets should both be recorded."""
        import confessional_hook
        monkeypatch.setattr(confessional_hook, "LOG_PATH", tmp_path / "hook.log")

        # First transcript: one turn
        transcript1 = make_transcript(tmp_path, [
            make_user_entry("hello"),
            make_assistant_entry([{"type": "text", "text": "hi"}]),
        ])

        with patch.object(confessional_hook, "get_project_name", return_value=seeded_project), \
             patch.object(confessional_hook, "is_recording_enabled", return_value=True):
            handle_stop(self._make_input(tmp_path, transcript1))

        # Second transcript: two turns (different offset for second prompt)
        transcript2_path = tmp_path / "transcript2.jsonl"
        entries = [
            make_user_entry("hello"),
            make_assistant_entry([{"type": "text", "text": "hi"}]),
            make_user_entry("another question"),
            make_assistant_entry([{"type": "text", "text": "another answer"}]),
        ]
        with open(transcript2_path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        with patch.object(confessional_hook, "get_project_name", return_value=seeded_project), \
             patch.object(confessional_hook, "is_recording_enabled", return_value=True):
            handle_stop(self._make_input(tmp_path, str(transcript2_path)))

        count = conn.execute("SELECT COUNT(*) FROM prompts WHERE project = ?", (seeded_project,)).fetchone()[0]
        assert count == 2
