# Claude Confessional 🙏

A reflection tool for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). It reads your conversation transcripts on-demand and analyzes your prompting methodology — not *what* you discussed, but *how* you work. Your iterative loop, your prompting patterns, your tool usage, your token efficiency.

You've developed a working style with Claude. You just haven't seen it from the outside yet.

## Installation

```bash
# Create directories
mkdir -p ~/.claude/commands ~/.claude/scripts

# Install commands and scripts
cp record.md ~/.claude/commands/
cp breakpoint.md ~/.claude/commands/
cp reflect.md ~/.claude/commands/
cp confessional_store.py ~/.claude/scripts/
cp transcript_reader.py ~/.claude/scripts/
cp confessional_hook.py ~/.claude/scripts/
chmod +x ~/.claude/scripts/confessional_store.py ~/.claude/scripts/transcript_reader.py ~/.claude/scripts/confessional_hook.py

# Register the system hooks
python3 ~/.claude/scripts/confessional_hook.py --install
```

Restart Claude Code after installing hooks.

## How It Works

**Zero duplication.** Conversation data already lives in Claude Code's native JSONL transcripts at `~/.claude/projects/`. confessional reads that data on-demand — it never copies it.

confessional only stores what's *unique*:

- **Breakpoints** — session boundaries you define (`~/.reflection/projects/<project>/breakpoints.jsonl`)
- **Reflections** — methodology analyses (`~/.reflection/projects/<project>/reflections.jsonl`)
- **Recording state** — which projects are active (`~/.reflection/config.json`)

Everything is plain text. No SQL. No database. Just JSON and JSONL files you can `cat`, pipe to an LLM, or load into any tool.

### Architecture

| Module | Purpose |
|--------|---------|
| `confessional_store.py` | Breakpoints, reflections, recording state (JSON/JSONL I/O) |
| `transcript_reader.py` | Reads native JSONL transcripts, extracts turns/tools/metrics |
| `confessional_hook.py` | SessionStart hook only (auto-breakpoints when sessions are >4h apart) |

A single hook fires on SessionStart — no per-turn overhead, no Stop hook, no tokens spent on bookkeeping.

## Usage

### `/record` — Start Recording

Enable recording for the current project. From then on, confessional tracks your session boundaries and can analyze your conversation data on-demand.

Recording persists across sessions — once enabled, it stays on until you disable it.

### `/breakpoint` — Mark a Session Boundary

Mark the end of a work session. Optionally attach a note:

```
/breakpoint Finished the auth refactor.
```

### `/reflect` — Analyze Your Methodology

Claude reads every prompt, response, tool call, and git commit since the last breakpoint from the native transcripts and delivers a reflection. Not a summary. A *diagnosis*. Your loop, your patterns, your cognitive fingerprint. What you say when you're confused. What you say when you're excited. How you think.

The reflection includes token economics — cache hit rates, cost-per-insight, most expensive turns — so you can see not just *how* you work, but how *efficiently*.

Reflections accumulate. Over time, Claude can trace the evolution of your methodology.

## The Loop

```
/record          <- enable recording (once per project)
  ... work ...
/breakpoint      <- mark a boundary
/reflect         <- analyze your methodology
  ... work ...   <- recording continues automatically
/breakpoint      <- mark another boundary
```

## What Gets Stored

| File | Contents |
|------|----------|
| `breakpoints.jsonl` | Session boundaries with timestamps and notes |
| `reflections.jsonl` | Methodology analyses produced by `/reflect` |
| `config.json` | Per-project recording toggle |

Everything lives in `~/.reflection/` as plain JSON/JSONL. Human-readable, LLM-loadable, and portable.

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
