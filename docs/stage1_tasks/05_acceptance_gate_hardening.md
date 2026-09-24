# Task 05 — Acceptance gate hardening

## Goal

Make “pass” mean more than “the LLM judge liked the answer”.

## Required gate

A case passes only when:

1. deterministic correctness gates pass, and
2. the commercial-quality judge passes, and
3. there is no material correctness blocker

Deterministic gates should cover the protections added in Task 02: entity, population/category, period, measure/unit, grain/denominator, coverage and evidence trace.

## Judge semantics

Keep the commercial judge focused on:

- commercial objective understood
- evidence relevant
- competing explanations checked when needed
- conclusion supported
- uncertainty respected
- useful next step
- clear concise owner-facing answer

Separate **material blockers** from **non-blocking warnings/style suggestions**. A material issue must not coexist with passed=true.

Do not describe an automated pass rate as commercial accuracy without manual review.

## Known regression

The Ocean Wash case must not receive a passing result if the answer attributes whole-inventory excess to the named product.

## Likely files

evals/stage1.py, commercial/v2_runtime.py or a reusable validation module, pages/2_Stage_1_Checks.py, and evaluation tests.

## Acceptance tests

- A syntactically valid but wrong-scope answer fails deterministically.
- A numerically supported answer with a material semantic blocker fails.
- Style-only warnings can coexist with pass.
- The result object clearly records deterministic gate status, judge status and material warnings separately.
- Existing downloadable JSON remains inspectable.

## Stop condition

No broad live run. Stop after local evaluator tests pass.
