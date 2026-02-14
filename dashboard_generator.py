#!/usr/bin/env python3
"""
dashboard_generator — pure-CSS HTML dashboard renderer for confessional reflections.

Generates self-contained HTML files with no external dependencies (no JS, no CDN).
Two output types:
  - Session dashboard: visualizes a single breakpoint window's analysis data
  - Index dashboard: lists all breakpoints and links to reflected sessions

Storage layout:
  ~/.reflection/projects/<project>/dashboards/
    session-<breakpoint_id>.html
    index.html
    manifest.jsonl
"""

import html
import json
import sys
from pathlib import Path

import confessional_store as store

# --- CSS ---

CSS_STYLES = """
:root {
    --bg: #1a1a2e;
    --surface: #16213e;
    --card: #0f3460;
    --text: #e0e0e0;
    --text-muted: #8b8b8b;
    --accent: #e94560;
    --bar-1: #533483;
    --bar-2: #e94560;
    --bar-3: #2ecc71;
    --bar-4: #f39c12;
    --bar-5: #3498db;
    --success: #2ecc71;
    --warning: #f39c12;
    --border: #2a2a4a;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 2rem;
    max-width: 960px;
    margin: 0 auto;
}

h1 { font-size: 1.5rem; margin-bottom: 0.25rem; color: var(--accent); }
h2 { font-size: 1.15rem; margin: 1.5rem 0 0.75rem; color: var(--text); border-bottom: 1px solid var(--border); padding-bottom: 0.3rem; }
h3 { font-size: 0.95rem; margin: 1rem 0 0.5rem; color: var(--text-muted); }

.subtitle { color: var(--text-muted); font-size: 0.85rem; margin-bottom: 1.5rem; }

/* Summary cards */
.cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 0.75rem;
    margin-bottom: 1rem;
}
.card {
    background: var(--card);
    border-radius: 6px;
    padding: 0.75rem;
    text-align: center;
}
.card-value { font-size: 1.4rem; font-weight: bold; color: var(--accent); }
.card-label { font-size: 0.75rem; color: var(--text-muted); margin-top: 0.15rem; }
.card-sub { font-size: 0.65rem; color: var(--text-muted); }

/* Bar chart */
.bar-chart { margin: 0.5rem 0; }
.bar-row {
    display: flex;
    align-items: center;
    margin-bottom: 0.35rem;
}
.bar-label {
    width: 100px;
    font-size: 0.8rem;
    color: var(--text-muted);
    text-align: right;
    padding-right: 0.75rem;
    flex-shrink: 0;
}
.bar-track {
    flex: 1;
    background: var(--surface);
    border-radius: 3px;
    height: 20px;
    overflow: hidden;
}
.bar-fill {
    height: 100%;
    border-radius: 3px;
    background: var(--bar-1);
    transition: width 0.3s;
}
.bar-fill.c2 { background: var(--bar-2); }
.bar-fill.c3 { background: var(--bar-3); }
.bar-fill.c4 { background: var(--bar-4); }
.bar-fill.c5 { background: var(--bar-5); }
.bar-value {
    width: 50px;
    font-size: 0.8rem;
    padding-left: 0.5rem;
    color: var(--text-muted);
    flex-shrink: 0;
}
.bar-chart .no-data { color: var(--text-muted); font-size: 0.8rem; font-style: italic; }

/* Progress bar */
.progress-row {
    display: flex;
    align-items: center;
    margin-bottom: 0.4rem;
}
.progress-label {
    width: 120px;
    font-size: 0.8rem;
    color: var(--text-muted);
    text-align: right;
    padding-right: 0.75rem;
    flex-shrink: 0;
}
.progress-track {
    flex: 1;
    background: var(--surface);
    border-radius: 3px;
    height: 16px;
    overflow: hidden;
}
.progress-fill {
    height: 100%;
    border-radius: 3px;
    background: var(--accent);
}
.progress-value {
    width: 50px;
    font-size: 0.8rem;
    padding-left: 0.5rem;
    color: var(--text-muted);
    flex-shrink: 0;
}

/* Tables */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 0.5rem 0;
    font-size: 0.85rem;
}
th {
    text-align: left;
    padding: 0.4rem 0.6rem;
    border-bottom: 2px solid var(--border);
    color: var(--text-muted);
    font-weight: 600;
}
td {
    padding: 0.35rem 0.6rem;
    border-bottom: 1px solid var(--border);
}
tr.best td { color: var(--success); }

/* Two-column layout for n-grams */
.two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
}

/* Index table */
.status-yes { color: var(--success); }
.status-no { color: var(--text-muted); }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

/* Indicator */
.indicator { font-size: 0.8rem; padding: 0.15rem 0.5rem; border-radius: 3px; }
.indicator.positive { background: rgba(46, 204, 113, 0.15); color: var(--success); }
.indicator.neutral { background: rgba(139, 139, 139, 0.15); color: var(--text-muted); }
"""


