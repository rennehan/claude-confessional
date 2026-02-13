# claude-confessional 🙏

*Because every prompt deserves absolution.*

You've been talking to Claude for hours. Days. Weeks. You've developed habits, tics, patterns — a whole liturgy of prompting that you're not even conscious of. You say "let's think about this" when you're not ready to commit. You say "this is fine" when you want Claude to shut up and move on. You have a *methodology*, and you don't even know what it is.

**confessional** records everything — your prompts, Claude's responses, every tool call, every sub-agent spawn — and then reflects it back to you. Not what you talked about. *How you think.*

Welcome to the Church of Claude. Please be seated.

## Installation

```bash
# Receive the sacraments
mkdir -p ~/.claude/commands ~/.claude/scripts

# Install the holy texts
cp record.md ~/.claude/commands/
cp breakpoint.md ~/.claude/commands/
cp reflect.md ~/.claude/commands/
cp reflection_db.py ~/.claude/scripts/
cp confessional_hook.py ~/.claude/scripts/
chmod +x ~/.claude/scripts/reflection_db.py ~/.claude/scripts/confessional_hook.py

# Register the system hooks
python3 ~/.claude/scripts/confessional_hook.py --install
```

Restart Claude Code after installing hooks.

## How It Works

Recording is powered by **Claude Code hooks** — system-level event handlers that fire automatically on every interaction. When you run `/record` in a project, it enables recording for that project. From then on, two hooks handle everything silently:

- **Stop hook** — fires after every Claude response, parses the conversation transcript, and records the prompt, response, and all tool calls to the database.
- **SessionStart hook** — fires when a new session begins, recording session context (git branch, commit, etc.).

No per-turn overhead. No tokens spent on bookkeeping. No reliance on Claude remembering to record. Just lossless, automatic capture.

## The Sacred Ritual

### `/record` — Begin Confession

Enable recording for the current project. Every prompt you utter and every response Claude gives is written to the eternal ledger at `~/.reflection/history.db`. Tool calls, sub-agent spawns, session context — all of it. Claude works normally, but now God is watching.

Recording persists across sessions — once enabled, it stays on until you disable it.

### `/breakpoint` — Say Your Amen

Mark the end of a work session. Optionally attach a note for the historical record:

```
/breakpoint Mass is over. We built a knowledge graph.
```

### `/reflect` — Receive Your Sermon

Claude examines your sins — every prompt, response, tool call, and git commit since the last breakpoint — and delivers a reflection. Not a summary. A *diagnosis*. Your loop, your patterns, your cognitive fingerprint. What you say when you're confused. What you say when you're excited. How you think.

Reflections accumulate. Over time, Claude can trace the evolution of your methodology. You're not just building software. You're building a doctrine.

## The Loop

```
/record          ← enter the confessional (once per project)
  ... work ...
/breakpoint      ← say amen
/reflect         ← receive your sermon
  ... work ...   ← recording continues automatically
/breakpoint      ← say amen again
```

## What Gets Recorded

| Table | The Sacred Record |
|-------|-------------------|
| `breakpoints` | Session boundaries — where one mass ends and another begins |
| `prompts` | Every word you speak to Claude, timestamped for eternity |
| `responses` | Every word Claude speaks back, in full |
| `tool_usage` | Every tool call, file touch, and sub-agent spawn |
| `session_context` | Model, git branch, MCP servers, CLAUDE.md hash |
| `reflections` | The sermons — Claude's analysis of your methodology |

Everything lives in `~/.reflection/history.db` (SQLite). Portable, queryable, and ready for the afterlife.

## What `/reflect` Actually Does

It doesn't summarize your conversation. Any chatbot can do that. It extracts your **methodology**:

- **Your loop** — Do you think first then build, or build first then think? How many rounds of discussion before you commit?
- **Your language** — What phrases signal intent? When you say "what about X?" do you mean "do X" or "I'm exploring"?
- **Your corrections** — When do you push back? What triggers a redirect?
- **Your tool patterns** — Heavy on file reads = exploring. Heavy on writes = building. Heavy on bash = debugging. The tools tell the truth.
- **Your evolution** — How your methodology changes across sessions, across weeks, across projects.

## Why

Because the unexamined prompt is not worth sending.

You're spending hours a day co-thinking with an AI. You've developed a working style — an implicit protocol for how you collaborate with Claude. But you've never articulated it. You've never seen it from the outside.

**confessional** makes the invisible visible. And once you can see your patterns, you can refine them.

Or at least feel smug about them.

## The Liturgical Edition (Optional)

If you've truly converted, you can install the meme aliases alongside the standard commands:

```bash
cp confess.md ~/.claude/commands/
cp amen.md ~/.claude/commands/
cp sermon.md ~/.claude/commands/
```

Then your ritual becomes:

```
/confess         ← kneel and begin
  ... work ...
/amen            ← close the prayer
/sermon          ← receive the word
```

Same functionality, more piety. Both sets can coexist — use whichever matches your current level of devotion.

## Managing Recording

```bash
# Enable recording for a project
python3 ~/.claude/scripts/reflection_db.py enable_recording "<project>"

# Disable recording for a project
python3 ~/.claude/scripts/reflection_db.py disable_recording "<project>"

# Check recording status
python3 ~/.claude/scripts/reflection_db.py is_recording "<project>"

# View stats
python3 ~/.claude/scripts/reflection_db.py stats "<project>"

# Uninstall hooks
python3 ~/.claude/scripts/confessional_hook.py --uninstall
```

## License

MIT.
