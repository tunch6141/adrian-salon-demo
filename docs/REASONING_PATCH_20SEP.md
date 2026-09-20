# Commercial question handling — 20 September 2026

The owner reported that ordinary booking, staff, trend and comparison questions retrieved incomplete evidence or lost their written answers. A daily staff result was incorrectly compared with a weekly average, and the next question lost the earlier person/period.

## Changes

- GPT-4.1 mini selects a booking lookup, revenue total, calendar trend, staff diagnostic, recorded-context lookup, or read-only cleaned-data SQL fallback. The configured model is unchanged.
- Complete cleaned booking records are available to the analyst. Exact booking IDs take precedence; a shortened zero-padded ID resolves only if unique, with both requested and actual identifiers returned.
- The model routes an individual booking request; the app displays exact record fields directly, avoiding paraphrased IDs, names or timestamps. Booking calendar queries use the business-local appointment date.
- Calendar trends include the whole requested interval, real bucket dates, clipped edge periods and coverage labels. Main-answer tables no longer truncate to ten rows.
- Staff comparisons include calculated differences. Period comparisons reject unequal duration after baseline averaging; complete calendar months remain supported. An invalid optional baseline does not suppress the valid current-period answer.
- Optional cost/capacity diagnostics do not block basic revenue. Recent conversation includes prior scope and execution limitations, even if narration was withheld. All follow-up figures are retrieved again.
- A reasoning graph maps existing metric families to core data, primary/cross-module diagnostics, commercial caveats and missing-data fallbacks. This implements the supplied patch's Calculate / Diagnose / Commercial separation without creating new metric families. It guides relevant investigations; it does not pretend every optional check ran.
- Business context is retrieved before analytical narration and review, using the actual metric period and each selected staff member. A context-only reading request displays the original notes and dates without a dummy SQL query or model paraphrase. Notes remain owner-reported and cannot change calculated results.
- Exactly copied cited values can be canonicalised to evidence slots. Fabricated values, uncited numbers, wrong references and unsupported meanings remain checked. The reviewer can remove an unsupported statement while retaining valid findings.
- Structured response schemas constrain each citation to an existing result, row and column, and context citations to retrieved notes. Claim prose must use evidence slots for digits. Trend summaries calculate full-period extrema, first/last changes and fluctuation patterns; partial edge periods cannot establish a full-week comparison.

## Preserved constraints

Only the saved cleaned snapshot is loaded into the analyst's read-only database. SQL is restricted to approved entitled views, one table per query, bounded result sizes and no model-written code. Raw batches, saved decisions and audit history are unchanged by analysis. Proposed commercial actions are not executed automatically.

Revising a past cleaning approval is deferred in `BACKLOG.md` at the owner's request. This patch does not change the saved Sarah correction.

## Verification

Automated regression coverage includes corrected booking lookup, ambiguous short IDs, full May–August weekly aggregation, single-day figures, two-staff difference, invalid baseline rejection, absent capacity, context-only reading, read-only queries and fabricated citation rejection. Live GPT-4.1 mini acceptance results are recorded after deployment below.