# --- HTML helpers ---

def _format_value(value):
    """Format a numeric value for display: comma-separate integers, keep floats short."""
    if isinstance(value, int):
        return f'{value:,}'
    if isinstance(value, float):
        if value == int(value):
            return f'{int(value):,}'
        return f'{value:,.1f}'
    return str(value)


def _bar_chart_html(items):
    """Render a horizontal bar chart. items: list of (label, value) tuples."""
    if not items:
        return '<div class="bar-chart"><span class="no-data">No data</span></div>'
    max_val = max(v for _, v in items) if items else 1
    if max_val == 0:
        max_val = 1
    colors = ["", "c2", "c3", "c4", "c5"]
    rows = []
    for i, (label, value) in enumerate(items):
        pct = round((value / max_val) * 100)
        color_class = colors[i % len(colors)]
        display_val = _format_value(value)
        rows.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{html.escape(str(label))}</span>'
            f'<div class="bar-track">'
            f'<div class="bar-fill {color_class}" style="width: {pct}%"></div>'
            f'</div>'
            f'<span class="bar-value">{html.escape(display_val)}</span>'
            f'</div>'
        )
    return '<div class="bar-chart">' + "\n".join(rows) + '</div>'


def _summary_card_html(title, value, subtitle=""):
    """Render a summary metric card."""
    sub = f'<div class="card-sub">{html.escape(str(subtitle))}</div>' if subtitle else ""
    return (
        f'<div class="card">'
        f'<div class="card-value">{html.escape(str(value))}</div>'
        f'<div class="card-label">{html.escape(str(title))}</div>'
        f'{sub}'
        f'</div>'
    )


def _table_html(headers, rows):
    """Render an HTML table. headers: list of str, rows: list of list of str."""
    th = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body_rows = []
    for row in rows:
        cls = ""
        if isinstance(row, tuple) and len(row) == 2:
            row, cls = row[0], row[1]
        tds = "".join(f"<td>{html.escape(str(c))}</td>" for c in row)
        if cls:
            body_rows.append(f"<tr class=\"{cls}\">{tds}</tr>")
        else:
            body_rows.append(f"<tr>{tds}</tr>")
    return (
        f'<table><thead><tr>{th}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody></table>'
    )


def _progress_bar_html(value, label):
    """Render a progress bar for a 0.0-1.0 ratio."""
    pct = round(value * 100)
    return (
        f'<div class="progress-row">'
        f'<span class="progress-label">{html.escape(str(label))}</span>'
        f'<div class="progress-track">'
        f'<div class="progress-fill" style="width: {pct}%"></div>'
        f'</div>'
        f'<span class="progress-value">{pct}%</span>'
        f'</div>'
    )


def _section_html(title, content):
    """Wrap content in a titled section."""
    return f'<h2>{html.escape(title)}</h2>\n{content}'


# --- Session dashboard ---

