"""Tests for dashboard_generator — HTML dashboard rendering.

Covers:
- HTML helper functions: bar chart, summary card, table, progress bar
- Markdown-to-HTML conversion
- Reflection dashboard generation: sections, data rendering, loops, full text
- Index dashboard generation: reflection listing, loop linking
- File write functions: path format, creation, overwrite
- CLI interface
- Backward compatibility with old session API
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


_DEFAULT_LOOPS = ["Experience \u2192 Question \u2192 Ship"]


def _make_reflection(id=1, loops=_DEFAULT_LOOPS, text="## Overview\n\nThis was a **great** session."):
    return {
        "id": id,
        "timestamp": "2025-02-13T16:05:00+00:00",
        "breakpoint_id": 2,
        "reflection": text,
        "git_summary": "3 commits: feature work",
        "prompt_count": 14,
        "loops": list(loops),
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
def reflection_data():
    return _make_reflection()


# --- Tests: HTML helpers ---

class TestBarChartHtml:

    def test_basic(self):
        html = dashboard._bar_chart_html([("Read", 10), ("Bash", 8), ("Edit", 5)])
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


# --- Tests: Markdown to HTML ---

class TestMarkdownToHtml:

    def test_headers(self):
        result = dashboard._markdown_to_html("# Title\n\n## Section\n\n### Sub")
        assert "<h1>" in result
        assert "<h2>" in result
        assert "<h3>" in result

    def test_bold(self):
        result = dashboard._markdown_to_html("This is **bold** text.")
        assert "<strong>bold</strong>" in result

    def test_code_spans(self):
        result = dashboard._markdown_to_html("Use `foo()` here.")
        assert "<code>foo()</code>" in result

    def test_list_items(self):
        result = dashboard._markdown_to_html("- first\n- second\n- third")
        assert "<ul>" in result
        assert "<li>" in result
        assert "first" in result
        assert "second" in result

    def test_paragraphs(self):
        result = dashboard._markdown_to_html("Line one.\n\nLine two.")
        assert "<p>" in result

    def test_escapes_html(self):
        result = dashboard._markdown_to_html("Use <script>alert(1)</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_bold_in_headers(self):
        result = dashboard._markdown_to_html("## 1. **The Loop**")
        assert "<strong>The Loop</strong>" in result
        assert "<h2>" in result


# --- Tests: Reflection dashboard ---

class TestGenerateReflectionHtml:

    def test_contains_sections(self, analysis_data, reflection_data):
        html = dashboard.generate_reflection_html(
            analysis_data, reflection_data, "test-project")
        for heading in ["Tool Usage", "Prompt Style", "Voice Profile",
                        "Session Arc", "N-grams", "Token"]:
            assert heading in html, f"Missing section: {heading}"

    def test_header_shows_reflection_id(self, analysis_data, reflection_data):
        html = dashboard.generate_reflection_html(
            analysis_data, reflection_data, "test-project")
        assert "Reflection #1" in html

    def test_shows_git_summary(self, analysis_data, reflection_data):
        html = dashboard.generate_reflection_html(
            analysis_data, reflection_data, "test-project")
        assert "3 commits" in html

    def test_shows_methodology_loops(self, analysis_data, reflection_data):
        html = dashboard.generate_reflection_html(
            analysis_data, reflection_data, "test-project")
        assert "Methodology Loops" in html
        assert "Experience" in html

    def test_shows_full_reflection_text(self, analysis_data):
        ref = _make_reflection(text="## Overview\n\nThis was a **great** session.")
        html = dashboard.generate_reflection_html(
            analysis_data, ref, "test-project")
        assert "Full Reflection" in html
        assert "great" in html
        assert "reflection-text" in html

    def test_no_reflection_text_skips_section(self, analysis_data):
        ref = _make_reflection(text="")
        html = dashboard.generate_reflection_html(
            analysis_data, ref, "test-project")
        assert "Full Reflection" not in html

    def test_tool_chart(self, analysis_data, reflection_data):
        html = dashboard.generate_reflection_html(
            analysis_data, reflection_data, "test-project")
        assert "Read" in html
        assert "Bash" in html
        assert "Edit" in html

    def test_effectiveness_table(self, analysis_data, reflection_data):
        html = dashboard.generate_reflection_html(
            analysis_data, reflection_data, "test-project")
        assert "question" in html
        assert "imperative" in html
        assert "statement" in html

    def test_voice_profile(self, analysis_data, reflection_data):
        html = dashboard.generate_reflection_html(
            analysis_data, reflection_data, "test-project")
        for label in ["I", "We", "You"]:
            assert label in html
        assert "Let" in html
        assert "hedging" in html.lower() or "assertive" in html.lower()

    def test_ngrams(self, analysis_data, reflection_data):
        html = dashboard.generate_reflection_html(
            analysis_data, reflection_data, "test-project")
        assert "add test" in html
        assert "make sure" in html
        assert "add test for" in html

    def test_valid_html(self, analysis_data, reflection_data):
        html = dashboard.generate_reflection_html(
            analysis_data, reflection_data, "test-project")
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_no_external_resources(self, analysis_data, reflection_data):
        html = dashboard.generate_reflection_html(
            analysis_data, reflection_data, "test-project")
        assert "<script src=" not in html
        assert "<link href=" not in html
        assert "cdn" not in html.lower()

    def test_html_escapes_special_chars(self):
        data = _make_analysis_data()
        data["prompt_linguistics"]["frequent_ngrams"]["bigrams"] = [
            {"ngram": "<script>alert(1)</script>", "count": 5}
        ]
        ref = _make_reflection()
        html = dashboard.generate_reflection_html(data, ref, "test-project")
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_summary_cards(self, analysis_data, reflection_data):
        html = dashboard.generate_reflection_html(
            analysis_data, reflection_data, "test-project")
        assert "10" in html  # turn count
        assert "25" in html  # tool calls
        assert "85" in html  # first-response acceptance (85%)

    def test_cache_hit_uses_correct_denominator(self):
        """Cache hit should be cache_read / (input + cache_read + cache_creation)."""
        data = _make_analysis_data()
        data["token_stats"] = {
            "total_input": 10000,
            "total_output": 1000,
            "total_cache_read": 9000000,
            "total_cache_creation": 400000,
        }
        ref = _make_reflection()
        html = dashboard.generate_reflection_html(data, ref, "test-project")
        # Correct: 9000000 / (10000 + 9000000 + 400000) = 95.6% -> rounds to 96%
        assert "90000%" not in html
        assert "96%" in html

    def test_dominant_agency_label(self):
        """Dominant agency should display 'Let's' not 'lets'."""
        data = _make_analysis_data()
        data["prompt_linguistics"]["agency_framing"]["dominant"] = "lets"
        ref = _make_reflection()
        html = dashboard.generate_reflection_html(data, ref, "test-project")
        assert "Let&#x27;s</strong>" in html or "Let's</strong>" in html
        assert ">lets</strong>" not in html

    def test_token_breakdown_split_charts(self, analysis_data, reflection_data):
        """Token breakdown should have separate Input/Output and Cache charts."""
        html = dashboard.generate_reflection_html(
            analysis_data, reflection_data, "test-project")
        assert "Input / Output" in html
        assert "Cache" in html

    def test_tool_scatter_has_percent(self, analysis_data, reflection_data):
        """Tool scatter values should display with % suffix."""
        html = dashboard.generate_reflection_html(
            analysis_data, reflection_data, "test-project")
        scatter_section = html.split("Tool Scatter")[1].split("<h2>")[0]
        assert "%" in scatter_section

    def test_no_loops_skips_section(self, analysis_data):
        ref = _make_reflection(loops=[])
        html = dashboard.generate_reflection_html(
            analysis_data, ref, "test-project")
        assert "Methodology Loops" not in html

    def test_step_frequency_section(self, analysis_data):
        ref = _make_reflection(loops=["A → B → C", "B → C → D"])
        html = dashboard.generate_reflection_html(
            analysis_data, ref, "test-project")
        assert "Step Frequency" in html

    def test_task_type_badge_on_loop_cards(self, analysis_data):
        ref = _make_reflection(
            loops=[{"loop": "A → B", "task_type": "Design"}])
        html = dashboard.generate_reflection_html(
            analysis_data, ref, "test-project")
        assert "task-badge" in html
        assert "Design" in html

    def test_old_string_loops_still_render(self, analysis_data):
        ref = _make_reflection(loops=["X → Y → Z"])
        html = dashboard.generate_reflection_html(
            analysis_data, ref, "test-project")
        assert "X → Y → Z" in html or "X →" in html
        assert "task-badge" in html  # unknown badge still appears


