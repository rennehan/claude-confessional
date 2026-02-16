#!/usr/bin/env python3
"""
dashboard_generator — pure-CSS HTML dashboard renderer for confessional reflections.

Generates self-contained HTML files with no external dependencies (no JS, no CDN).
Two output types:
  - Reflection dashboard: visualizes a single reflection's analysis data, loops, and text
  - Index dashboard: lists all reflections and links to their dashboards

Storage layout:
  ~/.reflection/projects/<project>/dashboards/
    reflection-<reflection_id>.html
    index.html
    manifest.jsonl
"""

import html
import json
import re
import sys
from pathlib import Path

import confessional_store as store

# --- CSS ---

THEMES = {
    "claude code": {
        "bg": "#1a1a1a", "surface": "#222222", "card": "#2a2a2a",
        "text": "#d4d4d4", "text-muted": "#737373", "accent": "#e07a3a",
        "bar-1": "#e07a3a", "bar-2": "#d4a27a", "bar-3": "#6bab6b",
        "bar-4": "#e0a848", "bar-5": "#7a9ec0",
        "success": "#6bab6b", "warning": "#e0a848", "border": "#333333",
    },
    "church of claude": {
        "bg": "#faf8f5", "surface": "#f0ebe3", "card": "#e8e0d4",
        "text": "#2a1a2e", "text-muted": "#6b5070", "accent": "#cfb53b",
        "bar-1": "#722f6b", "bar-2": "#cfb53b", "bar-3": "#8b2242",
        "bar-4": "#2e5090", "bar-5": "#1e8c5f",
        "success": "#1e8c5f", "warning": "#8b2242", "border": "#d4c8b8",
    },
    "midnight": {
        "bg": "#1a1a2e", "surface": "#16213e", "card": "#0f3460",
        "text": "#e0e0e0", "text-muted": "#8b8b8b", "accent": "#e94560",
        "bar-1": "#533483", "bar-2": "#e94560", "bar-3": "#2ecc71",
        "bar-4": "#f39c12", "bar-5": "#3498db",
        "success": "#2ecc71", "warning": "#f39c12", "border": "#2a2a4a",
    },
    "vespers": {
        "bg": "#1a1511", "surface": "#241c14", "card": "#2e2318",
        "text": "#e8dcc8", "text-muted": "#9a8b73", "accent": "#d4a254",
        "bar-1": "#b87333", "bar-2": "#c0755a", "bar-3": "#8fad7e",
        "bar-4": "#c07050", "bar-5": "#7a8b99",
        "success": "#8fad7e", "warning": "#d4a254", "border": "#3a2e20",
    },
    "cathedra": {
        "bg": "#1c1c1c", "surface": "#252525", "card": "#2e2e2e",
        "text": "#e0ddd5", "text-muted": "#8a8780", "accent": "#c0392b",
        "bar-1": "#2c3e6e", "bar-2": "#c0392b", "bar-3": "#d4a017",
        "bar-4": "#1e8c5f", "bar-5": "#7b4e9e",
        "success": "#1e8c5f", "warning": "#d4a017", "border": "#3a3a3a",
    },
    "cloister": {
        "bg": "#0d1b0e", "surface": "#142016", "card": "#1a2b1c",
        "text": "#c8d8c0", "text-muted": "#6e8a65", "accent": "#7dcea0",
        "bar-1": "#2d6a3f", "bar-2": "#7dcea0", "bar-3": "#8aad6e",
        "bar-4": "#5a8a50", "bar-5": "#4a9a8a",
        "success": "#7dcea0", "warning": "#a8c060", "border": "#243826",
    },
    "parchment": {
        "bg": "#f5f0e8", "surface": "#ebe4d8", "card": "#e0d8c8",
        "text": "#2c2416", "text-muted": "#6b5d4e", "accent": "#8b4513",
        "bar-1": "#a0522d", "bar-2": "#722f37", "bar-3": "#2c3e50",
        "bar-4": "#556b2f", "bar-5": "#5f6b7a",
        "success": "#556b2f", "warning": "#a0522d", "border": "#c8bfaf",
    },
    "terminal": {
        "bg": "#0a0a0a", "surface": "#111111", "card": "#1a1a1a",
        "text": "#cccccc", "text-muted": "#666666", "accent": "#00ff41",
        "bar-1": "#00ff41", "bar-2": "#00d4aa", "bar-3": "#ffb800",
        "bar-4": "#88ff00", "bar-5": "#ffffff",
        "success": "#00ff41", "warning": "#ffb800", "border": "#222222",
    },
    "byzantium": {
        "bg": "#120a1e", "surface": "#1a1028", "card": "#221638",
        "text": "#e0d8e8", "text-muted": "#8a7a9a", "accent": "#d4af37",
        "bar-1": "#7b4e9e", "bar-2": "#d4af37", "bar-3": "#c0392b",
        "bar-4": "#4a9a8a", "bar-5": "#e8dcc0",
        "success": "#4a9a8a", "warning": "#d4af37", "border": "#2e1e48",
    },
    "arctic": {
        "bg": "#0d1117", "surface": "#161b22", "card": "#1c2333",
        "text": "#c9d1d9", "text-muted": "#6e7a88", "accent": "#58a6ff",
        "bar-1": "#58a6ff", "bar-2": "#79c0ff", "bar-3": "#a0aec0",
        "bar-4": "#7ee8fa", "bar-5": "#b8a9e0",
        "success": "#3fb950", "warning": "#d29922", "border": "#21262d",
    },
    "ember": {
        "bg": "#1a0a0a", "surface": "#241210", "card": "#2e1815",
        "text": "#e8d0c8", "text-muted": "#9a7a70", "accent": "#ff6b35",
        "bar-1": "#ff6b35", "bar-2": "#c0443a", "bar-3": "#e8a030",
        "bar-4": "#a83232", "bar-5": "#8a7068",
        "success": "#e8a030", "warning": "#ff6b35", "border": "#3a2020",
    },
}

