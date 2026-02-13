"""Tests for dashboard_generator — HTML dashboard rendering.

Covers:
- HTML helper functions: bar chart, summary card, table, progress bar
- Session dashboard generation: sections, data rendering, validity
- Index dashboard generation: breakpoint listing, reflection linking
- File write functions: path format, creation, overwrite
- CLI interface
"""

import json
import sys

import pytest

import confessional_store as store
import dashboard_generator as dashboard


# --- Test data fixtures ---

def _make_analysis_data(**overrides):
    """Build a minimal but complete analysis data dict for testing."""
    data = {
        "turn_count": 10,
        "tool_stats": {
            "total": 25,
            "by_tool": {"Read": 10, "Bash": 8, "Edit": 5, "Grep": 2},
            "subagent_count": 0,
        },
        "token_stats": {
            "total_input": 50000,
            "total_output": 15000,
            "total_cache_read": 30000,
            "total_cache_creation": 5000,
        },
        "sessions": [
            {
                "session_id": "s1",
                "model": "claude-opus-4-6",
                "version": "2.1",
                "git_branch": "main",
                "turn_count": 10,
            }
        ],
        "prompt_linguistics": {
            "question_ratio": 0.3,
            "imperative_ratio": 0.5,
            "prompt_length": {
                "median": 12.0, "mean": 15.2, "min": 3, "max": 45,
                "stddev": 8.1, "count": 10,
            },
            "frequent_ngrams": {
                "bigrams": [
                    {"ngram": "add test", "count": 4},
                    {"ngram": "make sure", "count": 3},
                ],
                "trigrams": [
                    {"ngram": "add test for", "count": 2},
                ],
            },
            "certainty_markers": {
                "hedging_count": 5, "assertive_count": 12, "ratio": 2.4,
                "hedging_phrases": {"maybe": 2, "i think": 2, "perhaps": 1},
                "assertive_phrases": {"must": 3, "need to": 4, "should": 2,
                                      "have to": 1, "make sure": 1, "always": 1},
            },
            "agency_framing": {
                "i_count": 3, "we_count": 1, "you_count": 5,
                "lets_count": 2, "dominant": "you",
            },
            "prompt_length_by_position": {
                "first_quarter_avg": 18.0,
                "middle_half_avg": 14.0,
                "last_quarter_avg": 10.0,
            },
        },
        "effectiveness_signals": {
            "correction_rate": 0.15,
            "corrections_total": 3,
            "eligible_turns": 20,
            "per_style_effectiveness": {
                "question": {
                    "count": 6, "correction_rate": 0.1,
                    "avg_tool_count": 3.2, "avg_tokens": 1200.0,
                },
                "imperative": {
                    "count": 10, "correction_rate": 0.2,
                    "avg_tool_count": 5.1, "avg_tokens": 2000.0,
                },
                "statement": {
                    "count": 4, "correction_rate": 0.05,
                    "avg_tool_count": 2.0, "avg_tokens": 800.0,
                },
            },
            "tool_scatter": {
                "question": 0.4, "imperative": 0.6,
                "statement": 0.3, "overall": 0.45,
            },
            "first_response_acceptance": 0.85,
            "session_progression": {
                "first_half_correction_rate": 0.2,
                "second_half_correction_rate": 0.1,
                "warming_up": True,
            },
        },
    }
    data.update(overrides)
    return data


def _make_breakpoint(id=2, note="End of session"):
    return {
        "id": id,
        "timestamp": "2025-02-13T16:00:00+00:00",
        "note": note,
    }