# --- Tests: Backward compatibility (old session API) ---

class TestBackwardCompatSessionApi:

    def test_generate_session_html_still_works(self, analysis_data):
        bp = {"id": 2, "timestamp": "2025-02-13T16:00:00+00:00", "note": "End"}
        ref_meta = {"id": 1, "timestamp": "2025-02-13T16:05:00+00:00"}
        html = dashboard.generate_session_html(
            analysis_data, bp, ref_meta, "test-project")
        assert "<!DOCTYPE html>" in html
        assert "Tool Usage" in html

    def test_write_session_dashboard_still_works(self, project, analysis_data):
        bp = {"id": 2, "timestamp": "2025-02-13T16:00:00+00:00", "note": "End"}
        ref_meta = {"id": 1, "timestamp": "2025-02-13T16:05:00+00:00"}
        path = dashboard.write_session_dashboard(
            project, 2, analysis_data, bp, ref_meta)
        assert path.exists()
        assert "<!DOCTYPE html>" in path.read_text()


# --- Tests: Index dashboard ---

class TestGenerateIndexHtml:

    def test_lists_reflections(self):
        reflections = [
            {"id": 1, "timestamp": "2025-02-13T16:05:00+00:00",
             "breakpoint_id": 1, "git_summary": "3 commits",
             "prompt_count": 14, "loops": ["A \u2192 B"]},
        ]
        html = dashboard.generate_index_html(reflections, [], "test-project")
        assert "3 commits" in html
        assert "14" in html
        assert "1 loop" in html

    def test_links_reflections_to_dashboards(self):
        reflections = [
            {"id": 1, "timestamp": "2025-02-13T16:05:00+00:00",
             "breakpoint_id": 2, "git_summary": "", "prompt_count": 0,
             "loops": []},
        ]
        manifest = [
            {"reflection_id": 1, "breakpoint_id": 2,
             "html_path": "reflection-1.html"},
        ]
        html = dashboard.generate_index_html(reflections, manifest, "test-project")
        assert "reflection-1.html" in html
        assert "View" in html

    def test_no_reflections(self):
        html = dashboard.generate_index_html([], [], "test-project")
        assert "0 reflections" in html
        assert "<!DOCTYPE html>" in html

    def test_singular_pluralization(self):
        """'1 reflection' not '1 reflections'."""
        reflections = [
            {"id": 1, "breakpoint_id": 1, "timestamp": "2025-02-13T14:05:00+00:00",
             "git_summary": "", "prompt_count": 0, "loops": []},
        ]
        html = dashboard.generate_index_html(reflections, [], "test-project")
        assert "1 reflection" in html
        assert "1 reflections" not in html

    def test_plural_pluralization(self):
        """'2 reflections' not '2 reflection'."""
        reflections = [
            {"id": 1, "timestamp": "t1", "breakpoint_id": 1,
             "git_summary": "", "prompt_count": 0, "loops": []},
            {"id": 2, "timestamp": "t2", "breakpoint_id": 2,
             "git_summary": "", "prompt_count": 0, "loops": []},
        ]
        html = dashboard.generate_index_html(reflections, [], "test-project")
        assert "2 reflections" in html

    def test_loops_link_to_reflection_pages(self):
        reflections = [
            {"id": 1, "timestamp": "2025-02-13T16:05:00+00:00",
             "breakpoint_id": 2, "git_summary": "", "prompt_count": 0,
             "loops": ["A \u2192 B"]},
        ]
        manifest = [
            {"reflection_id": 1, "breakpoint_id": 2,
             "html_path": "reflection-1.html"},
        ]
        loops = [
            {"loop": "A \u2192 B", "reflection_id": 1,
             "timestamp": "2025-02-13T16:05:00+00:00", "breakpoint_id": 2},
        ]
        html = dashboard.generate_index_html(
            reflections, manifest, "test-project", loops=loops)
        assert "loop-card" in html
        assert 'href="reflection-1.html"' in html
        assert "A \u2192 B" in html or "A &#x2192; B" in html or "A →" in html

    def test_loops_without_dashboard_not_linked(self):
        loops = [
            {"loop": "X \u2192 Y", "reflection_id": 99,
             "timestamp": "2025-02-13T16:05:00+00:00", "breakpoint_id": 2},
        ]
        html = dashboard.generate_index_html([], [], "test-project", loops=loops)
        assert "href=" not in html.split("Methodology Loops")[1].split("<h2>")[0]

    def test_valid_html(self):
        html = dashboard.generate_index_html([], [], "test-project")
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_loop_count_in_reflections_table(self):
        reflections = [
            {"id": 1, "timestamp": "2025-02-13T16:05:00+00:00",
             "breakpoint_id": 1, "git_summary": "",
             "prompt_count": 10, "loops": ["A", "B", "C"]},
        ]
        html = dashboard.generate_index_html(reflections, [], "test-project")
        assert "3 loops" in html

    def test_core_loop_section(self):
        loops = [
            {"loop": "A → B → C", "task_type": "Design",
             "reflection_id": 1, "timestamp": "2025-02-13T16:05:00+00:00"},
            {"loop": "A → B → C", "task_type": "Design",
             "reflection_id": 2, "timestamp": "2025-02-14T16:05:00+00:00"},
            {"loop": "D → E", "task_type": "QA/Testing",
             "reflection_id": 3, "timestamp": "2025-02-15T16:05:00+00:00"},
        ]
        html = dashboard.generate_index_html([], [], "test-project", loops=loops)
        assert "Core Loop" in html
        assert "core-loop" in html

    def test_step_frequency_fingerprint(self):
        loops = [
            {"loop": "A → B → C", "task_type": "Design",
             "reflection_id": 1, "timestamp": "2025-02-13T16:05:00+00:00"},
        ]
        html = dashboard.generate_index_html([], [], "test-project", loops=loops)
        assert "Step Frequency Fingerprint" in html

    def test_loop_evolution_section(self):
        loops = [
            {"loop": "A → B", "task_type": "Design",
             "reflection_id": 1, "timestamp": "2025-02-13T16:05:00+00:00"},
            {"loop": "C → D", "task_type": "Implementation",
             "reflection_id": 2, "timestamp": "2025-02-14T16:05:00+00:00"},
        ]
        html = dashboard.generate_index_html([], [], "test-project", loops=loops)
        assert "Loop Evolution" in html
        assert "Design" in html
        assert "Implementation" in html

    def test_task_type_badges_on_index_loop_cards(self):
        loops = [
            {"loop": "A → B", "task_type": "Debugging",
             "reflection_id": 1, "timestamp": "2025-02-13T16:05:00+00:00"},
        ]
        html = dashboard.generate_index_html([], [], "test-project", loops=loops)
        assert "task-badge" in html
        assert "Debugging" in html

    def test_no_analytics_without_loops(self):
        html = dashboard.generate_index_html([], [], "test-project", loops=[])
        assert "Core Loop" not in html
        assert "Step Frequency" not in html
        assert "Loop Evolution" not in html


