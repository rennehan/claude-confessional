---
description: Receive your sermon — analyze your prompting patterns and methodology
---

# Reflect

Analyze all interactions since the last breakpoint to extract the user's prompting methodology, patterns, and thinking style. The goal is NOT to summarize what was discussed — it's to understand HOW the user works with Claude and extract their methodology.

## Steps

### 1. Gather Data

Determine the project:
```bash
basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
```

Pull all interactions in the current window:
```bash
python3 ~/.claude/scripts/reflection_db.py get_all_since_breakpoint "<project>"
```

Pull tool usage data:
```bash
python3 ~/.claude/scripts/reflection_db.py get_tools_since_breakpoint "<project>"
```

Pull session context:
```bash
python3 ~/.claude/scripts/reflection_db.py get_session_context "<project>"
```

Pull git history since the last breakpoint timestamp (if in a git repo):
```bash
git log --since="<breakpoint_timestamp>" --oneline --stat
```

Also pull the diff summary:
```bash
git diff --stat <earliest_relevant_commit>..HEAD
```

### 2. Analyze the Methodology

Study the prompts and responses together. Extract:

**The Loop** — What is the user's iterative cycle? Do they:
- Think first, then build? Or build first, then think?
- Start broad and narrow down? Or start specific and generalize?
- Design → implement → test → reflect? Or some other pattern?
- How many rounds of discussion before committing to action?

**Prompting Style** — How does the user communicate intent?
- Common phrases and what they signal (e.g., "let's think more" = not ready to commit, "this is fine" = move on, "what about X?" = exploring alternatives)
- Level of specificity — do they give detailed specs or high-level direction?
- How do they correct course — explicit redirection or subtle hints?
- Do they ask questions or make statements?

**Thinking Patterns** — What's the user's cognitive approach?
- Do they reason by analogy? By reduction to first principles? By example?
- What triggers them to push back on Claude's suggestions?
- What makes them satisfied with an answer vs. wanting to go deeper?
- Are they building toward a specific vision or exploring?

**Collaboration Dynamic** — How do they use Claude?
- As a thinking partner (discussion) vs. executor (do this)?
- Ratio of conceptual/design work to implementation work
- Do they validate Claude's reasoning or take it at face value?
- How do they handle disagreement?

**Code Outcomes** (from git history) — What actually got built?
- What was the tangible output of this session?
- How does the discussion map to the code changes?
- Was there wasted effort — discussion that didn't lead to action?

**Tool Behavior** (from tool usage data) — How was Claude used as a tool?
- What's the ratio of file reads to writes? (exploration vs. implementation)
- How much bash usage? (debugging, testing, building)
- Were sub-agents spawned? For what tasks? Did they succeed?
- What files were touched most frequently? Where was the focus?
- Tool density per prompt — some prompts trigger 10 tool calls, others zero. What does that say about the prompt?

**Session Context** — What was the environment?
- What model was used? Any MCP tools available?
- Did the CLAUDE.md change during the session?
- What branch was work happening on?

### 3. Produce the Reflection

Write a reflection that captures the methodology, not the content. Structure it as:

1. **Session Overview** — One paragraph: what was the goal and what was achieved
2. **The Loop** — The user's iterative pattern this session
3. **Key Prompting Patterns** — Specific phrases and behaviors with examples
4. **Thinking Style** — How the user reasons and makes decisions
5. **What Worked** — Moments where the collaboration was most productive
6. **What Didn't** — Moments of friction, miscommunication, or wasted cycles
7. **Methodology Extract** — A concise, reusable description of this user's working style that could inform future sessions

### 4. Store and Present

Store the reflection:
```bash
python3 ~/.claude/scripts/reflection_db.py store_reflection "<project>" "<reflection_text>" "<git_summary>" <prompt_count>
```

Check if there are previous reflections:
```bash
python3 ~/.claude/scripts/reflection_db.py get_reflections "<project>"
```

If previous reflections exist, also note:
- How the methodology is evolving over time
- Whether patterns are becoming more refined or shifting
- Any emerging meta-patterns across sessions

Present the full reflection to the user.