DEFAULT_THEME = "claude code"


def _theme_css_vars(theme_name=None):
    """Generate :root CSS variables for a theme."""
    theme = THEMES.get(theme_name or DEFAULT_THEME, THEMES[DEFAULT_THEME])
    lines = []
    for key, value in theme.items():
        lines.append(f"    --{key}: {value};")
    return ":root {\n" + "\n".join(lines) + "\n}"


THEME_SELECTOR_CSS = """
/* Page header with theme selector */
.page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.25rem;
}
.page-header h1 { margin-bottom: 0; }
.theme-selector {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    flex-shrink: 0;
}
.theme-selector label {
    font-size: 0.75rem;
    color: var(--text-muted);
    white-space: nowrap;
}
.theme-selector select {
    background: var(--card);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.3rem 0.5rem;
    font-size: 0.75rem;
    font-family: inherit;
    cursor: pointer;
    appearance: auto;
}
.theme-selector select:hover {
    border-color: var(--accent);
}
"""


def _theme_selector_html():
    """Generate the theme selector dropdown and script."""
    options = []
    for name in THEMES:
        label = name.title()
        options.append(f'<option value="{html.escape(name)}">{html.escape(label)}</option>')
    options_html = "\n".join(options)

    themes_json = json.dumps(THEMES, separators=(",", ":"))

    return f"""<div class="theme-selector">
<label for="theme-select">Select Theme:</label>
<select id="theme-select" aria-label="Color theme">
{options_html}
</select>
</div>
<script>
(function() {{
  var themes = {themes_json};
  var sel = document.getElementById('theme-select');
  var saved = localStorage.getItem('confessional-theme');
  if (saved && themes[saved]) sel.value = saved;
  function apply(name) {{
    var t = themes[name];
    if (!t) return;
    var r = document.documentElement.style;
    for (var k in t) r.setProperty('--' + k, t[k]);
    localStorage.setItem('confessional-theme', name);
  }}
  if (saved && themes[saved]) apply(saved);
  sel.addEventListener('change', function() {{ apply(sel.value); }});
}})();
</script>"""


