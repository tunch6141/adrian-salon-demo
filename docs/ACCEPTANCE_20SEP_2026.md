# Stage acceptance testing — 20 September 2026

## Outcome

The data pipeline passes the tests below. Context retrieval and owner approval controls work, but live context-aware explanations do not yet pass acceptance reliably. The whole stage should not be signed off as fully working until the two remaining context-response failures are resolved.

| Area | Result | Evidence |
|---|---|---|
| Supabase connection | Pass | Live database queries succeeded. Both Streamlit screens loaded cleaned version `0cdcac31-2d93-4e6c-b156-c3dc092195b0`. |
| Raw and cleaned separation | Pass | Supabase stores 2,507 original booking rows and 2,506 cleaned booking records. The original raw batch remains unchanged. |
| Validation | Pass | All nine checks on the deployed Data Validation page passed. Unknown staff, unknown stock cost and conflicting customer identity remain unresolved rather than guessed. |
| Approvals and rule reuse | Pass in isolated tests | Live Supabase transaction tested approval persistence, automatic reuse on another import, audit linkage, duplicate retry handling, stale-write rejection and protection against changing raw data or erasing earlier approvals. All temporary records were rolled back. |
| Analyst reads cleaned data | Pass | Live GPT calculation evidence identified the saved version and returned Sarah's service AUD 1,380, retail AUD 30, total AUD 1,410 for 7–13 September. Independent SQL against that saved Supabase snapshot matched service and retail totals. |
| Changed clean data reaches analyst | Pass in controlled integration test | A reviewed AUD 100 test sale changed evidence and the bound answer from AUD 1,410 to AUD 1,510 while raw records stayed unchanged. This test mocks the model response; no sale was added to the live business dataset. |
| Owner confirms context before saving | Pass in isolated UI test | Saving without the confirmation checkbox produced no record. Confirming with dates and the person's name saved exactly one note. |
| Relevant context reaches answer generation and review | Pass in integration tests; retrieval observed live | Source and stored notes are combined and filtered by entity and period. Both writer and reviewer receive relevant notes. Unrelated, retracted and explicitly unconfirmed notes were excluded in tests. |
| Complete live context-aware answer | Not passed | Relevant notes were retrieved, but the model's written response failed evidence checks. See reproducible cases below. |

## Live failures and the narrow fix made

Question: “For Sarah from 7 to 13 September 2026, report net revenue and any relevant recorded business context. Explain which information comes from calculated records and which is only owner-reported. Can those notes establish why revenue changed?”

The first run retrieved correct revenue and notes CTX1 and CTX2, but failed the numeric placeholder check. The date binding previously only recognised the analysis period, not the different dates in a cited owner note. The patch now binds dates to the exact cited context record, including dates such as 8–9 September. Tests confirm that unrelated dates, uncited dates and typed monetary amounts remain rejected. The patch was deployed in commit `4d701085a94898ace93a9421b72475720a04d33e`.

The subsequent live run passed that point but failed with “A factual claim has no evidence.” The answer writer still sometimes emits an uncited statement despite its formatting repair. The application correctly withholds the explanation; this is safe failure, not a successful answer.

Question: “What business context has been recorded for Matthew on 18 September 2026? Is that owner-reported information or independently verified attendance?”

A relevant stored note exists, but the planner attempted an unnecessary invalid query and its repair failed with “Each result must derive from database columns.” A dedicated context lookup path is needed so existing notes can be explained without inventing a financial query. The notes must remain labelled owner-reported, not verified attendance or proof of causation.

## Additional data observation

An existing Salon note has structured start/end dates of 18 September while its explanation says Sarah was on leave on 19 September. This inconsistency was not changed. It should be reviewed by the owner because retrieval uses the structured dates. This is a note-quality issue distinct from the model response failures.

## Verification scope and preserved state

- Full regression run after the date-binding fix: 91 tests and nine subtests passed. One additional context-approval UI test was then added and passed with the other three context tests: 92 distinct passing tests in total.
- Live validation page: nine checks passed. These use the independent fixture; they do not by themselves prove live GPT response quality.
- Live transactional database tests ran as the app's server role and ended with rollback. No test-only approval, sale or context was retained in the active database.
- Final database state: one raw batch, one cleaned version, one seed audit event, two pre-existing standalone context records. The active version remains unchanged.
- Three ambiguous source issues remain for actual owner review: S Wong, inventory item P04 cost, and customer import IMP04 identity conflict.

## Next acceptance gate

Fix the context-only lookup path and ensure the writer produces cited context claims or clearly labelled limitations without suppressing valid findings. Repeat both exact live questions above, plus an unrelated-date/person negative test. Keep numerical totals unchanged by narrative context. Require the final explanation to pass evidence review before treating the context area as accepted.
