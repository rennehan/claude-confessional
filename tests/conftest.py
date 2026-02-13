"""Shared fixtures for claude-confessional tests."""

import json
import os
import tempfile
from pathlib import Path

import pytest

import reflection_db as db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Redirect reflection DB to a temp directory for every test."""
    monkeypatch.setattr(db, "DB_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "history.db")
    db.init_db()
    return tmp_path


@pytest.fixture
def project():
    """Default test project name."""
    return "test-project"


@pytest.fixture
def conn():
    """Get a fresh DB connection (uses the isolated_db automatically)."""
    c = db.get_connection()
    yield c
    c.close()


@pytest.fixture
def seeded_project(project, conn):
    """A project with recording enabled and a breakpoint ready."""
    db.cmd_init(project)
    db.cmd_enable_recording(project)
    return project


def make_transcript(tmp_path, entries):
    """Write a list of dicts as JSONL transcript and return the path."""
    path = tmp_path / "transcript.jsonl"
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return str(path)


def make_user_entry(content, msg_id="user-1"):
    """Create a transcript user entry."""
    return {
        "type": "user",
        "message": {"id": msg_id, "content": content},
    }


def make_assistant_entry(content_blocks, msg_id="asst-1"):
    """Create a transcript assistant entry.

    content_blocks: list of dicts like {"type": "text", "text": "..."} or
    {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}
    """
    return {
        "type": "assistant",
        "message": {"id": msg_id, "content": content_blocks},
    }
