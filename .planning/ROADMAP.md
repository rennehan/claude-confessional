# Roadmap

## Recording Fidelity

- [x] **Harden `parse_last_turn` for structured user content** — Handle multi-part user messages (images, skill expansions, system injections) instead of returning empty string for non-string content
- [x] **Capture full response narrative with tool call ordering** — turn_blocks table preserves interleaved text/tool_use/tool_result sequence per turn
- [x] **Fix empty response recording** — Turns where Claude only makes tool calls (no text blocks) now record a synthetic summary like `[tool-only turn: Read, Edit]`
- [x] **Add deduplication** — transcript_offset tracked per prompt; duplicate offsets skipped in record_interaction

## Error Handling & Observability

- [x] **Add hook error logging** — Errors in handle_stop and handle_session_start now logged to `~/.reflection/hook.log` via get_logger(); exit-0 behavior preserved
- [x] **Fill `session_context.model` from hooks** — Accepted gap: model is only populated when `/record` is explicitly run. SessionStart payload doesn't include it. Documented in PLAN.md.

## Data Model

- [x] **Add sequence ordering to tool calls and response blocks** — Implemented via turn_blocks table with sequence column; get_turn_blocks retrieves ordered blocks grouped by prompt_id
- [x] **Revisit breakpoint semantics** — Auto-breakpoint created on SessionStart when last breakpoint is >4 hours old; prevents unbounded reflection windows

## Reflection Quality

- [x] **Include tool call ordering in reflection data** — get_all_since_breakpoint now includes turn_blocks; reflect.md pulls get_turn_blocks for reasoning flow analysis
- [x] **Cross-session reflection** — get_reflections_summary added; reflect.md pulls previous reflections and includes Methodology Evolution section

## Housekeeping

- [x] **Add `recording_state` table to README** — Added to "What Gets Recorded" table
- [x] **`.planning/` directory** — Kept git-tracked intentionally as project reference