def _make_reflection_meta(id=1):
    return {
        "id": id,
        "timestamp": "2025-02-13T16:05:00+00:00",
    }


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Redirect store to a temp directory for every test."""
    monkeypatch.setattr(store, "STORE_DIR", tmp_path)
    monkeypatch.setattr(store, "CONFIG_PATH", tmp_path / "config.json")
    return tmp_path


@pytest.fixture
def project():
    return "test-project"


@pytest.fixture
def analysis_data():
    return _make_analysis_data()


@pytest.fixture
def breakpoint_data():
    return _make_breakpoint()


@pytest.fixture
def reflection_meta():
    return _make_reflection_meta()


# --- Tests: HTML helpers ---

class TestBarChartHtml:

    def test_basic(self):
        items = [("Read", 10), ("Bash", 8), ("Edit", 5)]
        html = dashboard._bar_chart_html(items)
        assert "Read" in html
        assert "Bash" in html
        assert "10" in html
        assert "width:" in html

    def test_empty(self):
        html = dashboard._bar_chart_html([])
        assert "No data" in html or html.strip() == ""

    def test_single_item(self):
        html = dashboard._bar_chart_html([("Read", 42)])
        assert "Read" in html
        assert "42" in html
        assert "100" in html  # 100% width

    def test_large_numbers_formatted(self):
        html = dashboard._bar_chart_html([("Cache", 9835759)])
        assert "9,835,759" in html
        assert "9835759" not in html

    def test_float_values_formatted(self):
        html = dashboard._bar_chart_html([("Score", 33.0), ("Other", 617.5)])
        assert "33" in html
        assert "617.5" in html


class TestSummaryCardHtml:

    def test_basic(self):
        html = dashboard._summary_card_html("Turns", "127")
        assert "Turns" in html
        assert "127" in html

    def test_with_subtitle(self):
        html = dashboard._summary_card_html("Rate", "85%", "first-response")
        assert "85%" in html
        assert "first-response" in html


class TestTableHtml:

    def test_basic(self):
        headers = ["Style", "Count"]
        rows = [["question", "6"], ["imperative", "10"]]
        html = dashboard._table_html(headers, rows)
        assert "Style" in html
        assert "Count" in html
        assert "question" in html
        assert "imperative" in html
        assert "<table" in html

    def test_empty_rows(self):
        html = dashboard._table_html(["A", "B"], [])
        assert "<table" in html
        assert "A" in html


class TestProgressBarHtml:

    def test_basic(self):
        html = dashboard._progress_bar_html(0.75, "Questions")
        assert "Questions" in html
        assert "75" in html


# --- Tests: Session dashboard ---

class TestGenerateSessionHtml:

    def test_contains_sections(self, analysis_data, breakpoint_data,
                               reflection_meta):
        html = dashboard.generate_session_html(
            analysis_data, breakpoint_data, reflection_meta, "test-project")
        for heading in ["Tool Usage", "Prompt Style", "Voice Profile",
                        "Session Arc", "N-grams", "Token"]:
            assert heading in html, f"Missing section: {heading}"

    def test_tool_chart(self, analysis_data, breakpoint_data, reflection_meta):
        html = dashboard.generate_session_html(
            analysis_data, breakpoint_data, reflection_meta, "test-project")
        assert "Read" in html
        assert "Bash" in html
        assert "Edit" in html

    def test_effectiveness_table(self, analysis_data, breakpoint_data,
                                 reflection_meta):
        html = dashboard.generate_session_html(
            analysis_data, breakpoint_data, reflection_meta, "test-project")
        assert "question" in html
        assert "imperative" in html
        assert "statement" in html

    def test_voice_profile(self, analysis_data, breakpoint_data,
                           reflection_meta):
        html = dashboard.generate_session_html(
            analysis_data, breakpoint_data, reflection_meta, "test-project")
        # Agency framing
        for label in ["I", "We", "You"]:
            assert label in html
        # Let's gets HTML-escaped (apostrophe)
        assert "Let" in html
        # Certainty markers
        assert "hedging" in html.lower() or "assertive" in html.lower()

    def test_ngrams(self, analysis_data, breakpoint_data, reflection_meta):
        html = dashboard.generate_session_html(
            analysis_data, breakpoint_data, reflection_meta, "test-project")
        assert "add test" in html
        assert "make sure" in html
        assert "add test for" in html

    def test_valid_html(self, analysis_data, breakpoint_data, reflection_meta):
        html = dashboard.generate_session_html(
            analysis_data, breakpoint_data, reflection_meta, "test-project")
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_no_external_resources(self, analysis_data, breakpoint_data,
                                   reflection_meta):
        html = dashboard.generate_session_html(
            analysis_data, breakpoint_data, reflection_meta, "test-project")
        assert "<script src=" not in html
        assert "<link href=" not in html
        assert "cdn" not in html.lower()

    def test_html_escapes_special_chars(self, breakpoint_data,
                                        reflection_meta):
        data = _make_analysis_data()
        data["prompt_linguistics"]["frequent_ngrams"]["bigrams"] = [
            {"ngram": "<script>alert(1)</script>", "count": 5}
        ]
        html = dashboard.generate_session_html(
            data, breakpoint_data, reflection_meta, "test-project")
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_summary_cards(self, analysis_data, breakpoint_data,
                           reflection_meta):
        html = dashboard.generate_session_html(
            analysis_data, breakpoint_data, reflection_meta, "test-project")
        assert "10" in html  # turn count
        assert "25" in html  # tool calls
        assert "85" in html  # first-response acceptance (85%)

    def test_cache_hit_uses_correct_denominator(self, breakpoint_data,
                                                 reflection_meta):
        """Cache hit should be cache_read / (input + cache_read + cache_creation)."""
        data = _make_analysis_data()
        data["token_stats"] = {
            "total_input": 10000,
            "total_output": 1000,
            "total_cache_read": 9000000,
            "total_cache_creation": 400000,
        }
        html = dashboard.generate_session_html(
            data, breakpoint_data, reflection_meta, "test-project")
        # Correct: 9000000 / (10000 + 9000000 + 400000) = 95.6% -> rounds to 96%
        # Bug would give: 9000000 / 10000 * 100 = 90000%
        assert "90000%" not in html
        assert "96%" in html

    def test_dominant_agency_label(self, breakpoint_data, reflection_meta):
        """Dominant agency should display 'Let's' not 'lets'."""
        data = _make_analysis_data()
        data["prompt_linguistics"]["agency_framing"]["dominant"] = "lets"
        html = dashboard.generate_session_html(
            data, breakpoint_data, reflection_meta, "test-project")
        assert "Let&#x27;s</strong>" in html or "Let's</strong>" in html
        # Raw key should not appear as the display value
        assert ">lets</strong>" not in html

    def test_token_breakdown_split_charts(self, analysis_data, breakpoint_data,
                                           reflection_meta):
        """Token breakdown should have separate Input/Output and Cache charts."""
        html = dashboard.generate_session_html(
            analysis_data, breakpoint_data, reflection_meta, "test-project")
        assert "Input / Output" in html
        assert "Cache" in html

    def test_tool_scatter_has_percent(self, analysis_data, breakpoint_data,
                                      reflection_meta):
        """Tool scatter values should display with % suffix."""
        html = dashboard.generate_session_html(
            analysis_data, breakpoint_data, reflection_meta, "test-project")
        # Tool scatter section should use progress bars which include %
        scatter_section = html.split("Tool Scatter")[1].split("<h2>")[0]
        assert "%" in scatter_section


