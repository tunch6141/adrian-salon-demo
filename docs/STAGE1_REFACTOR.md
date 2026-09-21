# Stage 1 commercial reasoning refactor

**Acceptance: not ready for default use.** The experiment is isolated in
`pages/3_Stage_1_Preview.py`. Normal chat uses `stable_chat_ui.py`, copied exactly
from the pre-refactor UI at `7f52653d79d473a5bab9887c233228285df069fc`.
The acceptance harness remains available in Stage 1 Checks. Passing code tests
does not establish commercial reasoning quality. See `STAGE1_ACCEPTANCE.md`.

## Before implementation

The live UI imports analyst_ai.investigate. Its planner combines ROUTING_RULES,
PLANNER, analytics.rules.rules_for and analytics.reasoning's metric-family graph.
Python then applies staff-name/phrase guards and selects revenue, diagnostic,
trend, booking or dynamic SQL routes. A writer can request deeper queries;
numeric binding and a reviewer approve the result. Several direct-render routes
bypass synthesis. The UI displays diagnostic cards and large internal tables.
History consists primarily of the last five questions and plans, with limited
record resolution. The unpublished 22.4 commit adds a revenue-specific state.

Preserve: canonical intake, cleaned snapshot loading, source lineage, approval
and context audit flows, capability checks, deterministic views/calculations,
read-only SQL restrictions and evidence binding/visual validation mechanisms.

Isolate: analyst_ai, analytics.reasoning and its graph, old routing prompts and
phrase/name guards. Keep these for old regression/A-B work; do not import them
into the new commercial runtime or send their prompts to the model.

Replace: active orchestration, prompt composition, compact analytical state and
answer presentation. The new commercial package owns those responsibilities.
The old live version is preserved at archive/pre-stage1-commercial-refactor;
local commit 4a513fb preserves the unpublished revenue change as well.

Stage 2 remains a future structured issue/action/baseline/review store with
scheduled fresh investigations and suppression of unchanged acknowledged issues.
Stage 3 remains optional approved execution integrations. Neither is implemented
or implied by Stage 1's session state or suggested next steps.

## Implemented architecture

The Stage 1 preview UI calls commercial.runtime only. A structured Step frames the
objective, proposes up to four hypotheses and requests up to three evidence tools
at a time. There are three evidence-collection rounds, up to nine tool calls, and
two reserved conclusion/repair rounds per question. An independent assessment
examines evidence without seeing the proposed answer. The conclusion must respect
that assessment; absent an established driver, a primary cause is blocked.
A separate semantic audit checks the proposed final answer. Rejected
claims return specific feedback within the same bound; no unverified diagnosis
is promoted just because the budget is exhausted.

The compact session state stores scope, findings, tested hypotheses, unresolved
questions and snapshot identity. Null scope fields inherit independently;
explicit changes replace them and a new topic resets them. Changed snapshots
invalidate old findings. Prior findings are never current evidence citations.

Calculators expose trusted facts; the model chooses their relevance. General
SQL and restricted arithmetic over result references support investigations
outside those calculators. Data definitions describe grains, units, coverage and
relationships without importing the deprecated metric-family graph. There are
no benchmark prompts, staff-name switches or keyword recipes in commercial/.

The normal answer contains the direct diagnosis, selected supporting evidence,
and a supported action or next investigation. Only selected tables/one chart
appear. Full tool requests, result data, citations and hypothesis tests can be
inspected and downloaded from Evidence and calculations.

No database migration was required. Raw and cleaned records, approval logs,
context corrections and audit storage were preserved. Session analytical state
is not Stage 2 durable business memory or a scheduled review.

## Verification

The complete local regression run passed 153 tests and 9 subtests. After the
independent assessment change, 14 affected tests passed. A new test confirmed
that an unestablished cause cannot be promoted even by an approving writer and
auditor. The preview-page integration test also passed after isolating the UI.
Existing dependency deprecation warnings remain. Passing tests were not repeatedly
rerun; failed or changed behaviour was rechecked.

The initial 23-case live run failed acceptance. Shared implementation fixes
addressed evidence addresses, tool arguments, case-sensitive status filters,
SQLite dialect/schema failures, grouped cost-coverage checks, numerical prose
and stale context relevance. These were general changes, not benchmark recipes.
The later 16-case run reported 10 automated passes, but manual review rejected
several of those conclusions. The final affected-case run is recorded separately.
No automated pass count is presented as proof of commercial quality.

Evaluation questions and changed/renamed fixtures remain isolated under `evals/`;
they are never loaded by analytical chat. Fixtures operate on in-memory copies
of the current cleaned snapshot. They do not change Supabase data.

Model implementation reference: GPT-4.1 mini supports the Responses API and
structured outputs: https://developers.openai.com/api/docs/models/gpt-4.1-mini .
The requested model was retained; no higher model was substituted.

## Proposed later stages (not implemented)

Stage 2 should store an issue record with the business, subject, question,
baseline period and clean-version ID, baseline evidence, diagnosis, uncertainty,
owner-approved action, action date, review date and status. Reviews should read
the latest cleaned version, rerun a fresh investigation and record improvement,
persistence or worsening with evidence. Keep review history rather than replacing
the baseline. Suppress acknowledged unchanged issues until their review is due.

The weekly review should prioritise one highest-value insight, one quick win and
a due-customer follow-up list. Urgent exceptions need explicit commercial criteria.
None of these schedules or durable issue records is created by the Stage 1 chat.
Stage 3 can add separately approved CRM/calendar/message integrations without
granting the analytical query runtime write access.
