# Stage 1 finalisation plan — 24 September 2026

This is the current source of truth for finishing Stage 1 of the commercial analyst. Earlier Stage 1 documents remain historical implementation and test evidence.

## Current decision

- Primary Stage 1 reasoning model: **GPT-5.4 Mini**.
- Preserve the current native-tool architecture, canonical clean-data pipeline, deterministic calculations, evidence metadata, active analytical state and preview isolation.
- The latest 23-case GPT-5.4 Mini run reported 23/23 automated passes, but this is **not manual commercial acceptance**. Manual review found material errors, including named-entity scope leakage in the Ocean Wash inventory case.
- Do not restart the architecture or compare GPT-4.1 Mini again unless a specific regression requires it.
- Durable business memory, issue lifecycle, scheduled reviews and proactive monitoring remain Stage 2.

## Locked reasoning workflow

Owner question
→ assemble bounded Working Business Context
→ understand the commercial question using question + context
→ decide what deterministic evidence is required
→ request trusted calculations from canonical clean data
→ diagnose the commercial situation
→ generate the owner-facing response

Working Business Context currently comes primarily from the existing Business Context Log. It must be available before the system commits to the evidence/calculation plan. Future Stage 2 memory retrieval must be able to populate the same context interface without rebuilding the Stage 1 reasoning engine.

Owner-reported explanations may guide hypotheses, but are not causal proof. Owner-defined definitions, business rules and KPI targets may guide framing when their provenance and applicability are clear.

## Comparator semantics

Do not hardcode generic KPI targets such as 80%, 85% or 90% utilisation.

Keep these as separate concepts:

1. **Owner-defined target** — what the business wants to achieve. Use it first when a relevant current target exists.
2. **Recent comparable baseline** — what has recently been normal for this business. For weekly operational metrics, default to the previous four completed comparable weeks, using same elapsed weekdays or same lead-time position where appropriate.
3. **External benchmark** — an outside reference point. Use only when an approved external source is deliberately introduced and label source/date clearly.

A four-week baseline is not a target. If recent utilisation averaged 68% and no target exists, do not call 68% poor because of an assumed industry norm.

## Remaining Stage 1 defects

The finalisation work must address the following general behaviours:

- Working Business Context must influence framing before evidence planning.
- Named-entity conclusions must be supported by evidence attributable to the named entity.
- Scope, category, period, grain, measure, unit and denominator must remain compatible.
- The investigation must continue when available data can materially distinguish unresolved explanations.
- Metrics not already precomputed must use a safe structured deterministic-calculation fallback rather than unrestricted model-written Python.
- Future booking comparisons must support like-for-like same-lead-time baselines.
- Follow-up questions must preserve the active commercial objective and modify only the dimensions the owner changed.
- Stage 1 must know when evidence is unavailable, when a question requires external data, and when the owner's premise is false.
- The acceptance gate must combine deterministic correctness checks with an LLM commercial-quality review.
- Owner-facing answers must use plain business language: **Conclusion → 2–3 supporting facts → Next step**.
- The runtime and evaluation stack must expose checkpoint-level diagnostics so a later production problem can be isolated without rerunning the whole Stage 1 suite.

## Diagnostic checkpoint principle

Stage 1 must be observable as a sequence of independently testable contracts, not one opaque end-to-end answer.

A diagnostic bundle should preserve the output of each major checkpoint so downstream checks can reuse frozen upstream artifacts. This enables a reported failure to be narrowed to the first failing checkpoint instead of rerunning every earlier model call.

The intended checkpoints are:

1. Working Business Context assembly
2. question interpretation and scope framing
3. evidence/data requirement planning
4. deterministic retrieval and calculation
5. evidence binding and scope validation
6. diagnosis and stopping-rule behaviour
7. owner-facing response construction
8. follow-up state inheritance
9. boundary/hallucination behaviour

