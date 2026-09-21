# Revenue follow-ups — 21 September 2026

Release 22.4 keeps a structured revenue scope in the conversation: selected staff,
inclusive dates, revenue category, item breakdown and chart preference. Omitted
fields inherit the previous revenue request; explicitly named staff replace the
previous people. “What about Sarah and Matthew?” after Sam's product revenue
therefore requests those two people's product revenue for the same period.

Factual revenue totals, item breakdowns and transaction details use one filtered
set of cleaned financial records. Each item breakdown must reconcile to its
total. Counts distinguish distinct posted transactions from item lines. The model
interprets the question; these calculations and their factual rendering do not
need a separate narration/review call. Broader analytical questions retain the
existing diagnostic and read-only SQL routes.

Pie charts render directly from reconciled item revenue, independently of model
narration. Multiple people receive separate pies. Negative or zero-total net
revenue uses a labelled bar-chart fallback. Detail displays are capped at 500
lines, with an explicit notice; totals and composition include all matching lines.

Existing conversations can recover a simple staff/date/category scope from their
last executed financial query. Other SQL predicates are not discarded to force a
match. An unrelated data topic breaks inheritance. Start a new conversation to
avoid carrying forward previously incorrect results.

No raw records, cleaning approvals, business-context notes or database schemas
are modified by this release.

Validation: focused regression checks cover the three-turn conversation, SQL
reconciliation (Sam: AUD 990, 33 distinct posted transactions), transaction detail,
faceted pie specifications, explicit scope changes, old SQL history, topic
boundaries and signed-revenue chart fallback. All 4 focused checks passed. The
single full suite run passed 136 tests and 9 subtests; 4 existing temporary-file
tests were blocked by Windows filesystem permissions. Retrying only those 4
with a workspace temporary directory encountered the same permission failure.
No passing tests were repeatedly rerun outside the requested final suite.

Live verification is pending: browser automation could open the app but password
input did not reach the form. The mocked planner tests verify execution and
rendering, but do not substitute for a live GPT-4.1 mini routing check.
