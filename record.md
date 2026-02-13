---
description: Start recording prompts and responses to the reflection database
---

# Record

Enable automatic recording for this project. Once enabled, all interactions are
recorded silently via system hooks — no per-turn action required.

## Steps

1. Determine the project path stub:
```bash
basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
```

2. Initialize the database and enable recording:
```bash
python3 ~/.claude/scripts/reflection_db.py init "<project>"
python3 ~/.claude/scripts/reflection_db.py enable_recording "<project>"
```

3. Record session context for this session:
```bash
python3 ~/.claude/scripts/reflection_db.py record_session_context "<project>" \
  "<model_name>" \
  "$(git branch --show-current 2>/dev/null || echo 'no-git')" \
  "$(git rev-parse --short HEAD 2>/dev/null || echo 'no-git')" \
  "<comma-separated list of active MCP servers>" \
  "$(md5sum CLAUDE.md 2>/dev/null | cut -d' ' -f1 || md5 -q CLAUDE.md 2>/dev/null || echo 'none')"
```

4. Confirm to the user:
   - Recording is now active for **<project>**
   - All interactions will be automatically recorded via system hooks
   - Use `/breakpoint` (or `/amen`) to mark session boundaries
   - Use `/reflect` (or `/sermon`) to analyze patterns
   - Recording persists across sessions until explicitly disabled

## Notes

- Recording is **per-project** and persists across Claude Code sessions.
- The system hooks handle all recording automatically — no manual action needed per turn.
- To stop recording: `python3 ~/.claude/scripts/reflection_db.py disable_recording "<project>"`
