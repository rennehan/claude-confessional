---
description: Start recording prompts and responses to the reflection database
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
  "$(md5sum CLAUDE.md 2>/dev/null | cut -d' ' -f1 || md5 -q CLAUDE.md 2>/dev/null || echo 'none')"
```

4. Confirm recording is active by reporting the project name and current breakpoint.

## Recording Protocol

From this point forward, for EVERY user prompt in this conversation:

1. **Do your normal work** — answer the question, write code, whatever is asked. As you work, mentally note every tool you invoke (tool name, files touched, whether it's a sub-agent).

2. **Record the entire interaction** at the END of your response with a single call. Build a JSON object with the user's prompt, your full response, and all tool usage, then pass it via `--stdin`:
```bash
python3 ~/.claude/scripts/reflection_db.py record_interaction "<project>" --stdin <<'CONFESSIONAL_EOF'
{
  "prompt": "<the user's full prompt text>",
  "response": "<your full response text>",
  "tools": [
    {
      "tool_name": "<Read|Write|Edit|Bash|WebSearch|WebFetch|Spawn|etc>",
      "input_summary": "<brief description of what was done>",
      "files_touched": "<comma-separated file paths>",
      "is_subagent": false,
      "subagent_task": "",
      "subagent_result_summary": "",
      "duration_ms": 0
    }
  ]
}
CONFESSIONAL_EOF
```

For sub-agents, set `is_subagent` to `true` and include the task and result summary.

## Important

- Record EVERY interaction, no exceptions.
- The prompt text should be the user's exact words.
- The response text should be your complete response.
- Always use `--stdin` with a single-quoted heredoc delimiter (`<<'CONFESSIONAL_EOF'`) to pass the JSON. This prevents shell expansion of special characters.
- Escape double quotes, backslashes, and newlines within JSON string values. Use `\n` for newlines, `\"` for quotes, `\\` for backslashes.
- Do NOT mention the recording to the user unless they ask. Just do your work normally while silently recording.
- If the DB doesn't exist yet, init will create it automatically.
