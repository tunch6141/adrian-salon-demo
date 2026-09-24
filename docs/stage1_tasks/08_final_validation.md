# Task 08 — Targeted validation, repeatability and final promotion decision

## Preconditions

Tasks 01–07 are complete and reviewed.

## Phase A — focused live repair verification

Run only representative high-risk cases first:

- Ocean Wash named-product scope
- next-week vs prior comparable week at same lead time
- changed staff root-cause continuation
- no-target utilisation baseline
- owner-defined utilisation target
- context-before-planning
- one missing-internal-evidence boundary case
- one external-data boundary case
- one follow-up chain

If a foundational issue remains, stop and report. Do not continue to the broad suite.

## Phase B — broad verification

After the focused cases pass:

- run the 23-case GPT-5.4 Mini generalisation suite **once**
- manually review high-risk named-entity, changed-data, unseen, capacity, staff and customer-return cases
- retain the full downloadable JSON

Do not report 23/23 as commercial accuracy unless manual review supports it.

## Phase C — repeatability

Repeat only a small critical set 2–3 times. Suggested coverage:

- revenue diagnosis
- capacity/booking pace
- staff root cause
- named product scope
- customer returns
- one unseen question
- one follow-up chain

Assess whether the material conclusion, scope and evidence selection remain correct even when wording varies.

## Final report

Write a concise final acceptance report containing:

- commit/model/reasoning configuration
- focused test outcomes
- 23-case automated result
- manual-review overrides
- follow-up and boundary suite results
- repeatability findings
- runtime and AI-call counts
- input/output token totals
- known remaining limitations
- recommendation to keep preview isolated or promote

## Promotion rule

Do not promote Stage 1 Preview into normal chat until the owner explicitly accepts the final report.