CSS_STYLES = """
""" + _theme_css_vars(DEFAULT_THEME) + """

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

/* Loop cards grid */
.grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 0.75rem;
    margin-bottom: 1rem;
}
.loop-card {
    background: var(--card);
    border-radius: 6px;
    padding: 0.75rem;
    text-decoration: none;
    display: block;
    transition: background 0.15s;
}
.loop-card:hover { background: var(--surface); text-decoration: none; }
.loop-value { font-size: 1rem; font-weight: bold; color: var(--accent); margin-bottom: 0.25rem; }
.loop-label { font-size: 0.75rem; color: var(--text-muted); }

/* Reflection text */
.reflection-text {
    background: var(--surface);
    border-radius: 6px;
    padding: 1.25rem;
    font-size: 0.85rem;
    line-height: 1.7;
}
.reflection-text h1 { font-size: 1.2rem; margin: 1.25rem 0 0.5rem; border-bottom: none; }
.reflection-text h2 { font-size: 1.05rem; margin: 1.25rem 0 0.5rem; border-bottom: none; }
.reflection-text h3 { font-size: 0.9rem; margin: 1rem 0 0.4rem; color: var(--text); }
.reflection-text p { margin: 0.5rem 0; }
.reflection-text ul, .reflection-text ol { margin: 0.4rem 0 0.4rem 1.5rem; }
.reflection-text li { margin-bottom: 0.25rem; }
.reflection-text strong { color: var(--accent); }
.reflection-text code { background: var(--card); padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.8rem; }
""" + THEME_SELECTOR_CSS


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


def _markdown_to_html(text):
    """Convert basic markdown to HTML. Handles headers, bold, lists, paragraphs."""
    lines = text.split('\n')
    result = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        # Close list if we're no longer in one
        if in_list and not stripped.startswith('- '):
            result.append('</ul>')
            in_list = False

        # Headers
        if stripped.startswith('### '):
            result.append(f'<h3>{html.escape(stripped[4:])}</h3>')
        elif stripped.startswith('## '):
            header_text = stripped[3:]
            # Handle bold in headers: ## N. **Title**
            header_text = re.sub(
                r'\*\*(.+?)\*\*',
                lambda m: f'<strong>{html.escape(m.group(1))}</strong>',
                header_text)
            # Escape parts outside of tags
            parts = re.split(r'(<strong>.*?</strong>)', header_text)
            escaped = ''.join(
                p if p.startswith('<strong>') else html.escape(p)
                for p in parts)
            result.append(f'<h2>{escaped}</h2>')
        elif stripped.startswith('# '):
            result.append(f'<h1>{html.escape(stripped[2:])}</h1>')
        # List items
        elif stripped.startswith('- '):
            if not in_list:
                result.append('<ul>')
                in_list = True
            item_text = _inline_markdown(stripped[2:])
            result.append(f'<li>{item_text}</li>')
        # Empty line = paragraph break
        elif stripped == '':
            continue
        # Regular text
        else:
            result.append(f'<p>{_inline_markdown(stripped)}</p>')

    if in_list:
        result.append('</ul>')

    return '\n'.join(result)


def _inline_markdown(text):
    """Convert inline markdown (bold, code) to HTML."""
    # Code spans first (so bold inside code isn't processed)
    text = re.sub(r'`([^`]+)`',
                  lambda m: f'<code>{html.escape(m.group(1))}</code>', text)
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*',
                  lambda m: f'<strong>{html.escape(m.group(1))}</strong>', text)
    # Escape remaining text that isn't already in tags
    parts = re.split(r'(<(?:strong|code)>.*?</(?:strong|code)>)', text)
    result = ''.join(
        p if p.startswith(('<strong>', '<code>')) else html.escape(p)
        for p in parts)
    return result


# --- Reflection dashboard ---