Each checkpoint should have a small set of deterministic or focused canary tests, structured pass/fail diagnostics and a stable JSON artifact. The diagnostic harness must allow one checkpoint to be rerun from saved upstream artifacts wherever technically safe.

This is not a replacement for the final 23-case suite. It is the day-to-day debugging layer used before expensive end-to-end verification.

## Execution workflow

Work is deliberately split into small tasks under [stage1_tasks](stage1_tasks/README.md).

Rules for Astra/Codex:

1. Implement **one task at a time**.
2. Inspect the current repository before changing code.
3. Make the smallest general change that satisfies the task. Do not add benchmark-specific names, thresholds, routes or expected answers.
4. Run the task's deterministic/unit acceptance tests before any live-model test.
5. Do not start the next task until the current task's acceptance criteria pass and the result has been reviewed.
6. Commit after each task so progress is preserved if weekly usage is exhausted.
7. Avoid broad 23-case live reruns during development. The full suite runs once near the end.
8. If a task exposes a need for a major redesign, stop and report why before doing it.
9. Where a saved upstream artifact exists, rerun only the checkpoint under investigation instead of replaying the complete pipeline.

## Task sequence

1. [Working Business Context and comparator semantics](stage1_tasks/01_working_context_and_comparators.md)
2. [Named-entity and evidence-scope guardrails](stage1_tasks/02_scope_and_evidence_gates.md)
3. [Safe dynamic calculation fallback and booking pace](stage1_tasks/03_dynamic_calculation_fallback.md)
4. [Investigation completion and owner-facing answer contract](stage1_tasks/04_investigation_and_answer_contract.md)
5. [Acceptance gate hardening](stage1_tasks/05_acceptance_gate_hardening.md)
5A. [Checkpoint diagnostics and failure localisation](stage1_tasks/05a_checkpoint_diagnostics.md)
6. [Follow-up conversation acceptance harness](stage1_tasks/06_followup_checks_harness.md)
7. [Boundary and hallucination acceptance harness](stage1_tasks/07_boundary_hallucination_harness.md)
8. [Targeted validation, repeatability and final promotion decision](stage1_tasks/08_final_validation.md)

The sequence is intentional. Tasks 1–5 strengthen runtime behaviour and the examiner. Task 5A adds reusable diagnostic observability before the more expensive conversation-chain tests. Tasks 6–7 add focused multi-turn and boundary harnesses. Task 8 is the only task that should perform the final broad live verification.

## Stage 1 Definition of Done

Stage 1 is ready for owner acceptance only when:

- GPT-5.4 Mini is the accepted reasoning model.
- Relevant Working Business Context is assembled before evidence planning.
- Owner-defined targets, recent baselines and external benchmarks remain distinct.
- Named entities, population, category, dates, grain, units and denominators are protected.
- The analyst investigates until it reaches the strongest supportable diagnosis or genuinely runs out of relevant evidence.
- Safe deterministic fallback calculations cover reasonable questions that are not already precomputed.
- Multi-turn follow-ups preserve scope and retrieve fresh evidence where needed.
- Boundary/hallucination checks show no invented internal facts, silent entity substitution or unverified current external claims.
- Owner-facing output is concise and non-technical.
- Diagnostic checkpoint tests can identify the first failing layer without requiring a full 23-case rerun.
- Deterministic gates, the commercial judge and targeted manual review show no material correctness failures.
- Critical cases remain materially correct across repeated runs.
- The preview is not promoted to normal chat until the owner explicitly accepts Stage 1.

## Explicitly out of scope

Do not implement Stage 2 durable memory writing, embeddings, issue/action lifecycle, scheduled review checkpoints, proactive monitoring, learning from past actions, or Stage 3 execution integrations during this finalisation cycle.

## Historical evidence

- [NATIVE_TOOL_REVISION.md](NATIVE_TOOL_REVISION.md)
- [STAGE1_ACCEPTANCE.md](STAGE1_ACCEPTANCE.md)
- [STAGE1_REFACTOR.md](STAGE1_REFACTOR.md)
