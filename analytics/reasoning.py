"""Commercial investigation paths over existing modules, not new metric formulas.

Core data answers Calculate; optional diagnostics deepen Diagnose/Commercial.
Availability is determined from the actual entitled cleaned SQL schema.
"""
GRAPH={
 'revenue':('financial_lines',['financial_lines','service_sales','booking_outcomes','customer_returns','staff_daily','receivables','quote_conversion'],
   'Separate transaction volume and average transaction value, then mix, discounts/refunds, completed work, customer/staff patterns and context. Revenue is not profit.'),
 'average_transaction_value':('financial_lines',['attachment_pairs','service_sales','customer_value','quote_conversion'],
   'Basket size, mix, attachment, pricing/discounts/refunds, customer/staff mix. Do not infer satisfaction.'),
 'gross_profit':('financial_lines',['sale_cost_allocations','landed_receipts','service_sales','customer_value'],
   'Price, discount, direct cost, mix, landed cost and cost provenance. Unknown costs block margin, not revenue.'),
 'staff_performance':('financial_lines',['completed_services','capacity_daily','staff_daily','service_sales','staff_return_outcomes','booking_outcomes','customer_returns'],
   'Show core revenue, completed work and mix. If available diagnose value per productive hour, utilisation and value per available hour separately. Validate matched hours, skills, allocation, new/existing customer mix, cancellations and context. No inference about effort, attendance or ability.'),
 'productive_hour':('completed_services',['financial_lines','capacity_daily','staff_return_outcomes','booking_outcomes'],
   'Revenue or covered GP per completed service hour measures value of completed work. Also examine utilisation and value per available hour; unused capacity is distinct from poor productivity.'),
 'available_hour':('capacity_daily',['financial_lines','completed_services','staff_daily','booking_outcomes'],
   'Validate genuinely bookable capacity. Distinguish busy low-value work from high-value work with spare capacity. Do not subtract leave twice.'),
 'future_workload':('future_workload',['capacity_daily','booking_outcomes','customer_returns','quote_followup_queue'],
   'Booking maturity, equal-lead-time historical snapshots, day/staff/service skill-compatible capacity, cancellations, overdue customers and quotes. Wait/recheck may be appropriate. Missing booking-created dates prevents maturity judgements, not showing booked work. Booked value is not earned revenue or demand.'),
 'booking_volume':('booking_records',['booking_outcomes','future_workload','capacity_daily','customer_returns','quote_conversion'],
   'Lead time/maturity, cancellations/no-shows/reschedules, new/returning, service/staff/day/source, spare capacity and context.'),
 'cancellations':('booking_outcomes',['booking_records','capacity_daily','future_workload'],
   'Denominator, late cancellation/lead time, concentrations, recovered slots, utilisation and value exposure. Reasons are unknown unless recorded; exposure is not guaranteed loss.'),
 'workforce':('capacity_daily',['staff_daily','future_workload','staff_skills','booking_outcomes'],
   'Validate sustained pressure, temporary context, spare capacity elsewhere, compatible skills/day mismatch, roster changes and extra hours before hiring. Wage cost only if recorded.'),
 'pricing':('pricing_simulations',['financial_lines','service_sales','capacity_daily','quote_conversion','customer_returns'],
   'Price, completed volume, GP/value per hour, utilisation, quotes, return and context. Discount scenarios require spare compatible capacity; assumptions are scenarios, not forecasts.'),
 'profitability_mix':('financial_lines',['service_sales','completed_services','capacity_daily','customer_returns','attachment_pairs','inventory_coverage','landed_receipts'],
   'Category first, then services: revenue/GP/trend/hours/utilisation/return/attachment; products: revenue/GP/movement/stock/cash/returns/suppliers. Never grow or stop a line on revenue alone.'),
 'customers':('customer_value',['customer_returns','financial_lines','staff_return_outcomes','capacity_daily','attachment_pairs'],
   'New/returning counts and revenue, ATV, mix, covered GP, retention, source/staff-associated return and capacity.'),
 'customer_return':('customer_returns',['customer_value','staff_return_outcomes','booking_records'],
   'Expected interval priority explicit, adaptive customer history, service default, business default, unknown. Reminder lead time is not a service interval; follow-up date differs from due date. Compare actual/expected cadence, segments, service episodes, value and context; no dissatisfaction or competitor inference.'),
 'overdue':('customer_returns',['customer_value','future_workload','capacity_daily'],
   'Actual due date and lateness, future booking, service/value, follow-up and suitable capacity. Do not chase a high-value customer who is not due.'),
 'customer_value':('customer_value',['financial_lines','customer_returns','booking_outcomes','customer_concentration'],
   'Trailing twelve calendar months: revenue/covered GP/frequency/ATV/mix/discount/refund/cancellation/consistency/trend. Use own cadence, not rigid monthly activity. Owner-defined segments remain intact; derived value tiers are internal historical distributions.'),
 'concentration':('customer_concentration',['customer_value','financial_lines','customer_returns'],
   'Top one/five/ten revenue and covered GP shares with history, account growth and frequency. Rising concentration is not automatically bad or a forecast loss.'),
 'strategic_potential':('actions',['insights','review_checkpoints','customer_value','quote_conversion'],
   'Potential is owner-reported context. Separate proposal, owner decision and recorded action. Measure approved actions with baseline/revenue/GP/frequency/quotes/mix and checkpoints; never imply a suggestion was executed.'),
 'staff_return':('staff_return_outcomes',['customer_returns','customer_value','service_sales'],
   'Separate existing/new customer service episodes. Return to business counts even with another employee; same-staff return is separate. Do not infer staff quality without context.'),
 'inventory':('inventory_coverage',['financial_lines','landed_receipts','inventory_movements'],
   'Movement, reliability, cost/cash exposure, customer/service relevance and recorded supplier lead times. Do not invent reorder quantities or recovered sales.'),
 'quotes':('quote_followup_queue',['quote_conversion','quote_versions','quote_followups','customer_value'],
   'Maturity, actual follow-up date, conversion and covered commercial value; descriptive association is not causation.'),
 'receivables':('receivables',['customer_value'],
   'Actual balances and recorded payment delay; preserve amount/GST basis. Do not add unpaid balances to commercial revenue.')
}


def catalogue(schema):
    return {name:{'core_view':core,'core_available':core in schema,
            'available_diagnostics':[v for v in optional if v in schema],
            'missing_optional_views':[v for v in optional if v not in schema],
            'commercial_checks':checks}
        for name,(core,optional,checks) in GRAPH.items()}


GUIDANCE='''REASONING GRAPH: Choose the relevant supplied reasoning_family, or leave blank for a factual lookup/general cleaned-data query. Core calculation comes first. Then select only the primary/cross-module diagnostics needed for this question. Deeper analysis is optional: missing optional views must not block an available core answer or trigger endless investigation. A factual lookup needs no commercial recommendation. Stop when supported evidence adequately answers the question. For commercial advice connect measured driver -> feasible proposed action -> assumptions/trade-offs -> owner's decision -> checkpoint. An owner decision is not automatically an action. Record changes still require the separate reviewed approval flow. Reuse existing metric families; use read-only SQL over the supplied cleaned schema when no preset module fits. Do not claim an absent diagnostic was checked.'''
