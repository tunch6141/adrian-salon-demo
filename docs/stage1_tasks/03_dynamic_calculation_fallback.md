# Task 03 — Safe dynamic calculation fallback and booking pace

## Goal

Let GPT-5.4 Mini request useful calculations that are not already precomputed without creating a permanent metric for every possible owner question.

## Required architecture

Use a hybrid approach:

- the model decides what evidence is needed
- a trusted structured calculation layer performs the calculation from canonical clean data
- the request/result contract preserves entity, period, category, grain and units
- no unrestricted arbitrary Python execution is exposed to the model

Prefer extending reusable deterministic calculation capabilities over creating question-specific tools.

## First required capability

Support a generic **same-lead-time booking pace versus N prior comparable weeks** calculation.

The result should expose comparable periods as rows or another generic structure, not hardcoded fields such as two_weeks_ago_hours, three_weeks_ago_hours, etc.

This must support follow-ups such as:

- compare next week with last week at the same lead time
- compare next week with the recent four-week booking pace
- show which staff member is furthest behind their own recent pace

Do not compare a future schedule snapshot with a completed historical outcome when that is not like-for-like.

## Likely files

commercial/v2_data.py, commercial/v2_models.py, analytics/calculations.py, analytics/views.py and tests/test_commercial_v2.py.

## Acceptance tests

- Next-week booking pace can be compared with one prior comparable week at the same lead time.
- The same function can return N prior comparable weeks without adding week-specific columns.
- The four-week baseline is calculated as recent normal performance, not labelled as a target.
- Entity/staff filters remain intact.
- No overlapping future horizons are added together.
- The calculation is deterministic and does not require an LLM to do arithmetic.

## Stop condition

Local tests only. Do not run the full behavioural suite.
