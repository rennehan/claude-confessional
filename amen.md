---
description: Say amen — close this session and mark a new breakpoint
---

# Amen

Close the current work session. This creates an internal breakpoint so the next `/reflect` (or `/sermon`) knows where this session ended.

## Steps

1. Determine the project:
```bash
basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
```

2. If the user provided a note with this command (as $ARGUMENTS), use it. Otherwise, generate a brief one-line summary of what was accomplished this session.

3. Create the breakpoint:
```bash
python3 ~/.claude/scripts/confessional_store.py breakpoint "<project>" "<note>"
```

4. Report to the user:
   - Session closed
   - The note summarizing what was accomplished
   - Remind them they can use `/reflect` (or `/sermon`) to analyze their methodology
