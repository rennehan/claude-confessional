"""Smoke tests to verify test infrastructure and basic module imports."""

import confessional_store as store
import transcript_reader as reader
import confessional_hook as hook
import dashboard_generator as dashboard


def test_store_imports():
    """confessional_store module imports and has key functions."""
    assert callable(store.add_breakpoint)
    assert callable(store.store_reflection)
    assert callable(store.is_recording)


def test_reader_imports():
    """transcript_reader module imports and has key functions."""
    assert callable(reader.get_transcript_dir)
    assert callable(reader.find_sessions)
    assert callable(reader.parse_session)
    assert callable(reader.get_turns_since)
    assert callable(reader.compute_prompt_linguistics)
    assert callable(reader.compute_effectiveness_signals)


def test_hook_imports():
    """confessional_hook module imports and has key functions."""
    assert callable(hook.handle_session_start)
    assert callable(hook.get_project_name)


def test_dashboard_imports():
    """dashboard_generator module imports and has key functions."""
    assert callable(dashboard.generate_session_html)
    assert callable(dashboard.generate_index_html)
    assert callable(dashboard.write_session_dashboard)
    assert callable(dashboard.write_index_dashboard)