# --- Tests: Index dashboard ---

class TestGenerateIndexHtml:

    def test_lists_breakpoints(self):
        breakpoints = [
            {"id": 1, "timestamp": "2025-02-13T14:00:00+00:00", "note": "Start"},
            {"id": 2, "timestamp": "2025-02-13T16:00:00+00:00", "note": "End"},
        ]
        html = dashboard.generate_index_html(breakpoints, [], [], "test-project")
        assert "1" in html
        assert "2" in html
        assert "Start" in html
        assert "End" in html

    def test_links_reflected_breakpoints(self):
        breakpoints = [
            {"id": 1, "timestamp": "2025-02-13T14:00:00+00:00", "note": ""},
            {"id": 2, "timestamp": "2025-02-13T16:00:00+00:00", "note": ""},
        ]
        reflections = [
            {"id": 1, "breakpoint_id": 2, "timestamp": "2025-02-13T16:05:00+00:00"},
        ]
        manifest = [
            {"breakpoint_id": 2, "reflection_id": 1,
             "html_path": "session-2.html"},
        ]
        html = dashboard.generate_index_html(
            breakpoints, reflections, manifest, "test-project")
        assert "session-2.html" in html

    def test_no_reflections(self):
        breakpoints = [
            {"id": 1, "timestamp": "2025-02-13T14:00:00+00:00", "note": "Only one"},
        ]
        html = dashboard.generate_index_html(breakpoints, [], [], "test-project")
        assert "Only one" in html
        assert "<!DOCTYPE html>" in html

    def test_singular_pluralization(self):
        """'1 breakpoint' not '1 breakpoints'."""
        breakpoints = [
            {"id": 1, "timestamp": "2025-02-13T14:00:00+00:00", "note": ""},
        ]
        reflections = [
            {"id": 1, "breakpoint_id": 1, "timestamp": "2025-02-13T14:05:00+00:00"},
        ]
        html = dashboard.generate_index_html(breakpoints, reflections, [], "test-project")
        assert "1 breakpoint " in html or "1 breakpoint&" in html
        assert "1 reflection" in html
        assert "1 breakpoints" not in html
        assert "1 reflections" not in html

    def test_plural_pluralization(self):
        """'2 breakpoints' not '2 breakpoint'."""
        breakpoints = [
            {"id": 1, "timestamp": "t1", "note": ""},
            {"id": 2, "timestamp": "t2", "note": ""},
        ]
        html = dashboard.generate_index_html(breakpoints, [], [], "test-project")
        assert "2 breakpoints" in html

    def test_valid_html(self):
        html = dashboard.generate_index_html([], [], [], "test-project")
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html


