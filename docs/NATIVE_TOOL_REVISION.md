# Native-tool revision — 21 September 2026

This revision keeps GPT-4.1 mini and replaces the preview orchestration with
native Responses API function tools. Normal chat remains on the preserved
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
- Final complete local regression: 163 tests and 9 subtests passed in 133.14 seconds.
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
- Its follow-up retained the correct people, product category and May–August
  period, but a missing calculated cross-group ratio prevented an answer. The
  ratio calculation is now implemented and locally verified. Live retesting is
  pending; Chrome reported another extension window blocking preview input.

## Release status

**Stage 1 is not yet accepted.** The revised implementation is published to the
experimental preview, not promoted into the regular chat. Code correctness and
guardrails have improved, but broad commercial diagnosis still needs live
verification. No claim is made that these changes are ready for general SME use.

| Final affected case | Result | Remaining problem |
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
permission to change model or code; no such benchmark has yet run and GPT-4.1 mini
remains configured. Browser preview input requires the extension window to be
dismissed before that owner-facing verification can continue.

Implementation reference: native function schemas are supplied through the API's
`tools` argument, following the official function-calling guide:
https://developers.openai.com/api/docs/guides/function-calling .
