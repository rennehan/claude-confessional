---
description: Say amen — close this session and mark a new breakpoint
---

# Breakpoint

Create a new breakpoint in the reflection database. A breakpoint marks the boundary between work sessions, allowing /reflect to analyze discrete chunks of work.

## Steps

1. Determine the project path stub:
```bash
basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
```

2. If the user provided a note with this command (as $ARGUMENTS), use it. Otherwise, generate a brief one-line summary of what was accomplished since the last breakpoint by checking recent interactions:
```bash
python3 ~/.claude/scripts/reflection_db.py get_all_since_breakpoint "<project>"
```

3. Create the breakpoint:
```bash
python3 ~/.claude/scripts/reflection_db.py breakpoint "<project>" "<note>"
```

4. Report to the user:
   - Breakpoint ID and timestamp
   - The note
   - How many prompts/responses were in the completed window
   - A one-line summary of what that window covered
