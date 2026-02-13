---
description: Say amen — close this session and mark a new breakpoint
---

# Breakpoint

Create a new breakpoint. A breakpoint marks the boundary between work sessions, allowing /reflect to analyze discrete chunks of work.

## Steps

1. Determine the project:
```bash
basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
```

2. If the user provided a note with this command (as $ARGUMENTS), use it. Otherwise, generate a brief one-line summary of what was accomplished since the last breakpoint.

3. Create the breakpoint:
```bash
python3 ~/.claude/scripts/confessional_store.py breakpoint "<project>" "<note>"
```

4. Report to the user:
   - Breakpoint ID and timestamp
   - The note
   - A one-line summary of what the completed window covered
