# Native-tool revision — 21 September 2026

This revision replaces the preview orchestration with native Responses API
function tools. The development pages support GPT-4.1 mini and GPT-5.4 mini
with low reasoning effort. Normal chat remains on the preserved GPT-4.1 mini
version until commercial acceptance is established.

## Design

- `commercial/v2_runtime.py`: frame the objective; progressively request evidence;
  submit a conclusion; receive specific review feedback while queries remain.
- `commercial/v2_models.py`: small tool-specific contracts. Source references in
  the final-answer tool are constrained to the evidence actually retrieved.
- `commercial/v2_data.py`: enforce people, dates and revenue category; calculate
  grouped ratios from identical source rows; compare matched periods; retain
  missing values and cost coverage. SQL remains read-only on approved views.
- `commercial/v2_prompts.py`: one general commercial contract and evidence review.
  No benchmark questions, entity names, expected conclusions or routing recipes.
- `analytics/views.py`: a completed-booking customer history view distinguishes
  returning, new and unknown customers without using a latest-visit snapshot as
  historical retention data.
- `analyst_ui.py`: shared commercial presentation, optional validated charts,
  compact follow-up state and existing reviewed context correction controls.

The application computes facts. The model chooses the investigation and explains
what the evidence supports. The semantic review is fallible and is not a guarantee
of commercial accuracy. Automated acceptance grades require manual inspection.

No Supabase schema or records were changed. The active cleaned version, raw
preservation, cleaning approvals, amendment history and context audit trail are
preserved. Scheduled reviews and durable issue/action memory remain Stage 2.

## Verification performed

- Focused checks cover scope/category inheritance, SQL fallback scope, matched
  periods, customer-history grain, same-source ratios, missing costs, optional
  chart validation, review feedback and the preview UI.
- Final complete local regression: 166 tests and 9 subtests passed in 140.04 seconds.
  The subsequent optional-clarification change passed its focused regression,
  including preservation of genuine unknown-identity clarification.
  Existing legacy NumPy timedelta deprecation warnings remain.
- Initial 4-case live check revealed invalid tool combinations, citation protocol
  errors and unsupported claims despite automated passing grades. These grades
  were rejected manually.
- Second 4-case check confirmed improved retrieval but exposed repeated confusion
  between source table names and evidence identifiers. Dynamic schema enums now
  constrain those references; incompatible calendar defaults were removed.
- The full 23-case live run on `e169d123` reported 11 automated passes. Manual
  review rejected several of those: a booking count was reused as a cancellation
  count, an answer described customer trends without retrieving data, and a
  service-only refund query was generalised to all refunds. This is not an
  accepted 11/23 commercial-quality score.
- Revision `7f72e133` rejects empty-evidence conclusions, duplicate aggregates
  relabelled as different measures, and date filters outside the active period.
  It adds named calendar windows, scope-repair feedback, same-measure group
  comparisons and one bounded fresh synthesis using the same evidence checks.
  The final affected-case live run covered revenue, capacity, customers,
  busy/profit, conversation follow-up and refunds. It reported 1/6 automated
  passes, but the passing refund answer called retail products "services" and
  inferred a potential quality issue without evidence. It was not accepted.
- Owner-facing product lookup: Sam, May–August 2026, AUD 990, with a rendered pie
  chart by product, using saved cleaned version 3909bfd6. Completed in 9.8 seconds.
- After the group-ratio repair, the live product follow-up returned Sarah AUD
  1,620 and Matthew AUD 4,320 for May–August, retaining the product category and
  requested people. It took 28 seconds and 8 AI calls. The requested comparison
  chart was rejected by visual validation and a stray citation remained visible;
  the scope/numerical repair succeeded, but presentation is not fully accepted.
- The repeated setup lookup for this follow-up returned Sam AUD 990 with a
  rendered pie chart in 8.5 seconds and 4 AI calls.

## Release status

**Stage 1 is not yet accepted.** The revised implementation is published to the
experimental preview, not promoted into the regular chat. Code correctness and
guardrails have improved, but broad commercial diagnosis still needs live
verification. No claim is made that these changes are ready for general SME use.

The following table records the earlier GPT-4.1 mini run, before the reasoning
model experiment and subsequent scope repairs.

| GPT-4.1 mini affected case | Result | Remaining problem |
|---|---|---|
| Revenue | Facts only | Repeated invalid period choices; eventually reversed current/baseline windows; no successful evidence. |
| Capacity | Error | OpenAI request exceeded the configured 60-second timeout. |
| Customers | Facts only | Retrieved history, but interpretation still made unsupported return-rate/service-delivery claims. |
| Busy/profit | Facts only | Retrieved financial and hours comparisons, then suggested insufficient pricing without an evidenced comparator. |
| Follow-up | Facts only | Kept people and dates, but selected nonexistent columns and conflated outcome counts; partial evidence did not support the proposed explanation. |
| Refunds | Automated pass, manually rejected | Correct AUD 105 total and staff attribution, but misclassified products as services and suggested unsupported operational causes. |