# --- Tests: File write functions ---

class TestWriteDashboards:

    def test_write_session_dashboard_creates_file(
            self, project, analysis_data, breakpoint_data, reflection_meta,
            tmp_path):
        path = dashboard.write_session_dashboard(
            project, 2, analysis_data, breakpoint_data, reflection_meta)
        assert path.exists()
        content = path.read_text()
        assert "<!DOCTYPE html>" in content

    def test_write_session_dashboard_path_format(
            self, project, analysis_data, breakpoint_data, reflection_meta):
        path = dashboard.write_session_dashboard(
            project, 5, analysis_data, breakpoint_data, reflection_meta)
        assert path.name == "session-5.html"

    def test_write_index_dashboard_creates_file(self, project, tmp_path):
        path = dashboard.write_index_dashboard(project, [], [], [])
        assert path.exists()
        content = path.read_text()
        assert "<!DOCTYPE html>" in content

    def test_write_index_dashboard_overwrites(self, project):
        path1 = dashboard.write_index_dashboard(
            project,
            [{"id": 1, "timestamp": "2025-01-01T00:00:00+00:00", "note": "v1"}],
            [], [])
        content1 = path1.read_text()
        path2 = dashboard.write_index_dashboard(
            project,
            [{"id": 1, "timestamp": "2025-01-01T00:00:00+00:00", "note": "v2"}],
            [], [])
        content2 = path2.read_text()
        assert path1 == path2
        assert "v2" in content2


# --- Tests: CLI ---

class TestCLI:

    def test_cli_session_command(self, monkeypatch, capsys, project,
                                 analysis_data, breakpoint_data,
                                 reflection_meta):
        import io
        stdin_data = json.dumps({
            "analysis": analysis_data,
            "breakpoint": breakpoint_data,
            "reflection": reflection_meta,
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        monkeypatch.setattr("sys.argv",
                          ["dashboard_generator.py", "session", project,
                           "2", "--stdin"])
        dashboard.main()
        output = json.loads(capsys.readouterr().out)
        assert "path" in output

    def test_cli_index_command(self, monkeypatch, capsys, project):
        monkeypatch.setattr("sys.argv",
                          ["dashboard_generator.py", "index", project])
        dashboard.main()
        output = json.loads(capsys.readouterr().out)
        assert "path" in output

    def test_cli_usage_on_no_args(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["dashboard_generator.py"])
        with pytest.raises(SystemExit) as exc_info:
            dashboard.main()
        assert exc_info.value.code == 1
