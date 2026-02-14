# Claude Confessional 🙏

A methodology reflection tool for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

Claude Code ships with [`/insights`](https://www.zolkos.com/2026/02/04/deep-dive-how-claude-codes-insights-command-works.html) — a dashboard that aggregates your usage over 30 days: tool frequency, friction points, feature adoption. It tells you *what* you're doing. **confessional** is the complement: it analyzes *how* you think. Your iterative loop, your prompting language, your decision patterns, your collaboration dynamic with Claude — extracted per-session from the native transcripts and tracked over time.

| | `/insights` | `/reflect` |
|---|---|---|
| **Scope** | 30-day aggregate across all projects | Per-session, between breakpoints you define |
| **Output** | HTML dashboard with charts and stats | Text reflection + HTML dashboard, stored as JSONL + HTML |
| **Focus** | Tool usage, friction points, feature adoption | Prompting methodology, voice analysis, prompt effectiveness |
| **Data** | Usage statistics, code metrics | Turn-level analysis: prompts, responses, linguistic patterns, correction rates |
| **Tracking** | Snapshot — regenerate to see changes | Cumulative — reflections build a methodology history |
| **Control** | Fixed 30-day window | You choose when to mark boundaries and reflect |

## Installation

```bash
git clone https://github.com/rennehan/claude-confessional.git
cd claude-confessional
./install.sh
```

Restart Claude Code after installing.

<details>
<summary>Manual installation</summary>

```bash
mkdir -p ~/.claude/commands ~/.claude/scripts

cp record.md breakpoint.md reflect.md ~/.claude/commands/
cp confess.md amen.md sermon.md ~/.claude/commands/
cp confessional_store.py transcript_reader.py confessional_hook.py dashboard_generator.py ~/.claude/scripts/
chmod +x ~/.claude/scripts/confessional_store.py ~/.claude/scripts/transcript_reader.py ~/.claude/scripts/confessional_hook.py ~/.claude/scripts/dashboard_generator.py

python3 ~/.claude/scripts/confessional_hook.py --install
```

Restart Claude Code after installing hooks.
</details>

## Usage

### `/record` — Start Recording

Enable recording for the current project. Recording is **per-project** — you enable it independently in each project you want to track, and projects you haven't enabled are never touched. There is no global "always on" mode. Works in any directory — git repos and plain folders alike.

Once enabled for a project, recording persists across sessions — it stays on until you explicitly disable it. You only need to run `/record` once per project.

### `/breakpoint` — Mark a Session Boundary

Mark the end of a work session. Optionally attach a note:

```
/breakpoint Finished the auth refactor.
```

Breakpoints are also **created automatically** — a system hook fires on every SessionStart and inserts a breakpoint if your last session in that project was more than 4 hours ago. So if you forget to `/breakpoint` at the end of a session, the next session will pick up the boundary for you. Note: sessions less than 4 hours apart do **not** trigger an auto-breakpoint — use `/breakpoint` manually if you want a boundary between closely-spaced sessions.

### `/reflect` — Analyze Your Methodology

Claude reads every prompt, response, tool call, and git commit since the last breakpoint from the native transcripts and delivers a reflection. Not a summary. A *diagnosis*. Your loop, your patterns, your cognitive fingerprint. What you say when you're confused. What you say when you're excited. How you think.

If you have enough breakpoint history (3+), you'll be prompted to choose how far back to reflect — just the last session, or a wider arc spanning multiple sessions. This lets you zoom out and see how your methodology evolves over a longer stretch of work.

After the reflection is complete, `/reflect` automatically creates a new breakpoint so your next session starts fresh. You never need to manually `/breakpoint` after reflecting.

The reflection includes token economics — cache hit rates, cost-per-insight, most expensive turns — so you can see not just *how* you work, but how *efficiently*.

Each reflection also generates an **HTML dashboard** — a self-contained, pure-CSS visualization of your session data. Open it in any browser. No JavaScript, no CDN, no network requests. The master index at `~/.reflection/projects/<project>/dashboards/index.html` lists all breakpoints and links to reflected sessions.

Reflections accumulate. Over time, Claude can trace the evolution of your methodology.

### The Loop

```
/record          <- enable recording (once per project, not global)
  ... work ...
/breakpoint      <- mark a boundary
/reflect         <- analyze your methodology
  ... work ...   <- recording continues automatically
/breakpoint      <- mark another boundary
```

## How It Works

**Zero duplication.** Conversation data already lives in Claude Code's native JSONL transcripts at `~/.claude/projects/`. confessional reads that data on-demand — it never copies it.

confessional only stores what's *unique*:

- **Breakpoints** — session boundaries you define (`~/.reflection/projects/<project>/breakpoints.jsonl`)
- **Reflections** — methodology analyses (`~/.reflection/projects/<project>/reflections.jsonl`)
- **Recording state** — which projects are active, tracked per-project (`~/.reflection/config.json`)

Everything is plain text. No SQL. No database. Just JSON and JSONL files you can `cat`, pipe to an LLM, or load into any tool.

### Transcript Retention

Because confessional reads from Claude Code's native transcripts on-demand, those transcripts need to still exist when you `/reflect`. Claude Code automatically cleans up local transcripts after a configurable period (around 30 days by default). If you wait too long between a `/breakpoint` and `/reflect`, the transcript data for that session may already be gone.

Your confessional data in `~/.reflection/` (breakpoints, reflections, dashboards) is **never auto-cleaned** — once you generate a reflection, it's yours permanently. But you can only generate a reflection while the source transcripts still exist.

**Recommendation:** Run `/reflect` reasonably soon after a breakpoint. Don't let weeks pass. If you want a longer window, increase `cleanupPeriodDays` in your Claude Code settings (`~/.claude/settings.json`) to retain transcripts for longer.

### Architecture

| Module | Purpose |
|--------|---------|
| `confessional_store.py` | Breakpoints, reflections, recording state, dashboard manifest (JSON/JSONL I/O) |
| `transcript_reader.py` | Reads native JSONL transcripts, extracts turns/tools/metrics, computes prompt linguistics and effectiveness signals |
| `confessional_hook.py` | SessionStart hook only (auto-breakpoints when sessions are >4h apart) |
| `dashboard_generator.py` | Pure-CSS HTML dashboards: per-session visualizations and master index |

A single hook fires on SessionStart — no per-turn overhead, no Stop hook, no tokens spent on bookkeeping.

## What Gets Stored

| File | Contents |
|------|----------|
| `breakpoints.jsonl` | Session boundaries with timestamps and notes |
| `reflections.jsonl` | Methodology analyses produced by `/reflect` |
| `config.json` | Per-project recording toggle |
| `dashboards/index.html` | Master dashboard listing all breakpoints and reflection status |
| `dashboards/session-N.html` | Per-session HTML dashboard with charts and metrics |
| `dashboards/manifest.jsonl` | Tracks which dashboards have been generated |

Everything lives in `~/.reflection/` as plain JSON/JSONL/HTML. Human-readable, LLM-loadable, and portable.

## What Gets *Read* (Not Copied)

Claude Code's native transcripts at `~/.claude/projects/` contain everything:

- Every prompt and response, timestamped
- Every tool call with inputs and outputs
- Token usage, cache metrics, model info
- Session IDs, git branches, stop reasons

confessional reads this on-demand via `transcript_reader.py`. No duplication. The native transcripts are the source of truth.

## What `/reflect` Actually Does

It doesn't summarize your conversation. Any chatbot can do that. It extracts your **methodology**:

- **Your loop** — Do you think first then build, or build first then think? How many rounds of discussion before you commit?
- **Your language** — What phrases signal intent? When you say "what about X?" do you mean "do X" or "I'm exploring"?
- **Your corrections** — When do you push back? What triggers a redirect?
- **Your tool patterns** — Heavy on file reads = exploring. Heavy on writes = building. Heavy on bash = debugging. The tools tell the truth.
- **Your token economics** — Cache hit rate, cost per turn, output verbosity. Are you being efficient?
- **Your evolution** — How your methodology changes across sessions, across weeks, across projects.

### Voice Analysis

Each reflection includes a quantitative linguistic analysis of your prompts:

- **Signature phrases** — Your most frequent bigrams and trigrams, extracted and ranked. Repeated patterns like "for example", "make sure", or "what if" reveal your communication habits.
- **Communication mode** — Question ratio, imperative ratio, and agency framing (I/we/you/let's). Are you a questioner, a commander, or a collaborator?
- **Certainty profile** — Hedging phrases ("maybe", "I think", "not sure") vs assertive phrases ("must", "ensure", "need to"). When are you confident vs exploratory?
- **Effectiveness correlation** — Which prompt style (question, imperative, statement) gets the fewest corrections? The lowest token cost? The best first-response acceptance rate?
- **Session arc** — How your prompt length and correction rate change over a session. Do you warm up, or do you start strong and fatigue?

## The Liturgical Edition (Optional)

If you've fully converted to the Church of Claude, you can install the meme aliases alongside the standard commands:

```bash
cp confess.md ~/.claude/commands/
cp amen.md ~/.claude/commands/
cp sermon.md ~/.claude/commands/
```

Then your ritual becomes:

```
/confess         <- kneel and begin
  ... work ...
/amen            <- close the prayer
/sermon          <- receive the word
```

Same functionality, more piety. Both sets can coexist — use whichever matches your current level of devotion.

## Managing Recording

```bash
# Enable recording for a project
python3 ~/.claude/scripts/confessional_store.py enable_recording "<project>"

# Disable recording for a project
python3 ~/.claude/scripts/confessional_store.py disable_recording "<project>"

# Check recording status
python3 ~/.claude/scripts/confessional_store.py is_recording "<project>"

# Uninstall hooks
python3 ~/.claude/scripts/confessional_hook.py --uninstall
```

## License

MIT.