The outstanding problem is not database connectivity. It is reliable query
planning, scope selection and interpretation. Another round of benchmark-specific
prompt exceptions is not an acceptable remedy. A bounded comparison with a
stronger reasoning model is a sensible next experiment under the owner's latest
permission to change model or code. A development-only selector now permits
GPT-5.4 mini with low reasoning effort. Its initial 4-case pilot passed 2 automated
checks (busy/profit and refunds). Revenue and customers were blocked partly by
omitted citations to evidence already retrieved. A local citation repair now
adds retrieved sources only when every claimed number can be validated; invented
numbers still fail. The reviewer now distinguishes accounting contributions from
unproven behavioural causes. The 2 affected live checks subsequently answered in
24.16 and 26.14 seconds and passed automated review. Revenue used matched dates;
customer analysis rejected the premise of fewer returning customers and measured
visits per observed returning customer. Remaining generalisation coverage is
reported below. The regular chat still uses its existing configuration. API compatibility and UI
changes passed 12 affected tests after the complete regression. The browser input
block was resolved after the owner dismissed the other extension window.

The citation repair passed 10 focused tests, including a regression proving that
an omitted source can be repaired but a number absent from every retrieved result
still cannot pass. The evidence review still checks semantic attribution; a
matching number alone does not establish that it describes the claimed outcome.

## Reasoning-model verification and remaining limits

The subsequent 19-case GPT-5.4 mini run reported 18 automated passes. This is
**not a verified accuracy score**. Manual inspection found material errors:
overlapping future booking horizons were summed; an all-history query was
labelled August; booking counts were confused with distinct customer counts;
and a service-only subset was described as whole-business turnover. A profit
answer also described an approximately 85% gross margin as tight without a
supporting benchmark. These findings overrule automated passing grades.

Generic data contracts now reject dated snapshot queries, require explicit
date scopes, select exactly one matching precomputed booking horizon, reject
duplicate canonical row counts labelled as different measures, and identify
filtered category subsets in evidence metadata. Comparison packets include
independently calculated full-scope totals rather than totals inferred from
displayed groups. No benchmark-specific answer or entity routing was added.

The final affected checks were split after the live page interrupted after
3 completed cases. Only the remaining cases were resumed:

- Capacity: 43 booked hours / 114 available, 71-hour gap, 37.72% utilisation;
  correct single next-week horizon and 3 staff, rather than overlapping sums.
- Sales/profit: matched Sep 1–17 versus Aug 1–17 revenue AUD 20,345 versus
  AUD 20,655; gross profit AUD 17,293.67 versus AUD 17,329. Correctly rejects
  the premise that sales increased and separates gross profit from overheads.
- Turnover paraphrase: the same whole-business revenue totals, AUD 310 or
  1.50% lower, with item/staff contribution evidence. Underlying behavioural
  cause remains unproven. The response took 67.19 seconds, so speed is variable.
- Customer paraphrase: 137 to 157 returning visits, 128 to 157 observed returning
  customers, frequency 1.0703125 to 1.00 (-6.57%). The denominator is now distinct
  customers rather than bookings. This measures observed visitor frequency,
  not a cohort retention/churn rate. Response: 30.72 seconds.
- Profit paraphrase: correct whole-business matched totals and distinction
  between near-flat gross profit and unavailable operating expenses. It no
  longer described the approximately 85% gross margin as tight. Response:
  40.37 seconds.
- Changed staff fixture: correct August totals (Sarah AUD 25,200, Matthew
  AUD 12,680), AUD 12,520 gap, similar workload and service revenue per hour
  AUD 167.92 versus AUD 83.85. **Commercial reasoning remains incomplete:**
  it attributed the association to higher-value service mix without separating
  price/value per service from volume and mix. It offered that available
  investigation as a next step instead of completing it. Response: 58.18 seconds.

All 6 affected responses passed automated review. The changed-data response is
not a complete manual acceptance pass. Numerical correctness is necessary but
does not satisfy the handoff's commercial-investigation requirement by itself.
No further broad test run was started after these affected checks.

Live conversation checks also verified booking B00004 and the follow-up asking
whether its client was new or existing: the client was correctly identified as
returning from a first completed visit on 1 December 2025. Sam's May–August
product revenue returned AUD 990 with a pie chart. After a bounded reconsideration
of optional clarification, “What about Sarah and Matthew?” kept the same product
category and dates, returned AUD 1,620 and AUD 4,320 respectively, and rendered
a product pie chart. It took 37.4 seconds and 8 AI calls; no third staff member
was silently added. Genuine unknown-identity clarification is still allowed.

These results support continued development use, not unrestricted SME readiness.
The model can still be repetitive, use technical source names in suggestions,
or stop at a contribution analysis without completing every useful follow-up.
Neither its self-review nor a passing evaluator guarantees commercial accuracy.

Implementation reference: native function schemas are supplied through the API's
`tools` argument, following the official function-calling guide:
https://developers.openai.com/api/docs/guides/function-calling .