def generate_session_html(analysis_data, breakpoint, reflection_meta, project):
    """Generate a complete session dashboard HTML string."""
    tool_stats = analysis_data.get("tool_stats", {})
    token_stats = analysis_data.get("token_stats", {})
    linguistics = analysis_data.get("prompt_linguistics", {})
    effectiveness = analysis_data.get("effectiveness_signals", {})
    sessions = analysis_data.get("sessions", [])

    total_input = token_stats.get("total_input", 0)
    total_output = token_stats.get("total_output", 0)
    cache_read = token_stats.get("total_cache_read", 0)
    cache_creation = token_stats.get("total_cache_creation", 0)
    total_all_input = total_input + cache_read + cache_creation
    cache_hit = round(cache_read / total_all_input * 100) if total_all_input > 0 else 0

    bp_ts = breakpoint.get("timestamp", "")
    bp_note = breakpoint.get("note", "")

    parts = []

    # Header
    parts.append(f'<h1>{html.escape(project)}</h1>')
    parts.append(
        f'<div class="subtitle">'
        f'Breakpoint #{breakpoint.get("id", "?")} &mdash; {html.escape(bp_ts)}'
        f'{(" &mdash; " + html.escape(bp_note)) if bp_note else ""}'
        f'</div>'
    )

    # Summary cards
    cards = [
        _summary_card_html("Turns", analysis_data.get("turn_count", 0)),
        _summary_card_html("Tool Calls", tool_stats.get("total", 0)),
        _summary_card_html("Sessions", len(sessions)),
        _summary_card_html("Correction Rate",
                           f'{round(effectiveness.get("correction_rate", 0) * 100)}%'),
        _summary_card_html("Acceptance",
                           f'{round(effectiveness.get("first_response_acceptance", 0) * 100)}%',
                           "first-response"),
        _summary_card_html("Tokens",
                           f'{(total_input + total_output):,}',
                           "input + output"),
        _summary_card_html("Cache Hit",
                           f'{cache_hit}%',
                           "read / input"),
    ]
    parts.append('<div class="cards">' + "\n".join(cards) + '</div>')

    # Tool usage bar chart
    by_tool = tool_stats.get("by_tool", {})
    sorted_tools = sorted(by_tool.items(), key=lambda x: x[1], reverse=True)
    parts.append(_section_html("Tool Usage", _bar_chart_html(sorted_tools)))

    # Prompt style effectiveness table
    pse = effectiveness.get("per_style_effectiveness", {})
    best_style = None
    best_rate = 1.0
    for style, data in pse.items():
        if data.get("count", 0) > 0 and data.get("correction_rate", 1.0) < best_rate:
            best_rate = data["correction_rate"]
            best_style = style

    eff_rows = []
    for style in ["question", "imperative", "statement"]:
        data = pse.get(style, {})
        row = [
            style,
            str(data.get("count", 0)),
            f'{round(data.get("correction_rate", 0) * 100)}%',
            f'{data.get("avg_tool_count", 0):.1f}',
            f'{data.get("avg_tokens", 0):,.0f}',
        ]
        if style == best_style:
            eff_rows.append((row, "best"))
        else:
            eff_rows.append(row)

    parts.append(_section_html(
        "Prompt Style Effectiveness",
        _table_html(
            ["Style", "Count", "Correction Rate", "Avg Tools", "Avg Tokens"],
            eff_rows)))

    # Voice profile
    voice_parts = []

    # Communication mode
    voice_parts.append('<h3>Communication Mode</h3>')
    voice_parts.append(_progress_bar_html(
        linguistics.get("question_ratio", 0), "Questions"))
    voice_parts.append(_progress_bar_html(
        linguistics.get("imperative_ratio", 0), "Imperatives"))

    # Agency framing
    agency = linguistics.get("agency_framing", {})
    voice_parts.append('<h3>Agency Framing</h3>')
    agency_items = [
        ("I", agency.get("i_count", 0)),
        ("We", agency.get("we_count", 0)),
        ("You", agency.get("you_count", 0)),
        ("Let's", agency.get("lets_count", 0)),
    ]
    voice_parts.append(_bar_chart_html(agency_items))
    dominant_key = agency.get("dominant", "none")
    dominant_labels = {"i": "I", "we": "We", "you": "You", "lets": "Let's", "none": "None"}
    dominant_label = dominant_labels.get(dominant_key, dominant_key)
    voice_parts.append(
        f'<div class="subtitle">Dominant: <strong>{html.escape(dominant_label)}</strong></div>')

    # Certainty markers
    cert = linguistics.get("certainty_markers", {})
    voice_parts.append('<h3>Certainty Profile</h3>')
    cert_items = [
        ("Hedging", cert.get("hedging_count", 0)),
        ("Assertive", cert.get("assertive_count", 0)),
    ]
    voice_parts.append(_bar_chart_html(cert_items))

    parts.append(_section_html("Voice Profile", "\n".join(voice_parts)))

    # Session arc
    pos = linguistics.get("prompt_length_by_position", {})
    arc_items = [
        ("First quarter", round(pos.get("first_quarter_avg", 0), 1)),
        ("Middle half", round(pos.get("middle_half_avg", 0), 1)),
        ("Last quarter", round(pos.get("last_quarter_avg", 0), 1)),
    ]
    progression = effectiveness.get("session_progression", {})
    warming = progression.get("warming_up", False)
    warming_html = (
        '<span class="indicator positive">Warming up detected</span>'
        if warming else
        '<span class="indicator neutral">No warming trend</span>'
    )
    parts.append(_section_html(
        "Session Arc",
        '<h3>Prompt Length by Position (avg words)</h3>'
        + _bar_chart_html(arc_items)
        + '<h3>Session Progression (correction rate)</h3>'
        + _progress_bar_html(
            progression.get("first_half_correction_rate", 0), "First half")
        + _progress_bar_html(
            progression.get("second_half_correction_rate", 0), "Second half")
        + f'<div style="margin-top:0.3rem">{warming_html}</div>'
    ))

    # Tool scatter (use progress bars since these are 0.0-1.0 ratios)
    scatter = effectiveness.get("tool_scatter", {})
    scatter_html = '<div class="subtitle">Higher = more scattered file access</div>'
    for style_label, style_key in [("Question", "question"), ("Imperative", "imperative"),
                                    ("Statement", "statement"), ("Overall", "overall")]:
        scatter_html += _progress_bar_html(scatter.get(style_key, 0), style_label)
    parts.append(_section_html("Tool Scatter", scatter_html))

    # N-grams
    ngrams = linguistics.get("frequent_ngrams", {})
    bigrams = ngrams.get("bigrams", [])
    trigrams = ngrams.get("trigrams", [])
    bigram_rows = [[ng["ngram"], str(ng["count"])] for ng in bigrams[:10]]
    trigram_rows = [[ng["ngram"], str(ng["count"])] for ng in trigrams[:10]]
    parts.append(_section_html(
        "N-grams",
        '<div class="two-col">'
        + '<div><h3>Bigrams</h3>'
        + _table_html(["Phrase", "Count"], bigram_rows)
        + '</div>'
        + '<div><h3>Trigrams</h3>'
        + _table_html(["Phrase", "Count"], trigram_rows)
        + '</div></div>'))

    # Token breakdown — split into two charts since cache tokens dwarf input/output
    io_items = [
        ("Input", total_input),
        ("Output", total_output),
    ]
    cache_items = [
        ("Cache Read", cache_read),
        ("Cache Create", cache_creation),
    ]
    parts.append(_section_html(
        "Token Breakdown",
        '<h3>Input / Output</h3>'
        + _bar_chart_html(io_items)
        + '<h3>Cache</h3>'
        + _bar_chart_html(cache_items)))

    body = "\n".join(parts)
    return _wrap_html(f"{project} — Session Dashboard", body)


