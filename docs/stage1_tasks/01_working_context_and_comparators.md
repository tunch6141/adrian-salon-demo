# Task 01 — Working Business Context and comparator semantics

## Goal

Make relevant business context available **before** Stage 1 commits to its evidence/calculation plan, while keeping Stage 2 durable memory out of scope.

## Current gap

commercial/v2_runtime.py currently calls frame_question first and only then retrieves context_candidates(...) using the resolved scope. Context can influence later investigation, but it cannot reliably influence the initial commercial framing or evidence plan.

## Required behaviour

- Introduce a bounded read-only **Working Business Context** object/interface.
- Assemble relevant context from the existing Business Context Log before the system commits to its evidence/calculation plan.
- A lightweight question-level retrieval followed by one bounded refinement after tentative framing is acceptable, but relevant context must be present before evidence planning begins.
- Preserve provenance/applicability where available: source, entity, affected topic/metric, dates, status and whether a record represents an owner report, definition, business rule or explicit KPI target.
- Existing context rows may not contain every structured field. Do not invent missing metadata. Preserve absent/unknown values cleanly.
- Design the read contract so future Stage 2 memory retrieval can populate the same object.
- Do not build memory writing, embeddings, issue lifecycle, scheduled reviews or proactive monitoring.

## Comparator semantics

Implement and document the hierarchy:

1. Relevant current owner-defined KPI target, if present.
2. Otherwise recent comparable business performance as baseline.
3. External benchmark only when an approved external source exists.

Keep all three concepts separate. A four-week baseline must never be silently labelled a target.

For weekly operational metrics, support a recent baseline defined as the previous four completed comparable weeks, with same elapsed weekdays or same lead-time position where commercially appropriate.

## Likely files

Inspect first. Likely touch points include commercial/v2_runtime.py, commercial/v2_models.py, commercial/v2_prompts.py, analytics/runtime.py, business_context.py and tests/test_commercial_v2.py.

Do not change the persistent context schema unless it is genuinely necessary.

## Acceptance tests

Add deterministic tests proving:

- A relevant owner-defined term/rule can influence framing before the first data request.
- With no utilisation target, the runtime does not invent 80/85/90%; it uses recent comparable performance when a comparator is needed.
- With an explicit current owner target, target attainment can be evaluated against that target while the four-week baseline remains separately available.
- An owner-reported explanation can influence hypotheses but cannot itself satisfy a causal evidence claim.
- Unknown/missing context fields remain unknown rather than guessed.
- The Working Business Context object can accept a future additional source without changing the core investigation contract.

## Stop condition

Stop after local tests pass. Do not run the 23-case suite.
