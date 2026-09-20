# Owner feedback: reasoning 22.3

Customer follow-ups can resolve the customer and appointment date from the previous cleaned booking. A customer profile compares the recorded first completed visit with the requested date, displays available booking history, and distinguishes export counts from lifetime counts. Other calculations retain the cleaned, read-only SQL fallback.

Staff explanations use the same evidence-bound numeric parts as other answers, allowing digits rather than spelled-out amounts. Name corrections retain the other comparison participant. Unknown staff must be clarified. Valid trend and staff-comparison charts display even when the written explanation is withheld. Mixed comparison tables format numbers to at most 2 decimal places. Requested periods beyond the reporting clock carry a to-date notice.

## Correcting business context

In **Ask your salon → Context log**, select a note, edit its fields, supply your name and reason, approve, and confirm the change. The same form can retract a note. The selected note's change history shows before/after fields and supports export. Database audit events remain in `business_context_audit`.

Imported source notes receive an audited override; raw source data remains unchanged. Only the active replacement is supplied to subsequent answers, even when its entity or dates change. Earlier chat replies remain historical. Concurrent edits reject stale versions. Names are self-reported under the shared demo password.

Apply `db/context_corrections.sql` before this release. It adds `origin_id`, `change_reason`, and a unique source-override index to the existing server-only context table. Existing audit triggers capture changes.

## Revising an approved cleaning rule

In **Data Validation → Correct an earlier data approval**, choose a rule, select the replacement, enter your name and reason, preview affected cleaned fields, then approve and save. This appends a superseding decision and publishes a new cleaned version using the existing atomic pipeline. It does not edit raw data or prior versions/approvals. Matching future uploads use the latest approved rule. Record-specific fixes retain their source-row scope.

The approval history shows the previous and replacement values. For example, replacing S Wong = Sarah with S Wong = Sam changes matching cleaned bookings after confirmation. This feature does not itself change the owner's current approval.

## Scope and validation

Focused regression coverage: client status, comparison name replacement, chart independence, numeric table formatting, context approval/edit/retraction/audit/stale-edit handling, and superseding cleaning rules on current/future imports. One full regression run follows the focused checks. Live verification is limited to representative conversation paths and the new controls.

Automatic future metric review and scheduling remain a separate, unimplemented workflow; measurement advice does not create a scheduled review.

### Recorded checks

- Full regression run: 133 tests and 9 subtests passed. Existing dependency deprecation warnings remain.
- Replacement-approval screen: preview, explicit confirmation and save passed in Streamlit's test runner.
- Supabase context insert/correct/retract audit verified inside a rolled-back transaction; no temporary test note remains.
- Live GPT-4.1 mini: booking B00004 followed by “Is that client new or existing at this booking?” returned C0004, existing on 22 June 2026, first completed visit 1 December 2025, and 3 completed bookings in the export through that date.
- Live staff comparison retrieved Sarah and Matthew and the recorded leave notes, with a comparison chart. It exposed capacity wording and spelled-out leave counts; focused checks for the fixes passed.
- Live chart follow-up exposed loss of plural staff scope and an ending value labelled as a difference. After fixing those, the targeted live retry retained Sarah and Matthew and displayed their chart. Its explanation was withheld because an intermediate month label failed numeric binding. The narrow date-binding fix passed its focused test. A calculated trend summary now remains visible alongside the chart even if narration is withheld.
- Live context correction and cleaning-rule replacement controls were inspected. Existing owner approvals and source notes were not changed by the live UI checks.

The full suite was run once; subsequent checks covered only defects found in the live pass. No broad claim is made that arbitrary future questions will all pass narrative verification.
