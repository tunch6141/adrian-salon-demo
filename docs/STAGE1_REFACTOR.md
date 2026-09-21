# Stage 1 commercial reasoning refactor

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
