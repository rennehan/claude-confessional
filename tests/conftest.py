"""Shared fixtures for claude-confessional tests."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def project():
    """Default test project name."""
    return "test-project"


def write_jsonl(path: Path, entries: list[dict]) -> Path:
    """Write a list of dicts as JSONL and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return path
