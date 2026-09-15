# Adrian's salon demo — six months of synthetic data

All people, transactions and results are fictional. This dataset demonstrates three agreed business questions. It is not evidence about an actual salon or Australian industry benchmarks.

## Start here

Use **13 September 2026, 23:59:59, Australia/Melbourne** as the fixed demo date. Do not use your computer's current date for the demonstration.

- History: 16 March–13 September 2026, 26 completed weeks (approximately six months).
- This week: 7–13 September 2026.
- Four-week baseline: weeks starting 10, 17, 24 and 31 August 2026. This excludes this week.
- Next week: 14–20 September 2026.
- Six additional known appointments in 21–25 September prevent already-booked customers appearing as unbooked follow-up opportunities. That later week is NOT a complete demand forecast.
- Dates use ISO format. Timestamps are local Melbourne wall-clock times without UTC offsets. All money is AUD. Amounts use one consistent illustrative GST-exclusive basis; no tax calculations are modelled.

## Files and joins

| File | Purpose | Key |
|---|---|---|
| customers.csv | Fictional names, example.com email addresses, first-ever completed visit and preferred staff | customer_id |
| services.csv | Six services, prices, durations and colour-service eligibility | service_id |
| staff_capacity.csv | Daily bookable shifts for Sarah, Matthew and Sam | capacity_id |
| appointments.csv | Completed, cancelled and future bookings, recorded dates, services and revenue | appointment_id |
| retail_sales.csv | Colour-care shampoo purchases linked to appointments | retail_sale_id |
| customer_followups.csv | Past contact attempts and explicitly linked booking outcomes | followup_id |
| weekly_metrics.csv | Calculated reference answers for weekly bookings and revenue | week_start |
| retention_opportunities.csv | Calculated due-customer review list, including exclusions | customer_id |
| scenario_answers.csv | Expected results for the three demo questions | scenario + metric |
| data_dictionary.csv | Column definitions and data types | file + field |

The first six files are source tables. The next three are **derived reference outputs**, useful for checking your app. Recompute them from source records rather than presenting hard-coded answers. Do not import derived outputs as transaction records.

Import customers and services before appointments. Import appointments before retail_sales and customer_followups. Use customer_id and service_id for joins, appointment_id for retail purchases and attributed follow-ups, and staff_name for capacity. IDs are text. Empty CSV fields mean missing/not applicable. Booleans are lowercase true/false. Each appointment contains one complete service or package; do not split a package into extra revenue rows.

## Scenario 1 — Sarah's sales

Question: Why did Sarah's sales drop even though she was fully booked?

| Metric | Previous four-week weekly average | This week |
|---|---:|---:|
| Completed hours | 38 | 38 |
| Colour-service customers | 5 | 5 |
| Colour customers buying shampoo | 3 | 1 |
| Shampoo purchase rate | 60% | 20% |
| Service revenue | $3,800 | $3,800 |
| Shampoo revenue | $105 | $35 |
| Total service + retail revenue | $3,905 | $3,835 |

Sarah's total sales declined $70 (approximately 1.79%). Shampoo sales declined 66.67%, not total sales. Purchase rate fell 40 percentage points. Matthew's shampoo purchase rate is 60% this week and Sam's 50%, versus approximately 55.56% for each across the baseline. Their lower colour volumes reflect the salon's service-mix change. 'Normal' means their purchase rates remain broadly stable, not that their absolute sales are unchanged.

Use DISTINCT colour-service customers as the denominator and DISTINCT eligible customers with a linked shampoo purchase as the numerator. There is one active appointment per customer per week in this sample. Aggregate four-week numerators and denominators for staff rates, rather than averaging percentages with unequal denominators.

Suggested action: discuss relevant visits with Sarah and review product recommendation or customer needs. Inventory and recommendation records are intentionally absent, so the demo cannot establish stock availability or why someone declined shampoo. With only five colour customers, do not label this proof of poor performance.

## Scenario 2 — a quieter next week

Question: Why is next week only 50% booked, and who could we invite back?

| Metric | Four-week weekly average | Next week |
|---|---:|---:|
| Bookable hours | 114 | 114 |
| New-customer appointments | 24 | 24 |
| Returning-customer appointments | 56 | 26 |
| Total appointments | 80 | 50 |
| New-customer booked hours | 27 | 27 |
| Returning-customer booked hours | 64.25 | 30 |
| Total booked hours | 91.25 | 57 |
| Booking utilisation | 80.04% | 50% |

