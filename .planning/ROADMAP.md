# Roadmap

## Recording Fidelity

- [x] **Harden `parse_last_turn` for structured user content** — Handle multi-part user messages (images, skill expansions, system injections) instead of returning empty string for non-string content
- [ ] **Capture full response narrative with tool call ordering** — Preserve the interleaved sequence of text blocks and tool calls so reflections can see "Claude said X, called tool Y, then said Z"
- [x] **Fix empty response recording** — Turns where Claude only makes tool calls (no text blocks) now record a synthetic summary like `[tool-only turn: Read, Edit]`
- [ ] **Add deduplication** — Prevent the same turn from being recorded twice across sessions or hook re-fires (e.g. track transcript offset or prompt hash)

## Error Handling & Observability

- [ ] **Add hook error logging** — Write failures to `~/.reflection/hook.log` instead of swallowing all exceptions silently; keep exit-0 behavior so Claude is never blocked
- [ ] **Fill `session_context.model` from hooks** — The `SessionStart` payload doesn't include model name, so it's always empty; find an alternative source or accept the gap and document it

## Data Model

- [ ] **Add sequence ordering to tool calls and response blocks** — Add an `ordinal` column (or equivalent) so the chronological relationship between text and tool use within a turn is preserved in the DB
- [ ] **Revisit breakpoint semantics** — If a user never calls `/breakpoint`, reflections span unbounded time; consider auto-breakpoints on session boundaries (SessionStart hook) or a time-based heuristic

## Reflection Quality

- [ ] **Include tool call ordering in reflection data** — Update `get_tools_since_breakpoint` and `get_all_since_breakpoint` to return sequenced, interleaved turn data so `/reflect` can analyze reasoning flow
- [ ] **Cross-session reflection** — Allow `/reflect` to compare across multiple breakpoint windows, not just the current one, for methodology evolution analysis

## Housekeeping

- [ ] **Add `recording_state` table to README** — Minor omission in the "What Gets Recorded" table
- [ ] **Add `.planning/` to `.gitignore`** — Keep planning artifacts local
