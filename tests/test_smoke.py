"""Smoke test to verify test infrastructure works."""

import reflection_db as db


def test_db_initializes(isolated_db):
    """DB initializes without error and tables exist."""
    conn = db.get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = [t[0] for t in tables]
    conn.close()

    assert "breakpoints" in table_names
    assert "prompts" in table_names
    assert "responses" in table_names
    assert "tool_usage" in table_names
    assert "recording_state" in table_names


def test_fixtures_isolated(project, seeded_project, conn):
    """Seeded project has recording enabled and a breakpoint."""
    row = conn.execute(
        "SELECT enabled FROM recording_state WHERE project = ?", (project,)
    ).fetchone()
    assert row is not None
    assert row[0] == 1

    bp = db.get_current_breakpoint(conn, project)
    assert bp is not None
