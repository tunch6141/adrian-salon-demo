# Commercial question handling — 20 September 2026

The owner reported that ordinary booking, staff, trend and comparison questions retrieved incomplete evidence or lost their written answers. A daily staff result was incorrectly compared with a weekly average, and the next question lost the earlier person/period.

## Changes

- GPT-4.1 mini selects a booking lookup, revenue total, calendar trend, staff diagnostic, recorded-context lookup, or read-only cleaned-data SQL fallback. The configured model is unchanged.
- Complete cleaned booking records are available to the analyst. Exact booking IDs take precedence; a shortened zero-padded ID resolves only if unique, with both requested and actual identifiers returned.
- The model routes an individual booking request; the app displays exact record fields directly, avoiding paraphrased IDs, names or timestamps. Booking calendar queries use the business-local appointment date.
- Calendar trends include the whole requested interval, real bucket dates, clipped edge periods and coverage labels. Main-answer tables no longer truncate to ten rows. Equivalent model-written revenue time-series queries are promoted to this module after inspecting the SQL structure; queries with extra filters or metrics retain the general fallback. A request to show a trend displays the calculated summary and chart directly. A request to explain it can use deeper analysis.
- Staff numerical results and matched baseline figures are displayed directly from the calculation module; GPT supplies evidence-linked qualitative interpretation and proposed actions. This prevents a narration reference error from turning a record ID into an amount or an amount into a percentage. Staff comparisons include calculated differences. Period comparisons reject unequal duration after baseline averaging; complete calendar months remain supported. An invalid optional baseline does not suppress the valid current-period answer.
- Optional cost/capacity diagnostics do not block basic revenue. Recent conversation includes owner questions, prior calculation scopes and execution limitations, even if narration was withheld. Old model prose is excluded so a mistaken phrase is not recycled into new answers. New analytical follow-up figures are retrieved again; a question about the previous calculation reads its recorded scope.
- A reasoning graph maps existing metric families to core data, primary/cross-module diagnostics, commercial caveats and missing-data fallbacks. This implements the supplied patch's Calculate / Diagnose / Commercial separation without creating new metric families. It guides relevant investigations; it does not pretend every optional check ran.
- Explicitly named staff in a new straightforward request replace people carried over from a prior comparison; comparisons, exclusions and pronoun-based follow-ups retain semantic planning.
- Business context is retrieved before analytical narration and review, using the actual metric period and each selected staff member. A context-only route can display original notes and dates directly; combined analytical answers cite retrieved notes. Notes remain owner-reported and cannot change calculated results. The structured response must assess every retrieved context note. The app validates note IDs, requires relevant temporary leave/closure context to be addressed, and exposes the assessments under “How business context was considered”. Service-mix comparisons now calculate the matching baseline average and differences, rather than letting a weekly answer use raw multi-week category totals.
- Exactly copied cited values can be canonicalised to evidence slots. Fabricated values, uncited numbers, wrong references and unsupported meanings remain checked. Uncited asides are omitted; the reviewer still checks the supported findings and can remove an unsupported statement without discarding valid findings.
- Structured responses express sentences as prose parts and direct value references. Each displayed value names its actual result/row/column; period years and context dates have distinct reference types. The app builds internal evidence slots itself, so the model cannot accidentally number a year as a booking count. Schemas restrict references to available fields and notes, and restrict monetary/percentage/plain formatting to matching field types. Trend summaries calculate full-period extrema, first/last changes and fluctuation patterns; partial edge periods cannot establish a full-week comparison.
- Questions about what the previous calculation compared display the recorded calculation scope directly. They do not trigger a new baseline investigation. Unqueried profit cannot be labelled missing when scoped costed sales exist; isolated utilisation has no invented efficiency target.

## Preserved constraints

Booking counts from service-level views must use distinct booking IDs; counting service lines as bookings is rejected and sent through query repair. Invalid optional charts are omitted without discarding a verified explanation.

Only the saved cleaned snapshot is loaded into the analyst's read-only database. SQL is restricted to approved entitled views, one table per query, bounded result sizes and no model-written code. Raw batches, saved decisions and audit history are unchanged by analysis. Proposed commercial actions are not executed automatically.

Revising a past cleaning approval is deferred in `BACKLOG.md` at the owner's request. This patch does not change the saved Sarah correction.

## Verification

Automated regression coverage includes corrected booking lookup, ambiguous short IDs, full May–August weekly aggregation, single-day figures, two-staff difference, invalid baseline rejection, absent capacity, context-only reading, read-only queries and fabricated citation rejection. Live GPT-4.1 mini acceptance results are recorded after deployment below.

## Live acceptance (20 September 2026)

Tested in the deployed Streamlit app with its configured GPT-4.1 mini and saved cleaned version `6e2cc8ae-33aa-4b97-9148-ed42811712d6`. Checks use the actual browser interaction, not mocked model responses.

| Owner question | Observed result |
| --- | --- |
| Show booking B0004 | Resolves unique zero-padding alias to B00004 and shows the corrected Sarah / S01 record; appointment start precedes end. |
| Sarah's performance on 17 September 2026 | AUD 420 service revenue, six appointments, six completed service hours, eight bookable hours, 75% utilisation, AUD 70 per completed service hour; no unsolicited weekly comparison. |
| Are you comparing his one-day revenue with weekly revenue? | Retains Sarah and 17 September, explicitly says the previous calculation used no weekly baseline. |
| Compare Sarah and Matthew's August service revenue | Matthew AUD 12,200; Sarah AUD 11,880, with a written comparison. |
| Sarah's weekly service revenue from May to August | Sarah only, all 19 calendar buckets and chart, total AUD 35,340. Complete weeks range AUD 1,030–2,780 and fluctuate. Partial first/last weeks labelled, not mistaken for full-week declines. |
| Completed August bookings by booking source | Custom cleaned-data SQL fallback gives phone 98, online 82, walk-in 81, with a written explanation. |
| Why Sarah was lower on 7–13 September, and what to do | Exact matching figures: AUD 1,380 versus AUD 2,698.75; change AUD -1,318.75 (-48.87%). Complete qualitative explanation covers completed work, capacity, value per completed hour and service mix. Both owner notes are assessed visibly. Advice checks roster/capacity and booking patterns before changing staffing or pricing. |
| Read Sarah's recorded context for 7–13 September | Retrieves owner-reported leave on 8–9 September and fewer colour packages with no established reason. |

The full regression suite passed 127 tests plus nine subtests. Final release: reasoning 21. Targeted regression checks also passed after each substantive correction. Coverage includes context assessment requirements, formatted value types, raw-baseline exclusion, exact staff calculation display, and optional-chart failure preserving valid findings. Existing NumPy deprecation warnings originate in the legacy demo UI.

Read-only database verification confirms two cleaned versions, two approval events, the same active cleaned version and unchanged raw payload fingerprint (`6709e7484cea9425f96dda003e0d5420`). Analytical tests did not change source data, approval history or owner notes.

Limits: these are acceptance examples and regression checks, not a guarantee that every possible commercial question can be answered. Missing evidence still leads to a specific limitation; unverifiable narration may be withheld while calculated results remain visible. Proposed business actions require an owner decision and are not executed by this analyst. Start a new conversation after refreshing to test the updated release; old messages retain their original answers.
