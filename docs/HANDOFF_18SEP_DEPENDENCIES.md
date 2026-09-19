# Implementation contract for the 18 September 2026 handoff

The 18 September handoff is the design authority. This release extends the synthetic dataset and connects deterministic analytics to that dataset. Source records remain immutable. The original `piece1_validation/sample_raw` is the frozen regression fixture. The generated active fixture is `data/handoff_2026_09_18/raw`.

| Module | Minimum data | Enrichment | Missing-data behaviour |
|---|---|---|---|
| Revenue / ATV | Posted transactions and net amounts | Lines, staff, service, refund links | Partial coverage explicit, no invented totals |
| Volume / cancellation | Booking identity, dates, status | Event history, slot recovery | No cancellation motive inferred |
| Retention / customer value | Customer identity, completed visits, transactions | Explicit due date, service defaults, follow-ups | Due rule provenance, unknown when no rule |
| Staff / capacity | Staff, availability, completed service duration | Service mix, context, skills | Missing denominator makes utilisation unavailable |
| Future workload | Active bookings and history | Available hours, same-lead-time history | Never label booked value earned revenue |
| Service / attachment | Services, booking and transaction lines | Package components, cost, durations | Unpriced package components never receive invented revenue |
| Inventory | On-hand quantity, movements | Cost, lead time, on-order, owner suppression | Zero movement has no finite stock-days value |
| Supplier / costing | Receipts, SKU, quantity, cost | Invoice charges, batches, returns, terms | exact_batch / explicit_cost / FIFO_estimated / latest_cost_fallback provenance |
| Pricing | Prices, sales, volume | Costs, capacity, quote versions | Simulation is not forecast or causality |
| Quotes / follow-up | Quote identity, amount, outcome | Attempts, date override, reasons, linked sales | Three-calendar-day follow-up default, preserve closed history |
| Receivables | Invoice, due date, payments and credits | Historical delay, promises | Actual outstanding separated from estimated working-capital burden |
| Insight / action / checkpoints | Insight identity and owner decision | Baseline, snapshots, dates | No automatic operational changes, append history |

## Explicit fixture choices and open decisions

- Synthetic history extends to June 2025, with a fixed as-of instant of 17 September 2026 at 18:00 in Australia/Melbourne. The handoff date is a specification version, not the reporting clock.
- The old sale-only ATV remains labelled `average_transaction_value` in the regression calculator. New financial views expose both sale count and posted-document count, labelled explicitly; the app does not silently decide the refund denominator.
- Period service revenue per completed hour uses posting-period revenue and states that basis. Unlinked service sales or cross-period postings make the productivity ratio unavailable until reconciled. Sales are still revenue.
- Adaptive return intervals use at least three observed completed visit dates and median gap for this synthetic fixture. This is labelled a fixture policy, not a universal locked threshold.
- Fixture-specific expected returns, stock irregularity indicators, sample-size choices, pricing tests and owner priorities are test inputs, not production defaults inferred from data.
- Exact anomaly ranking thresholds, subscription boundaries, cash forecasting, operating profit and live Supabase migrations remain OPEN and are not implemented by this release.
- Scenario metadata and expected results are testing artefacts, never model evidence.

## Change scope

Preserve the legacy six-CSV demo and three-issue clarification flow. Add a reproducible generator, expanded canonical fields and tables, common runtime, deterministic analytical views, supported staff/booking/inventory/quote/receivable calculations, context bridging and tests. Retain read-only dynamic SQL restrictions and source citations. Model-generated Python is never executed. Owner writes still require explicit confirmation. Broader operational event writes and automatic insight scheduling are not enabled.