# --- Index dashboard ---

def generate_index_html(breakpoints, reflections, manifest, project):
    """Generate the master index dashboard HTML string."""
    # Build lookup: breakpoint_id -> reflection
    reflected_ids = set()
    for ref in reflections:
        bp_id = ref.get("breakpoint_id")
        if bp_id is not None:
            reflected_ids.add(bp_id)

    # Build lookup: breakpoint_id -> html_path
    dashboard_paths = {}
    for entry in manifest:
        dashboard_paths[entry["breakpoint_id"]] = entry["html_path"]

    parts = []
    parts.append(f'<h1>{html.escape(project)}</h1>')
    bp_count = len(breakpoints)
    ref_count = len(reflections)
    bp_word = "breakpoint" if bp_count == 1 else "breakpoints"
    ref_word = "reflection" if ref_count == 1 else "reflections"
    parts.append(
        f'<div class="subtitle">'
        f'{bp_count} {bp_word} &mdash; '
        f'{ref_count} {ref_word}'
        f'</div>')

    # Breakpoint table
    rows = []
    for bp in breakpoints:
        bp_id = bp["id"]
        is_reflected = bp_id in reflected_ids
        html_path = dashboard_paths.get(bp_id)

        if is_reflected and html_path:
            status = f'<a href="{html.escape(html_path)}">View Dashboard</a>'
        elif is_reflected:
            status = '<span class="status-yes">Reflected</span>'
        else:
            status = '<span class="status-no">&mdash;</span>'

        rows.append(
            f'<tr>'
            f'<td>{bp_id}</td>'
            f'<td>{html.escape(bp.get("timestamp", ""))}</td>'
            f'<td>{html.escape(bp.get("note", ""))}</td>'
            f'<td>{status}</td>'
            f'</tr>'
        )

    table = (
        '<table><thead><tr>'
        '<th>ID</th><th>Timestamp</th><th>Note</th><th>Status</th>'
        '</tr></thead><tbody>'
        + "\n".join(rows)
        + '</tbody></table>'
    )
    parts.append(_section_html("Breakpoints", table))

    body = "\n".join(parts)
    return _wrap_html(f"{project} — Dashboard Index", body)


