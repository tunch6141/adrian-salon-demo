# Task 06 — Follow-up conversation acceptance harness

## Goal

Create a dedicated development page/harness for diagnosing multi-turn commercial conversations without repeatedly rerunning setup turns.

## Required capabilities

For every turn show/save:

- owner question
- inherited analytical state
- fields that changed in scope
- Working Business Context used
- evidence requests and retrieved packets
- deterministic calculations
- review feedback
- final answer
- timing, model calls, input/output tokens
- deterministic gate result and LLM judge result

Allow a saved first-turn analytical state to be reused for several follow-ups.

Provide downloadable JSON for the full chain.

Diagnose failures by layer: follow-up understanding, state retention, entity scope, period scope, data retrieval, deterministic calculation, investigation depth, synthesis, presentation or unsupported claim.

## Initial evaluation chains

Evaluation only — never hardcode these phrases:

- Capacity: quiet next week → compare with last week at same lead time → biggest staff gap → what to do
- Staff: Sarah vs Matthew → what is going wrong with Sarah → matched prior period → what part of the gap is actually explained
- Revenue: why lower → which area contributed most → is Sarah driving it → next action/investigation
- Customers: regulars visiting less → prior period → concentration → safe conclusion

## Pass criteria

- original objective preserved unless explicitly changed
- unchanged entity/category/date dimensions remain intact
- changed dimension updates cleanly
- fresh evidence is retrieved when needed
- like-for-like baseline used where required
- no silent extra entities
- lookup vs diagnosis vs visualisation intent remains distinct
- final answer remains concise and commercially useful

## Stop condition

Build and locally test the harness. Run only a small representative subset of chains, save JSON and stop for review.
