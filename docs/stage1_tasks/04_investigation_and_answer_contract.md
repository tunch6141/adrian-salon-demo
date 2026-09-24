# Task 04 — Investigation completion and owner-facing answer contract

## Goal

Make the analyst finish an available investigation before stopping, then present the result in simple business language.

## Investigation stopping rule

If multiple plausible explanations remain and available connected data can materially distinguish them, continue investigating before answering.

Stop only when:

- a commercially meaningful diagnosis is sufficiently supported, or
- available data genuinely cannot resolve the remaining uncertainty

In the second case, state what is known and give one specific next investigation.

Do not stop at an intermediate metric such as revenue per hour when accessible price/value, volume, service mix, customer mix or another relevant breakdown can resolve the question.

Use reviewer feedback while data-call budget remains. Do not merely mention the missing investigation in the final answer when the runtime can still perform it.

## Owner-facing output

Keep GPT-5.4 Mini for reasoning. The default visible answer must be:

1. **Conclusion** — one short direct answer
2. **Supporting evidence** — usually 2–3 material facts/calculations
3. **Next step** — one supported action, or one next investigation if uncertainty remains

Avoid internal dataset names, SQL terminology, evidence IDs, repeated facts and long decimals in the main answer. Technical details stay in Evidence and Calculations.

A chart is optional and must never block a valid answer.

## Acceptance tests

Local/unit:

- A reviewer request for available distinguishing evidence causes another evidence call before finalisation.
- If the required evidence is unavailable, the answer is allowed to stop with qualified uncertainty.
- Optional chart failure does not erase a valid answer.
- Display output does not repeat the same fact in multiple sections.
- Business-facing values are sensibly rounded.

Focused live checks only after local tests pass:

- changed staff revenue-gap case
- one revenue/root-cause case
- one capacity case

Do not run all 23 cases.

## Stop condition

Report the three focused outputs and stop for review.