def generate_reflection_html(analysis_data, reflection, project):
    """Generate a complete reflection dashboard HTML string.

    Args:
        analysis_data: Transcript analysis dict (tool_stats, token_stats, etc.)
        reflection: Full reflection entry dict (id, timestamp, reflection text,
                    loops, git_summary, prompt_count, breakpoint_id)
        project: Project name string
    """
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

    ref_id = reflection.get("id", "?")
    ref_ts = reflection.get("timestamp", "")
    ref_date = ref_ts[:10] if len(ref_ts) >= 10 else ref_ts
    git_summary = reflection.get("git_summary", "")

    parts = []

    # Header with theme selector
    selector = _theme_selector_html()
    parts.append(
        f'<div class="page-header">'
        f'<h1>{html.escape(project)}</h1>'
        f'{selector}'
        f'</div>'
    )
    parts.append(
        f'<div class="subtitle">'
        f'Reflection #{ref_id} &mdash; {html.escape(ref_date)}'
        f'{(" &mdash; " + html.escape(git_summary)) if git_summary else ""}'
        f'</div>'
    )

    # Methodology Loops
    loops = reflection.get("loops", [])
    if loops:
        loop_items = []
        for loop_text in loops:
            loop_items.append(
                f'<div class="card">'
                f'<div class="loop-value">{html.escape(loop_text)}</div>'
                f'</div>'
            )
        parts.append(_section_html(
            "Methodology Loops",
            f'<div class="grid">{"".join(loop_items)}</div>'))

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

    # Full reflection text
    reflection_text = reflection.get("reflection", "")
    if reflection_text:
        rendered = _markdown_to_html(reflection_text)
        parts.append(_section_html(
            "Full Reflection",
            f'<div class="reflection-text">{rendered}</div>'))

    body = "\n".join(parts)
    return _wrap_html(f"{project} — Reflection #{ref_id}", body)


# Backward-compatible alias
def generate_session_html(analysis_data, breakpoint, reflection_meta, project):
    """Deprecated: use generate_reflection_html instead."""
    reflection = dict(reflection_meta)
    reflection.setdefault("loops", [])
    reflection.setdefault("reflection", "")
    reflection.setdefault("git_summary", "")
    return generate_reflection_html(analysis_data, reflection, project)


# --- Index dashboard ---

def generate_index_html(reflections, manifest, project, loops=None):
    """Generate the master index dashboard HTML string."""
    # Build lookup: reflection_id -> html_path
    dashboard_paths = {}
    for entry in manifest:
        dashboard_paths[entry.get("reflection_id")] = entry["html_path"]

    ref_count = len(reflections)
    ref_word = "reflection" if ref_count == 1 else "reflections"

    parts = []
    selector = _theme_selector_html()
    parts.append(
        f'<div class="page-header">'
        f'<h1>{html.escape(project)}</h1>'
        f'{selector}'
        f'</div>'
    )
    parts.append(f'<div class="subtitle">{ref_count} {ref_word}</div>')

    # Methodology Loops section — cards link to reflection pages
    if loops:
        loop_items = []
        for entry in loops:
            ts = entry.get("timestamp", "")
            date = ts[:10] if len(ts) >= 10 else ts
            ref_id = entry.get("reflection_id", "?")
            html_path = dashboard_paths.get(ref_id)
            if html_path:
                loop_items.append(
                    f'<a class="loop-card" href="{html.escape(html_path)}">'
                    f'<div class="loop-value">{html.escape(entry["loop"])}</div>'
                    f'<div class="loop-label">Reflection #{ref_id} &mdash; {html.escape(date)}</div>'
                    f'</a>'
                )
            else:
                loop_items.append(
                    f'<div class="loop-card">'
                    f'<div class="loop-value">{html.escape(entry["loop"])}</div>'
                    f'<div class="loop-label">Reflection #{ref_id} &mdash; {html.escape(date)}</div>'
                    f'</div>'
                )
        loops_html = f'<div class="grid">{"".join(loop_items)}</div>'
        parts.append(_section_html("Methodology Loops", loops_html))

    # Reflections table
    rows = []
    for ref in reflections:
        ref_id = ref["id"]
        ts = ref.get("timestamp", "")
        date = ts[:10] if len(ts) >= 10 else ts
        git_summary = ref.get("git_summary", "")
        prompt_count = ref.get("prompt_count", 0)
        ref_loops = ref.get("loops", [])
        loop_count = len(ref_loops)
        html_path = dashboard_paths.get(ref_id)

        if html_path:
            view = f'<a href="{html.escape(html_path)}">View</a>'
        else:
            view = '<span class="status-no">&mdash;</span>'

        loops_cell = f'{loop_count} loop{"s" if loop_count != 1 else ""}'

        rows.append(
            f'<tr>'
            f'<td>{ref_id}</td>'
            f'<td>{html.escape(date)}</td>'
            f'<td>{html.escape(git_summary)}</td>'
            f'<td>{prompt_count}</td>'
            f'<td>{loops_cell}</td>'
            f'<td>{view}</td>'
            f'</tr>'
        )

    table = (
        '<table><thead><tr>'
        '<th>ID</th><th>Date</th><th>Git Summary</th>'
        '<th>Prompts</th><th>Loops</th><th></th>'
        '</tr></thead><tbody>'
        + "\n".join(rows)
        + '</tbody></table>'
    )
    parts.append(_section_html("Reflections", table))

    body = "\n".join(parts)
    return _wrap_html(f"{project} — Confessional", body)


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

