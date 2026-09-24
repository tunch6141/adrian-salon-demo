# Stage 1 finalisation task index

Use these tasks sequentially. Each task is intentionally small enough to implement, test and review before proceeding.

| Task | Goal | Live-model use | Status |
|---|---|---:|---|
| 01 | Working Business Context before evidence planning; target/baseline semantics | None expected | Pending |
| 02 | Named-entity and evidence-scope deterministic guardrails | None expected | Pending |
| 03 | Safe dynamic calculations, including same-lead-time booking pace | None expected | Pending |
| 04 | Investigation stopping rule and simple owner answer contract | 2–3 focused checks only after unit tests | Pending |
| 05 | Stronger deterministic + LLM acceptance gate | None expected initially | Pending |
| 06 | Multi-turn follow-up checks harness with saved state and JSON diagnostics | Focused chain runs | Pending |
| 07 | Boundary and hallucination checks harness | Focused boundary runs | Pending |
| 08 | Focused regression, one 23-case run, repeatability and final report | Final planned live budget | Pending |

## Working rule

After each task:

1. Run its local/unit acceptance tests.
2. Report files changed and test results.
3. Stop for review.
4. Only then proceed to the next task.

Do not combine multiple tasks into a large refactor unless the owner explicitly approves it.
