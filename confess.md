---
description: Begin confession — start recording your prompts to the eternal ledger
---

# Record

Enable recording for this project. Once enabled, breakpoints are automatically
managed via system hooks. Conversation data is read from Claude Code's native
transcripts on-demand — no per-turn recording overhead.

## Steps

1. Determine the project path stub:
```bash
basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
```

2. Initialize recording and create the first breakpoint:
```bash
python3 ~/.claude/scripts/confessional_store.py init "<project>"
```

3. Confirm to the user:
   - Recording is now active for **<project>**
   - Conversation data is automatically captured by Claude Code
   - Use `/breakpoint` (or `/amen`) to mark session boundaries
   - Use `/reflect` (or `/sermon`) to analyze patterns
   - Recording persists across sessions until explicitly disabled

## Notes

- Recording is **per-project** and persists across Claude Code sessions.
- No per-turn overhead — data lives in Claude Code's native JSONL transcripts.
- Auto-breakpoints are created when sessions are >4 hours apart.
- To stop recording: `python3 ~/.claude/scripts/confessional_store.py disable_recording "<project>"`