# --- Tests: Theme system ---

class TestThemes:

    def test_all_themes_have_required_vars(self):
        required = {"bg", "surface", "card", "text", "text-muted", "accent",
                     "bar-1", "bar-2", "bar-3", "bar-4", "bar-5",
                     "success", "warning", "border"}
        for name, theme in dashboard.THEMES.items():
            assert set(theme.keys()) == required, f"Theme '{name}' has wrong keys"

    def test_default_theme_exists(self):
        assert dashboard.DEFAULT_THEME in dashboard.THEMES

    def test_theme_selector_in_output(self, analysis_data, reflection_data):
        html = dashboard.generate_reflection_html(
            analysis_data, reflection_data, "test-project")
        assert "theme-select" in html
        assert "localStorage" in html

    def test_all_themes_in_selector(self, analysis_data, reflection_data):
        html = dashboard.generate_reflection_html(
            analysis_data, reflection_data, "test-project")
        for name in dashboard.THEMES:
            assert name in html, f"Theme '{name}' missing from selector"

    def test_theme_selector_in_index(self):
        html = dashboard.generate_index_html([], [], "test-project")
        assert "theme-select" in html

    def test_no_external_resources_with_themes(self, analysis_data,
                                                reflection_data):
        html = dashboard.generate_reflection_html(
            analysis_data, reflection_data, "test-project")
        assert "http://" not in html
        assert "https://" not in html


