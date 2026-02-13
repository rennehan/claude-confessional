---
description: Begin confession — start recording your prompts to the eternal ledger
---

# Record

You are now in **recording mode** for this session. Your job is to record every interaction to the reflection database.

## Setup

1. Determine the project path stub by running:
```bash
basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
```

2. Initialize the database:
```bash
python3 ~/.claude/scripts/reflection_db.py init "<project>"
```

3. Capture session context:
```bash
python3 ~/.claude/scripts/reflection_db.py record_session_context "<project>" \
  "<model_name>" \
  "$(git branch --show-current 2>/dev/null || echo 'no-git')" \
  "$(git rev-parse --short HEAD 2>/dev/null || echo 'no-git')" \
  "<comma-separated list of active MCP servers>" \
  "$(md5sum CLAUDE.md 2>/dev/null | cut -d' ' -f1 || echo 'none')"
```

4. Confirm recording is active by reporting the project name and current breakpoint.

## Recording Protocol

From this point forward, for EVERY user prompt in this conversation:

1. **Record the user's prompt** immediately when you receive it:
```bash
python3 ~/.claude/scripts/reflection_db.py record_prompt "<project>" "<the user's full prompt text>"
```

2. **Do your normal work** — answer the question, write code, whatever is asked.

3. **Record tool usage** for each tool you invoke during your work:
```bash
python3 ~/.claude/scripts/reflection_db.py record_tool "<project>" "<prompt_id>" \
  "<tool_name>" "<brief input summary>" "<comma-separated files touched>" \
  "<true if subagent, false otherwise>" "<subagent task description if applicable>" \
  "<subagent result summary if applicable>" "<duration_ms if known>"
```

Tool names to record: Read, Write, Edit, Bash, WebSearch, WebFetch, Spawn (for sub-agents), and any MCP tool calls. For sub-agents, set is_subagent to "true" and include the task and result summary.

4. **Record your full response** after you've completed your work:
```bash
python3 ~/.claude/scripts/reflection_db.py record_response "<project>" "<prompt_id from step 1>" "<your full response text>"
```

## Important

- Record EVERY interaction, no exceptions.
- The prompt text should be the user's exact words.
- The response text should be your complete response.
- Escape quotes and special characters properly when passing to the shell.
- If the prompt_id is returned as JSON like `{"prompt_id": 5}`, extract the number.
- Do NOT mention the recording to the user unless they ask. Just do your work normally while silently recording.
- If the DB doesn't exist yet, init will create it automatically.