def write_reflection_dashboard(project, reflection_id, analysis_data, reflection):
    """Write a reflection dashboard HTML file. Returns the file Path."""
    dashboards_dir = store._dashboards_dir(project)
    dashboards_dir.mkdir(parents=True, exist_ok=True)
    path = dashboards_dir / f"reflection-{reflection_id}.html"
    content = generate_reflection_html(analysis_data, reflection, project)
    path.write_text(content, encoding="utf-8")
    return path


# Backward-compatible alias
def write_session_dashboard(project, breakpoint_id, analysis_data,
                            breakpoint, reflection_meta):
    """Deprecated: use write_reflection_dashboard instead."""
    reflection = dict(reflection_meta)
    reflection.setdefault("loops", [])
    reflection.setdefault("reflection", "")
    reflection.setdefault("git_summary", "")
    ref_id = reflection.get("id", breakpoint_id)
    return write_reflection_dashboard(project, ref_id, analysis_data, reflection)


def write_index_dashboard(project, reflections, manifest, loops=None):
    """Write/overwrite the index dashboard HTML file. Returns the file Path."""
    dashboards_dir = store._dashboards_dir(project)
    dashboards_dir.mkdir(parents=True, exist_ok=True)
    path = dashboards_dir / "index.html"
    content = generate_index_html(reflections, manifest, project, loops)
    path.write_text(content, encoding="utf-8")
    return path


# --- CLI ---

def main():
    if len(sys.argv) < 3:
        print("Usage: dashboard_generator.py <command> <project> [args...] [--stdin]")
        print("Commands: reflection, index")
        sys.exit(1)

    use_stdin = "--stdin" in sys.argv
    argv = [a for a in sys.argv if a != "--stdin"]

    command = argv[1]
    project = argv[2]

    if command in ("reflection", "session"):
        reflection_id = int(argv[3]) if len(argv) > 3 else 1
        if use_stdin:
            if hasattr(sys.stdin, "buffer"):
                data = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="surrogatepass"))
            else:
                data = json.loads(sys.stdin.read())
        else:
            print(json.dumps({"error": "reflection command requires --stdin"}))
            sys.exit(1)
        analysis = data["analysis"]
        reflection = data["reflection"]
        path = write_reflection_dashboard(
            project, reflection_id, analysis, reflection)
        print(json.dumps({"path": str(path)}))

    elif command == "index":
        reflections = store.get_reflections(project)
        manifest = store.get_dashboard_manifest(project)
        loops = store.get_all_loops(project)
        path = write_index_dashboard(
            project, reflections, manifest, loops)
        print(json.dumps({"path": str(path)}))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
