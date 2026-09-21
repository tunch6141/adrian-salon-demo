# Stage 1 acceptance — 21 September 2026

Later native-tool revision: see [NATIVE_TOOL_REVISION.md](NATIVE_TOOL_REVISION.md)
for the current implementation and results. The report below preserves the
earlier attempt and must not be treated as the latest test totals.

## Decision

**Not accepted for normal use.** The implementation and repeatable harness are
available in Stage 1 Preview and Stage 1 Checks. The main app uses the prior chat
UI, preserved from commit `7f52653d79d473a5bab9887c233228285df069fc`.
This is an incomplete commercial-reasoning refactor, not a completed Stage 1.
The failures below are failures of this implementation, not proof that the model
cannot support the intended product.

## Environment and integrity

- Runtime model: GPT-4.1 mini; no replacement with a higher model.
- Live source: saved Supabase clean version
  `3909bfd6-5348-4210-82da-77db4d1f020e`, with 1 unresolved issue.
- Reporting clock: 17 September 2026, Australia/Sydney.
- No database migrations or raw, cleaned, approval or context-record mutations.
- Changed and renamed datasets were copies in memory, not production edits.
- Earlier live baseline remains on `archive/pre-stage1-commercial-refactor`.

## Code verification

The complete regression run passed **153 tests and 9 subtests** in 122.78 seconds.
Existing dependency deprecation warnings remain. After the independent evidence
assessment change, 14 affected tests passed. One additional test passed proving
that an approving writer/auditor cannot promote a primary cause when the
independent assessment established none. The integration test passed again after
moving the experiment into its separate preview page.

These checks cover source access, calculations, SQL restrictions, cleaning and
context workflows, state handling and validation. They do not certify the
quality of model-generated commercial explanations.

## Behavioural evaluation

The harness contains 9 core cases, 8 paraphrases, renamed staff/product cases,
a changed-data case and its control, and 2 unseen questions: 23 cases in total.
Passing cases were excluded from subsequent reruns unless manual review found
a material problem. Checks used deterministic data plus an automated judge;
the judge's results were manually checked rather than accepted at face value.

The initial 23-case run failed. Several general fixes improved later results,
including SQL cost-coverage checks, staff IDs, numerical citation handling,
context relevance and reserved conclusion rounds. A later 16-case run reported
10 automated passes, but manual review found unsupported causal claims among
those passes. Earlier useful results included service gross-profit ranking and
the changed-data staff comparison, where doubling one person's revenue changed
the explanation to revenue per service hour rather than more appointments.

The final affected-case run used commit
`0afb72fc073d45024d7338685535b37fa5c94577` with independent evidence assessment.
It reported **2 automated passes out of 11**. Neither automated pass was accepted
on manual review. This was not a fresh run of all 23 cases, so it must not be
presented as an overall 23-case score.

| Case | Final runtime result | Material finding |
|---|---|---|
| Revenue month comparison | Withheld | Unequal periods, incomplete context review and failure to retrieve/use a matched comparison. |
| Returning customers | Withheld | Latest-visit snapshot used as historical counts; malformed citations; genuine history was not investigated correctly. |
| Busy but insufficient profit | Withheld | Wrong cross-result denominator and missing calculated total; available cost data was not retrieved successfully. |
| Sales rising/profit worsening | Withheld | Did not establish the actual profit trend before discussing causes. |
| Capacity paraphrase | Withheld | Missing hypothesis metadata; reviewer also treated spare capacity as evidence against a demand problem, which is not justified. |
| Customer paraphrase | Withheld | Latest-visit snapshot again mistaken for visit history; query failure described as missing data. |
| Busy/profit paraphrase | Withheld | Failed cross-domain queries; unsupported characterisation of revenue per hour; insufficient evidence collection. |
| Turnover/earnings paraphrase | Automated pass, manually rejected | Described gross profit as net revenue minus costs AND refunds even though refunds were already included in net revenue. |
| Renamed staff | Withheld | Invalid hypothesis cell addresses and invalid chart grouping, despite retrieving useful staff data. |
| Base staff comparison | Withheld | Useful volume/rate explanation was blocked by a nonexistent chart series column. |
| Unseen refunds | Automated pass, manually rejected | Queried service-only refunds, then generalised absence to all staff refunds; product refunds were excluded. |

An ordinary-chat check of product revenue with a pie chart, followed by a request
for two other staff, was also withheld. Its saved scope retained product revenue
and the requested dates on the first turn, but this did not produce a usable
owner-facing answer or chart. It is not counted as a successful chart test.

Full reports can be downloaded from Stage 1 Checks when a run is present in the
browser session. This document records observed outcomes, not fabricated expected
answers. It deliberately preserves failures rather than tuning question-specific
branches to the benchmark.

## Remaining work before acceptance

1. Simplify the planner/tool output protocol and distinguish a query failure from
   absent data. Evidence review needs to influence the next investigation while
   tool budget remains, not only reject the final answer after collection ends.
2. Separate optional presentation failures from evidence sufficiency. A wrong
   chart column or optional cell citation must not erase an otherwise supported
   answer. Preserve strict numeric validation and show a clear visual limitation.
3. Improve semantic checks of source grain, filters, denominators, net/gross
   accounting and the exact outcome. The current model reviewer can approve
   mutually inconsistent claims; an automated pass is insufficient.
4. Re-evaluate general behaviour and the existing product-revenue/pie follow-up
   before promoting the preview. Do not substitute a higher model or add benchmark
   recipes silently. Stage 2/3 remain future work.

The next iteration should address these structural issues. Further accumulation
of prompt exceptions or repeated broad live runs is not recommended.
