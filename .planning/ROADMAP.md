# Roadmap

## Recording Fidelity

- [x] **Harden `parse_last_turn` for structured user content** — Handle multi-part user messages (images, skill expansions, system injections) instead of returning empty string for non-string content
- [x] **Capture full response narrative with tool call ordering** — turn_blocks table preserves interleaved text/tool_use/tool_result sequence per turn
- [x] **Fix empty response recording** — Turns where Claude only makes tool calls (no text blocks) now record a synthetic summary like `[tool-only turn: Read, Edit]`
- [ ] **Add deduplication** — Prevent the same turn from being recorded twice across sessions or hook re-fires (e.g. track transcript offset or prompt hash)

## Error Handling & Observability

- [x] **Add hook error logging** — Errors in handle_stop and handle_session_start now logged to `~/.reflection/hook.log` via get_logger(); exit-0 behavior preserved
- [ ] **Fill `session_context.model` from hooks** — The `SessionStart` payload doesn't include model name, so it's always empty; find an alternative source or accept the gap and document it

## Data Model

- [x] **Add sequence ordering to tool calls and response blocks** — Implemented via turn_blocks table with sequence column; get_turn_blocks retrieves ordered blocks grouped by prompt_id
- [ ] **Revisit breakpoint semantics** — If a user never calls `/breakpoint`, reflections span unbounded time; consider auto-breakpoints on session boundaries (SessionStart hook) or a time-based heuristic

## Reflection Quality

- [ ] **Include tool call ordering in reflection data** — Update `get_tools_since_breakpoint` and `get_all_since_breakpoint` to return sequenced, interleaved turn data so `/reflect` can analyze reasoning flow
- [ ] **Cross-session reflection** — Allow `/reflect` to compare across multiple breakpoint windows, not just the current one, for methodology evolution analysis

## Housekeeping

- [ ] **Add `recording_state` table to README** — Minor omission in the "What Gets Recorded" table
- [ ] **Add `.planning/` to `.gitignore`** — Keep planning artifacts local
