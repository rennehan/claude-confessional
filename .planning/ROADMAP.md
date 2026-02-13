# Roadmap

## Pure JSON Redesign (Completed)

- [x] **Build `transcript_reader.py`** — Reads Claude Code's native JSONL transcripts on-demand, extracts structured turns, tools, token metrics, session metadata
- [x] **Build `confessional_store.py`** — Pure JSON/JSONL storage for breakpoints, reflections, recording state. No SQL.
- [x] **Slim `confessional_hook.py`** — SessionStart hook only. Removed Stop hook and all per-turn recording logic.
- [x] **Update all commands** — reflect.md, sermon.md, record.md, confess.md, breakpoint.md, amen.md now use `confessional_store.py` and `transcript_reader.py`
- [x] **Delete old code** — Removed `reflection_db.py` (SQLite) and all associated tests
- [x] **95% test coverage** — 95 tests across 4 test files

## Previous Work (Superseded by Redesign)

- [x] Harden `parse_last_turn` for structured user content — *moved to transcript_reader.py*
- [x] Capture full response narrative with tool call ordering — *built into parse_session*
- [x] Fix empty response recording — *tool-only turns get synthetic summary*
- [x] Add deduplication — *no longer needed (JSONL is source of truth)*
- [x] Add hook error logging — *preserved in slimmed hook*
- [x] Add sequence ordering to tool calls and response blocks — *built into parse_session blocks*
- [x] Revisit breakpoint semantics — *auto-breakpoints on SessionStart when >4h stale*
- [x] Include tool call ordering in reflection data — *turn blocks with sequence in parse_session*
- [x] Cross-session reflection — *get_reflections_summary in confessional_store*

## Voice Analysis Engine (Completed)

- [x] **`session_id` on turns** — Each turn carries its session ID for cross-session boundary detection
- [x] **`compute_prompt_linguistics`** — Question ratio, imperative ratio, n-gram extraction, certainty markers, agency framing, prompt length distribution by position (25 tests)
- [x] **`compute_effectiveness_signals`** — Correction detection, per-style effectiveness (question/imperative/statement), tool scatter, session progression with warming-up detection (19 tests)
- [x] **Wired into `get_turns_since` + CLI** — Both analysis layers auto-computed and included in `analyze` and `stats` output (5 tests)
- [x] **Voice Analysis in reflect.md / sermon.md** — Signature phrases, communication mode, certainty profile, effectiveness correlation, tool scatter, session arc
- [x] **Smoke tests updated** — `compute_prompt_linguistics` and `compute_effectiveness_signals` importable

## HTML Dashboard (Completed)

- [x] **`breakpoint_id` on reflections** — Explicit link between reflections and the breakpoint they cover (backward-compatible)
- [x] **Dashboard manifest** — `dashboards/manifest.jsonl` tracks generated HTML files per project
- [x] **`dashboard_generator.py`** — Pure-CSS HTML renderer: session dashboards with bar charts, summary cards, tables; master index with breakpoint/reflection status (28 tests)
- [x] **Session dashboard** — Self-contained HTML per reflection: tool usage, prompt effectiveness, voice profile, session arc, n-grams, token breakdown
- [x] **Master index** — `index.html` listing all breakpoints with reflection status and links to session dashboards
- [x] **Integrated into `/reflect`** — Dashboard generation is Step 5 of the reflect workflow, no separate command
- [x] **Smoke tests updated** — `dashboard_generator` importable with key functions

## Future

- [ ] **Migration tool** — Script to migrate existing SQLite data to JSONL (for users upgrading from v1)
- [ ] **Token budget tracking** — Track cumulative token spend per project across reflections
- [ ] **Reflection diffing** — Compare methodology across reflections to surface evolution patterns
- [ ] **Multi-project dashboard** — Aggregate patterns across projects (extend dashboard_generator.py)