# --- Tests: File write functions ---

class TestWriteDashboards:

    def test_write_reflection_dashboard_creates_file(
            self, project, analysis_data, reflection_data):
        path = dashboard.write_reflection_dashboard(
            project, 1, analysis_data, reflection_data)
        assert path.exists()
        content = path.read_text()
        assert "<!DOCTYPE html>" in content

    def test_write_reflection_dashboard_path_format(
            self, project, analysis_data, reflection_data):
        path = dashboard.write_reflection_dashboard(
            project, 5, analysis_data, reflection_data)
        assert path.name == "reflection-5.html"

    def test_write_index_dashboard_creates_file(self, project, tmp_path):
        path = dashboard.write_index_dashboard(project, [], [])
        assert path.exists()
        content = path.read_text()
        assert "<!DOCTYPE html>" in content

    def test_write_index_dashboard_overwrites(self, project):
        reflections_v1 = [
            {"id": 1, "timestamp": "t1", "breakpoint_id": 1,
             "git_summary": "v1", "prompt_count": 0, "loops": []}]
        reflections_v2 = [
            {"id": 1, "timestamp": "t1", "breakpoint_id": 1,
             "git_summary": "v2", "prompt_count": 0, "loops": []}]
        path1 = dashboard.write_index_dashboard(
            project, reflections_v1, [])
        path2 = dashboard.write_index_dashboard(
            project, reflections_v2, [])
        content2 = path2.read_text()
        assert path1 == path2
        assert "v2" in content2


# --- Tests: CLI ---

class TestCLI:

    def test_cli_reflection_command(self, monkeypatch, capsys, project,
                                     analysis_data, reflection_data):
        import io
        stdin_data = json.dumps({
            "analysis": analysis_data,
            "reflection": reflection_data,
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        monkeypatch.setattr("sys.argv",
                          ["dashboard_generator.py", "reflection", project,
                           "1", "--stdin"])
        dashboard.main()
        output = json.loads(capsys.readouterr().out)
        assert "path" in output
        assert "reflection-1" in output["path"]

    def test_cli_session_alias_still_works(self, monkeypatch, capsys, project,
                                            analysis_data, reflection_data):
        import io
        stdin_data = json.dumps({
            "analysis": analysis_data,
            "reflection": reflection_data,
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        monkeypatch.setattr("sys.argv",
                          ["dashboard_generator.py", "session", project,
                           "1", "--stdin"])
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