The 30% new / 70% returning split refers to baseline appointment counts, not hours. Historical weeks vary around the average. Next week has a different mix because returning bookings declined. The entire 34.25-hour gap is in returning-customer hours.

**Fair comparison:** for each target week, count bookings that existed by 23:59:59 on the Sunday immediately before it. A booking was active then if booking_created_at <= cutoff and cancelled_at is blank or > cutoff. Do not filter historical snapshots solely on today's final status. The curated baseline has no net late-booking changes, so its advance-booked and completed hours coincide; that will not always happen in real data.

For these weekly snapshots, a new customer has no completed visit on or before the cutoff. Use first_completed_visit_date from the customer master, including imported pre-period history. Do not equate 'first appointment visible in the CSV' with 'first-ever customer'. The is_new_customer_at_booking field uses the booking creation date instead; it is explicitly a different reference point.

**Follow-up investigation:** require at least three completed visits in the six-month window. Estimate normal return interval using the median days between successive completed visits, then estimate the due date from the last completed visit. These are estimates, not confirmed retention losses.

The resulting file includes all due customers meeting that rule. Exclude customers already booked for a future visit and distinguish those contacted in the last 14 days. Sort suitable remaining customers by urgency and service fit. The generated history produces a broader list than the earlier illustrative 24-person example; use the CSV's actual counts. The list is a pool of possible follow-ups, not an explanation for exactly 30 missing bookings.

Action: review the list, then contact suitable customers and fit appointments to available staff/time slots. Measure contacts, attributed bookings, completed hours and recognised revenue separately. Potential repeat value uses each customer's last service and is not guaranteed revenue. There are historical linked outcomes for demonstrating tracking. Future follow-up success is deliberately unknown at the demo date.

## Scenario 3 — lower revenue per hour

Question: Why are we equally busy but earning less per completed service hour?

| Metric | Four-week weekly average | This week |
|---|---:|---:|
| Completed hours | 91.25 | 91.25 |
| $80/hour services: haircut and blow-dry | 25 hours | 44.75 hours |
| $100/hour treatment service | 10 hours | 10 hours |
| $120/hour colour and haircut | 20 hours | 20 hours |
| $130/hour packages and highlights | 36.25 hours | 16.5 hours |
| Service revenue | $10,112.50 | $9,125.00 |
| Service revenue per completed hour | $110.82 | $100.00 |

19.75 hours shifted from $130/hour work to $80/hour work. That explains $987.50 less service revenue at unchanged total hours: 19.75 × ($130 - $80). The final totals differ slightly from the earlier rough example so every figure reconciles to whole appointments and the agreed service durations.

Action: review whether targeted promotion of colour/treatment/cut packages could increase suitable package demand. Monitor package bookings, utilisation and revenue per completed hour. There is no enquiry, campaign, cost or inventory dataset, so this demo cannot identify why package demand changed, prove that promotion will fix it, calculate enquiry conversion or claim increased profit.

## Modelling boundaries and validation

- Three staff, 38 hours each: Monday–Thursday 09:00–17:00 and Friday 09:00–15:00. All rostered time is assumed bookable; breaks, admin and holidays are not deducted.
- Appointments block the full service duration, including processing time. No concurrent bookings are allowed for the same staff member.
- Sarah has a consistent service mix in the five scenario weeks to isolate the retail effect. Earlier history has more variation. These patterns are intentionally planted for demonstration.
- Cancelled bookings carry no recognised revenue and consume no current capacity. Future bookings have a quoted value but zero recognised service revenue. No discounts, no-shows, refunds or reschedules are modelled.
- No inventory, payroll, individual performance scorecards, stock costs or marketing attribution are included. Retail purchases and staff schedules are retained only because the agreed scenarios need them.
- Source tables should be aggregated separately before combining service revenue and retail revenue, to avoid double-counting appointment revenue after one-to-many joins.
- Never use live dates to recalculate this fixed snapshot. A live production version would need refreshed bookings and statuses.
- The source generation and exported CSVs are checked for unique keys, valid relationships, appointment durations, revenue reconciliation, snapshot counts, future/recognised revenue separation, staff capacity and non-overlapping active appointments.

Recommended first app view: three question cards, each showing the finding, supporting numbers, a drill-down and a suggested next action. Keep customer follow-up outcomes editable only after adding persistent storage.
