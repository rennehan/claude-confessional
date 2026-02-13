"""Tests for auto-breakpoints on session start.

Covers:
- Stale breakpoint detection (>4 hours old)
- Auto-breakpoint created when stale
- No auto-breakpoint when breakpoint is recent
- Auto-breakpoint note identifies it as automatic
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import reflection_db as db
from confessional_hook import handle_session_start


class TestAutoBreakpoints:

    def _make_input(self, tmp_path):
        return {"cwd": str(tmp_path)}

    def test_stale_breakpoint_triggers_auto(self, tmp_path, seeded_project, conn, monkeypatch):
        """A breakpoint older than 4 hours should trigger an auto-breakpoint."""
        import confessional_hook
        monkeypatch.setattr(confessional_hook, "LOG_PATH", tmp_path / "hook.log")

        # Manually set the breakpoint timestamp to 5 hours ago
        five_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        conn.execute(
            "UPDATE breakpoints SET timestamp = ? WHERE project = ?",
            (five_hours_ago, seeded_project)
        )
        conn.commit()

        bp_count_before = conn.execute(
            "SELECT COUNT(*) FROM breakpoints WHERE project = ?", (seeded_project,)
        ).fetchone()[0]

        with patch.object(confessional_hook, "get_project_name", return_value=seeded_project), \
             patch.object(confessional_hook, "is_recording_enabled", return_value=True):
            handle_session_start(self._make_input(tmp_path))

        bp_count_after = conn.execute(
            "SELECT COUNT(*) FROM breakpoints WHERE project = ?", (seeded_project,)
        ).fetchone()[0]
        assert bp_count_after == bp_count_before + 1

        # Check the note
        latest_bp = db.get_current_breakpoint(conn, seeded_project)
        assert "Auto-breakpoint" in latest_bp["note"]

    def test_recent_breakpoint_no_auto(self, tmp_path, seeded_project, conn, monkeypatch):
        """A breakpoint less than 4 hours old should NOT trigger auto-breakpoint."""
        import confessional_hook
        monkeypatch.setattr(confessional_hook, "LOG_PATH", tmp_path / "hook.log")

        # Default breakpoint was just created (seconds ago)
        bp_count_before = conn.execute(
            "SELECT COUNT(*) FROM breakpoints WHERE project = ?", (seeded_project,)
        ).fetchone()[0]

        with patch.object(confessional_hook, "get_project_name", return_value=seeded_project), \
             patch.object(confessional_hook, "is_recording_enabled", return_value=True):
            handle_session_start(self._make_input(tmp_path))

        bp_count_after = conn.execute(
            "SELECT COUNT(*) FROM breakpoints WHERE project = ?", (seeded_project,)
        ).fetchone()[0]
        # Only the session_context init may create a breakpoint, but not an auto one
        # The existing breakpoint is recent, so no auto-breakpoint added
        latest_bp = db.get_current_breakpoint(conn, seeded_project)
        assert "Auto-breakpoint" not in (latest_bp.get("note") or "")

    def test_no_breakpoint_no_crash(self, tmp_path, project, conn, monkeypatch):
        """If there are no breakpoints at all, should not crash."""
        import confessional_hook
        monkeypatch.setattr(confessional_hook, "LOG_PATH", tmp_path / "hook.log")

        # Enable recording but don't create a breakpoint (unusual state)
        db.cmd_enable_recording(project)

        with patch.object(confessional_hook, "get_project_name", return_value=project), \
             patch.object(confessional_hook, "is_recording_enabled", return_value=True):
            # Should not crash
            handle_session_start(self._make_input(tmp_path))

    def test_just_under_4_hours_not_stale(self, tmp_path, seeded_project, conn, monkeypatch):
        """Breakpoint under 4 hours old should NOT trigger."""
        import confessional_hook
        monkeypatch.setattr(confessional_hook, "LOG_PATH", tmp_path / "hook.log")

        four_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=3, minutes=59)).isoformat()
        conn.execute(
            "UPDATE breakpoints SET timestamp = ? WHERE project = ?",
            (four_hours_ago, seeded_project)
        )
        conn.commit()

        bp_count_before = conn.execute(
            "SELECT COUNT(*) FROM breakpoints WHERE project = ?", (seeded_project,)
        ).fetchone()[0]

        with patch.object(confessional_hook, "get_project_name", return_value=seeded_project), \
             patch.object(confessional_hook, "is_recording_enabled", return_value=True):
            handle_session_start(self._make_input(tmp_path))

        bp_count_after = conn.execute(
            "SELECT COUNT(*) FROM breakpoints WHERE project = ?", (seeded_project,)
        ).fetchone()[0]
        # Boundary: exactly 4 hours is NOT stale
        assert bp_count_after == bp_count_before
