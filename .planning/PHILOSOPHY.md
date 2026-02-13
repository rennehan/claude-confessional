# Development Philosophy

## The Cycle

Every piece of work follows this loop:

1. **Explore** — Understand before building. Read the code, trace the data flow, identify the real problem. Never guess.
2. **Establish** — Set process expectations once. Define what "done" looks like, what tests cover, what the commit boundary is.
3. **Execute** — Be terse, trust the process. Write tests first, then the minimum code to pass them. No commentary, no over-engineering.
4. **Verify** — Critical review after each cycle. Run tests, check coverage, read the diff. Does this actually solve the problem?
5. **Correct** — Fix concepts, not just symptoms. If a test failure reveals a misunderstanding, go back to Explore. Don't patch around it.

## TDD as the Spine

- Tests are written **before** implementation code. Always.
- Tests define the contract. If you can't write a test for it, you don't understand it yet.
- Test coverage is maximized — not for vanity, but because untested code is unverified code.
- Tests inform implementation quality. If tests are hard to write, the design is wrong.
- Failing tests are the only valid reason to write production code.

## Commit Discipline

- Commit after each completed cycle (test + implementation passing together).
- Push as you go. Small, frequent commits > large batches.
- Each commit should be independently coherent — tests pass, no broken intermediate states.

## Code Values

- **Minimum necessary complexity.** Three similar lines > premature abstraction.
- **No speculative features.** Build for the current requirement, not hypothetical futures.
- **No data duplication.** Read from the source of truth (native JSONL) on-demand. Only store what's unique to this tool (breakpoints, reflections, recording state).
- **Plain text over databases.** JSON and JSONL files are human-readable, LLM-loadable, crash-safe (append-only), and need no driver or schema. SQLite is overkill for a few KB of metadata.
- **Silent correctness.** Hooks exit 0. Errors log, never block. The tool serves the user, not the other way around.