# --- HTML wrapper ---

def _wrap_html(title, body):
    """Wrap body content in a full HTML document."""
    return (
        f'<!DOCTYPE html>\n'
        f'<html lang="en">\n'
        f'<head>\n'
        f'<meta charset="utf-8">\n'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{html.escape(title)}</title>\n'
        f'<style>{CSS_STYLES}</style>\n'
        f'</head>\n'
        f'<body>\n'
        f'{body}\n'
        f'</body>\n'
        f'</html>\n'
    )


# --- File writers ---

def write_session_dashboard(project, breakpoint_id, analysis_data,
                            breakpoint, reflection_meta):
    """Write a session dashboard HTML file. Returns the file Path."""
    dashboards_dir = store._dashboards_dir(project)
    dashboards_dir.mkdir(parents=True, exist_ok=True)
    path = dashboards_dir / f"session-{breakpoint_id}.html"
    content = generate_session_html(
        analysis_data, breakpoint, reflection_meta, project)
    path.write_text(content, encoding="utf-8")
    return path


def write_index_dashboard(project, breakpoints, reflections, manifest):
    """Write/overwrite the index dashboard HTML file. Returns the file Path."""
    dashboards_dir = store._dashboards_dir(project)
    dashboards_dir.mkdir(parents=True, exist_ok=True)
    path = dashboards_dir / "index.html"
    content = generate_index_html(breakpoints, reflections, manifest, project)
    path.write_text(content, encoding="utf-8")
    return path


# --- CLI ---

def main():
    if len(sys.argv) < 3:
        print("Usage: dashboard_generator.py <command> <project> [args...] [--stdin]")
        print("Commands: session, index")
        sys.exit(1)

    use_stdin = "--stdin" in sys.argv
    argv = [a for a in sys.argv if a != "--stdin"]

    command = argv[1]
    project = argv[2]

    if command == "session":
        breakpoint_id = int(argv[3]) if len(argv) > 3 else 1
        if use_stdin:
            if hasattr(sys.stdin, "buffer"):
                data = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="surrogatepass"))
            else:
                data = json.loads(sys.stdin.read())
        else:
            print(json.dumps({"error": "session command requires --stdin"}))
            sys.exit(1)
        analysis = data["analysis"]
        bp = data["breakpoint"]
        ref_meta = data["reflection"]
        path = write_session_dashboard(
            project, breakpoint_id, analysis, bp, ref_meta)
        print(json.dumps({"path": str(path)}))

    elif command == "index":
        breakpoints = store.get_all_breakpoints(project)
        reflections = store.get_reflections(project)
        manifest = store.get_dashboard_manifest(project)
        path = write_index_dashboard(
            project, breakpoints, reflections, manifest)
        print(json.dumps({"path": str(path)}))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
