# Task 05A — Checkpoint diagnostics and failure localisation

## Goal

Build a reusable Stage 1 diagnostic layer so future customer-reported problems can be isolated to the first failing part of the pipeline without reading the whole codebase or rerunning the 23-case suite.

This is an observability/testability task, not a new reasoning architecture.

## Diagnostic model

Represent Stage 1 as independently inspectable checkpoints:

1. **Working Context** — relevant owner/business context assembled correctly.
2. **Question/Scope** — commercial objective, entities, category, period and comparison understood.
3. **Evidence Plan** — required datasets/calculations selected appropriately.
4. **Deterministic Data** — retrieval/calculation output is correct for the requested scope.
5. **Evidence Contract** — population, entity, period, category, grain, units and denominators are compatible with the claims they can support.
6. **Diagnosis** — competing explanations and stopping rule behave correctly.
7. **Owner Response** — conclusion, 2–3 supporting facts and next step are plain-language and supported.
8. **Follow-up State** — inherited objective/scope changes only where the owner changed it.
9. **Boundary** — missing/external/unknown information is handled without hallucination.

## Key requirement: frozen upstream artifacts

Each checkpoint should emit a stable structured artifact that can be saved and reused by later checkpoint tests.

Examples:

- context bundle
- framed scope
- evidence request plan
- deterministic result packets
- validated evidence bundle
- diagnosis candidate/review result
- final display payload
- analytical follow-up state

Where technically safe, a downstream checkpoint test must be runnable from these saved artifacts without invoking the earlier model stages again.

This is important for both failure localisation and token control.

## Diagnostic bundle

For one investigation, provide a downloadable/readable JSON bundle containing at least:

- question and snapshot/version identity
- model/configuration
- checkpoint ID and status
- checkpoint input summary
- checkpoint output summary
- deterministic assertions
- blocking error or failure code
- evidence/result references
- model call count for that checkpoint
- input/output tokens for that checkpoint
- elapsed time
- upstream artifact IDs/hashes
- whether the checkpoint can be replayed independently

Do not log secrets or raw credentials.

## Failure taxonomy

Use stable failure categories so a production bug can be routed quickly. At minimum:

- context_retrieval
- question_framing
- scope_inheritance
- evidence_planning
- data_retrieval
- deterministic_calculation
- evidence_scope
- denominator_or_grain
- investigation_depth
- semantic_review
- answer_presentation
- followup_state
- boundary_or_hallucination
- infrastructure_or_timeout

A single run may contain warnings, but identify the **first material failing checkpoint** separately.

## Test strategy

Create a small canary set for each checkpoint. These are contract tests, not benchmark-specific answer recipes.

Most early checkpoints should be deterministic and use no live model call.

For model-dependent checkpoints, use a very small focused canary set and saved upstream artifacts.

Examples:

- test question/scope framing with a saved Working Context bundle
- test evidence planning from a saved framed scope
- test deterministic calculations without invoking any LLM
- test diagnosis from a saved validated evidence bundle
- test owner-response wording from a saved supported diagnosis
- test follow-up state from a saved prior analytical state
- test boundary behaviour from a saved scope plus deliberately missing evidence

## Stage 1 Diagnostics page

Add a development-only diagnostic page or extend the existing Stage 1 checks area with:

- checkpoint selector
- canary/case selector
- option to load a saved diagnostic bundle
- run selected checkpoint only
- run checkpoints sequentially until first failure
- clear pass/fail/warning table
- first-failing-checkpoint summary
- downloadable JSON
- token/call/time totals by checkpoint

Do not expose this as the normal owner-facing product UI.

## Debugging workflow after launch

When a customer reports a problem:

1. Reproduce or load the affected investigation bundle.
2. Start with the cheapest relevant deterministic checkpoint.
3. Run checkpoints in order only until the first material failure is located.
4. Fix that layer.
5. Rerun that checkpoint and the immediately downstream contract checks.
6. Run a small end-to-end regression for the affected behaviour.
7. Run the full Stage 1 suite only when the change is broad enough to justify it or as part of planned release validation.

## Token discipline

The checkpoint harness exists partly to prevent unnecessary model usage.

- deterministic checkpoints should use zero LLM tokens
- reuse frozen upstream artifacts instead of regenerating them
- do not repeat successful upstream model calls while debugging a downstream layer
- record token use per checkpoint so expensive stages are visible
- do not run the full 23-case suite to diagnose one customer-reported issue

## Acceptance criteria

- A seeded context failure is identified as a Working Context failure without invoking later checkpoints.
- A wrong entity/scope packet is identified by the Evidence Contract checkpoint.
- A wrong deterministic calculation is separated from a diagnosis failure.
- A valid diagnosis with poor wording is classified as Owner Response, not Data or Diagnosis.
- A follow-up inheritance error is classified separately from fresh-question framing.
- An external-information hallucination is classified as Boundary.
- A saved validated-evidence artifact can be used to test diagnosis without repeating context/framing/data model calls.
- The diagnostic JSON clearly identifies the first material failure, warnings, calls, tokens and elapsed time.
- Existing Stage 1 runtime behaviour remains unchanged except for instrumentation/test seams needed to support the diagnostics.

## Stop condition

Run local tests plus a very small canary demonstration. Do not run the 23-case suite. Save one example diagnostic bundle and stop for review before Task 06.
