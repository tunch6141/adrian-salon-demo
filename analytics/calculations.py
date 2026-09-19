"""Deterministic commercial calculations. No model calls or source writes."""
from collections import defaultdict
from datetime import date,datetime,timedelta
from decimal import Decimal as D
from statistics import median
import calendar

ZERO=D(0)
def num(value):return None if value in (None,'') else D(str(value))
def ratio(a,b):return float(a/b) if b else None

def local_date(value,zone):
    if not value:return None
    if len(value)==10:return date.fromisoformat(value)
    return datetime.fromisoformat(value).astimezone(zone).date()

def enabled(intake,module):
    return any(r['module']==module and r['entitled'] is True for r in intake.tables.get('capabilities',[]))

def capability_rows(intake):
    from .contracts import DEPENDENCIES
    result=[]
    for module,required in DEPENDENCIES.items():
        missing=[t for t in required if t not in intake.tables]
        result.append({'module':module,'entitled':enabled(intake,module),'state':'Not in plan' if not enabled(intake,module) else 'Missing data' if missing else 'Partially Available' if any(intake.health[t]['state']!='Available' for t in required) else 'Available','missing_tables':', '.join(missing)})
    return result

def financial_lines(intake):
    t=intake.tables;docs={r['transaction_id']:r for r in t.get('transactions',[])};items={r['item_id']:r for r in t.get('items',[])}
    names={r['staff_id']:r['staff_name'] for r in t.get('staff',[])}
    bad={i['record_id'] for i in intake.issues if i['table']=='transaction_items' and i.get('record_id')}
    result=[]
    for line in t.get('transaction_items',[]):
        doc=docs.get(line['transaction_id']);item=items.get(line['item_id'])
        if not doc or not item or doc['status']!='Posted' or not doc['posted_at']:continue
        if datetime.fromisoformat(doc['posted_at'])>intake.asof:continue
        if line['transaction_item_id'] in bad:continue
        net=num(line['net_amount_ex_gst']);cost=num(line.get('direct_cost'))
        if net is None:continue
        result.append({'transaction_item_id':line['transaction_item_id'],'transaction_id':doc['transaction_id'],
            'booking_id':doc.get('booking_id'),'customer_id':doc.get('customer_id'),'staff_id':line.get('staff_id'),
            'staff_name':names.get(line.get('staff_id')),'posted_date':str(local_date(doc['posted_at'],intake.zone)),
            'item_id':line['item_id'],'item_name':item['item_name'],'item_type':item['item_type'],
            'transaction_type':doc['transaction_type'],'quantity':float(num(line['quantity']) or 0),
            'net_revenue':float(net),'direct_cost':float(cost) if cost is not None else None,
            'gross_profit':float(net-cost) if cost is not None else None,
            'discount':float(num(line.get('discount_ex_gst')) or 0),'refund':float(num(line.get('refund_ex_gst')) or 0),
            'cost_provenance':'explicit_cost' if cost is not None else 'unknown'})
    return result

def completed_services(intake):
    t=intake.tables;bookings={r['booking_id']:r for r in t.get('bookings',[])}
    names={r['staff_id']:r['staff_name'] for r in t.get('staff',[])}
    catalog={r['item_id']:r for r in t.get('items',[])};services={r['service_id']:r for r in t.get('services',[])}
    result=[]
    for r in t.get('booking_services',[]):
        b=bookings.get(r['booking_id'])
        if not b or b['status']!='Completed' or not b['appointment_end']:continue
        if datetime.fromisoformat(b['appointment_end'])>intake.asof:continue
        duration=num(r['duration_minutes'])
        if duration is None or duration<0:continue
        # Service-performer attribution is direct evidence, distinct from booking-level alias.
        sid=r.get('staff_id'); service=services.get(r['service_id'],{})
        result.append({'booking_service_id':r['booking_service_id'],'booking_id':b['booking_id'],'customer_id':b['customer_id'],
                       'staff_id':sid,'staff_name':names.get(sid),'service_id':r['service_id'],
                       'service_name':service.get('service_name') or catalog.get(r['service_id'],{}).get('item_name'),
                       'service_family':service.get('service_family'),'visit_date':str(local_date(b['appointment_start'],intake.zone)),
                       'completed_service_hours':float(duration/60),'booking_source':b.get('booking_source')})
    return result

def capacity_rows(intake):
    result=[];names={r['staff_id']:r['staff_name'] for r in intake.tables.get('staff',[])}
    for r in intake.tables.get('staff_availability',[]):
        roster,blocked,bookable=[num(r.get(k)) for k in ['rostered_minutes','nonbookable_minutes','bookable_minutes']]
        valid=all(v is not None and v>=0 for v in [roster,blocked,bookable]) and roster-blocked==bookable
        result.append({'availability_id':r['availability_id'],'staff_id':r['staff_id'],'staff_name':names.get(r['staff_id']),
                       'work_date':r['work_date'],'bookable_hours':float(bookable/60) if valid else None,
                       'rostered_hours':float(roster/60) if roster is not None else None,'capacity_valid':int(valid)})
    return result

def staff_summary(intake,start,end,staff_names=None):
    """Half-open dates. Capacity is already net of unavailable time; never subtract twice."""
    finance=financial_lines(intake);services=completed_services(intake);cap=capacity_rows(intake)
    result=[];bookings={r['booking_id']:r for r in intake.tables.get('bookings',[])}
    for person in intake.tables.get('staff',[]):
        name,sid=person['staff_name'],person['staff_id']
        if staff_names and name not in staff_names:continue
        fs=[r for r in finance if r['staff_id']==sid and start<=r['posted_date']<end]
        ss=[r for r in services if r['staff_id']==sid and start<=r['visit_date']<end]
        cs=[r for r in cap if r['staff_id']==sid and start<=r['work_date']<end]
        service=sum(D(str(r['net_revenue'])) for r in fs if r['item_type']=='service')
        retail=sum(D(str(r['net_revenue'])) for r in fs if r['item_type']=='product')
        hours=sum(D(str(r['completed_service_hours'])) for r in ss)
        capacity=sum(D(str(r['bookable_hours'])) for r in cs if r['bookable_hours'] is not None)
        capacity_ok=bool(cs) and all(r['capacity_valid'] for r in cs) and all(any(c['work_date']==s['visit_date'] for c in cs) for s in ss)
        finance_ok=all(t in intake.tables for t in ['transactions','transaction_items','items']) and not any(i['table'] in ['transactions','transaction_items'] for i in intake.issues)
        unmatched=[r for r in fs if r['item_type']=='service' and (r['booking_id'] not in bookings or not start<=str(local_date(bookings[r['booking_id']]['appointment_start'],intake.zone))<end or bookings[r['booking_id']]['status']!='Completed')]
        priced_bookings={r['booking_id'] for r in fs if r['item_type']=='service'}
        missing_sales={s['booking_id'] for s in ss}-priced_bookings
        rate_ok=not unmatched and not missing_sales and finance_ok
        if not enabled(intake,'revenue') or not all(t in intake.tables for t in ['transactions','transaction_items','items']):
            service=retail=None
        result.append({'staff_id':sid,'staff_name':name,'period_start':start,'period_end_exclusive':end,
          'service_revenue_aud':float(service) if service is not None else None,'retail_revenue_aud':float(retail) if retail is not None else None,'total_revenue_aud':float(sum(D(str(r['net_revenue'])) for r in fs)) if service is not None else None,
          'completed_appointments':len({s['booking_id'] for s in ss}),'completed_service_hours':float(hours),
          'bookable_hours':float(capacity) if capacity_ok and enabled(intake,'staff_capacity') else None,
          'realised_utilisation_pct':100*ratio(hours,capacity) if capacity_ok and capacity and enabled(intake,'staff_capacity') else None,
          'revenue_per_service_hour':ratio(service,hours) if rate_ok and service is not None and enabled(intake,'staff_capacity') else None,
          'unlinked_or_cross_period_service_lines':len(unmatched),'completed_bookings_without_period_sale':len(missing_sales),
          'productivity_basis':'posting-period net service revenue / completed booked service hours; unavailable on unreconciled dates',
          'financial_coverage':'supported_only' if not finance_ok else 'available',
          'evidence_level':'deterministic_calculation'})
    return result

def stock_coverage(intake):
    settings={r['setting']:r['value'] for r in intake.tables.get('customer_profile',[])}
    days=int(settings.get('inventory_lookback_days',90));start=intake.asof-timedelta(days=days)
    low=D(settings.get('inventory_low_stock_days',30));target=D(settings.get('inventory_target_days',60))
    names={r['item_id']:r['item_name'] for r in intake.tables.get('items',[])}
    result=[]
    for item in intake.tables.get('inventory_items',[]):
        iid=item['item_id'];qty=num(item['quantity_on_hand']);cost=num(item['unit_cost']);lead=num(item.get('supplier_lead_days'))
        moves=[r for r in intake.tables.get('inventory_movements',[]) if r['item_id']==iid and r.get('occurred_at') and datetime.fromisoformat(r['occurred_at'])<=intake.asof]
        used=-sum((num(r['quantity_delta']) or 0) for r in moves if r['movement_type'] in ['sale','service_usage'] and datetime.fromisoformat(r['occurred_at'])>=start and (num(r['quantity_delta']) or 0)<0)
        adm=D(str(used))/days; doh=qty/adm if qty is not None and adm else None
        excess=max(qty-adm*target,0) if qty is not None else None
        reconciliation=qty-sum(num(r['quantity_delta']) or 0 for r in moves) if qty is not None else None
        has_opening=any(r['movement_type']=='opening_balance' for r in moves) or any(r['movement_type']=='purchase_received' for r in moves)
        result.append({'item_id':iid,'item_name':names.get(iid),'quantity_on_hand':float(qty) if qty is not None else None,
            'average_daily_movement':float(adm),'lookback_days':days,'days_on_hand':float(doh) if doh is not None else None,
            'stock_state':'unknown' if qty is None else 'no movement' if not adm else 'low stock' if doh<=low else 'excess stock' if doh>target else 'within configured range',
            'unit_cost':float(cost) if cost is not None else None,'excess_units':float(excess) if excess is not None else None,
            'excess_value_at_cost':float(excess*cost) if excess is not None and cost is not None else None,
            'supplier_lead_days':float(lead) if lead is not None else None,
            'projected_stock_before_receipt':float(qty-adm*lead) if qty is not None and lead is not None else None,
            'anomaly_suppressed':int(item.get('anomaly_suppressed') is True),
            'reliability':item.get('movement_reliability') or 'unassessed',
            'ledger_difference':float(reconciliation) if has_opening and reconciliation is not None else None,
            'estimate_note':'Historical movement estimate, not guaranteed demand. On-order arrival dates not assumed.'})
    return result

def landed_receipts(intake):
    receipts={r['receipt_id']:r for r in intake.tables.get('purchase_receipts',[])};lines=intake.tables.get('purchase_receipt_items',[])
    totals=defaultdict(lambda:D(0))
    for r in lines:
        q,c=num(r['quantity']),num(r['purchase_unit_cost'])
        if q is not None and c is not None:totals[r['receipt_id']]+=q*c
    result=[]
    for r in lines:
        parent=receipts.get(r['receipt_id']);q=num(r['quantity']);unit=num(r['purchase_unit_cost'])
        if not parent or not q or unit is None:continue
        shared=[num(parent.get(k)) for k in ['freight_ex_gst','duty_ex_gst','other_charges_ex_gst']]
        direct=[num(r.get(k)) for k in ['direct_freight_ex_gst','direct_duty_ex_gst','direct_other_ex_gst']]
        complete=all(x is not None for x in shared+direct) and totals[r['receipt_id']]>0
        allocated=sum(shared)*q*unit/totals[r['receipt_id']] if complete else None
        landed=(q*unit+sum(direct)+allocated)/q if complete else None
        result.append({'receipt_item_id':r['receipt_item_id'],'receipt_id':r['receipt_id'],'supplier_id':parent['supplier_id'],'item_id':r['item_id'],
                       'received_at':parent['received_at'],'quantity':float(q),'purchase_unit_cost':float(unit),
                       'allocated_shared_charges':float(allocated) if allocated is not None else None,
                       'landed_unit_cost':float(landed) if landed is not None else None,'currency':parent['currency'],
                       'unit_of_measure':r['unit_of_measure'],'cost_state':'exact_source_calculation' if complete else 'incomplete acquisition charges'})
    return result

def quote_queue(intake):
    asof=intake.asof.date();settings={r['setting']:r['value'] for r in intake.tables.get('customer_profile',[])};delay=int(settings.get('quote_followup_days',3));result=[]
    for q in intake.tables.get('quotes',[]):
        if q['status']!='Open' or q.get('no_more_followup') is True:continue
        if q.get('snoozed_until') and date.fromisoformat(q['snoozed_until'])>asof:continue
        follows=sorted([f for f in intake.tables.get('quote_followups',[]) if f['quote_id']==q['quote_id'] and datetime.fromisoformat(f['contacted_at'])<=intake.asof],key=lambda r:r['contacted_at'])
        last=follows[-1] if follows else None
        if q.get('owner_followup_date'):due=q['owner_followup_date'];basis='owner_override'
        elif last:due=last.get('next_action_date') or str(local_date(last['contacted_at'],intake.zone)+timedelta(days=delay));basis='followup_explicit' if last.get('next_action_date') else 'default_after_followup'
        elif q.get('source_followup_date'):due=q['source_followup_date'];basis='source_date'
        else:due=str(local_date(q['issued_at'],intake.zone)+timedelta(days=delay));basis='default_after_issue'
        value,cost=num(q['value_ex_gst']),num(q.get('direct_cost'))
        result.append({'quote_id':q['quote_id'],'customer_id':q['customer_id'],'due_date':due,'due_basis':basis,
          'days_overdue':max((asof-date.fromisoformat(due)).days,0),'due_now':int(due<=str(asof)),
          'quote_value':float(value) if value is not None else None,'potential_gross_profit':float(value-cost) if value is not None and cost is not None else None,
          'attempts':len(follows),'expires_on':q.get('expires_on'),'estimate_note':'Potential value, not earned revenue. Age alone does not close quote.'})
    return sorted(result,key=lambda r:(-r['due_now'],-(r['potential_gross_profit'] if r['potential_gross_profit'] is not None else r['quote_value'] or 0),r['due_date']))

def receivables(intake):
    asof=intake.asof.date();historical=defaultdict(list);invoices=[]
    for inv in intake.tables.get('invoices',[]):
        if date.fromisoformat(inv['issued_on'])>asof:continue
        pays=sorted([p for p in intake.tables.get('payments',[]) if p['invoice_id']==inv['invoice_id'] and date.fromisoformat(p['paid_on'])<=asof],key=lambda p:p['paid_on'])
        amount=num(inv['invoice_amount']);credit=num(inv.get('credit_amount'));total=sum(num(p['amount']) or 0 for p in pays)
        if amount is None or credit is None:continue
        outstanding=amount-credit-total;due=date.fromisoformat(inv['due_on'])
        if outstanding<=0 and pays:
            running=D(0)
            for p in pays:
                running+=num(p['amount']) or 0
                if running+credit>=amount:
                    historical[inv['customer_id']].append((date.fromisoformat(p['paid_on'])-due).days);break
        invoices.append((inv,outstanding,due))
    result=[]
    for inv,balance,due in invoices:
        if balance<=0:continue
        delay=max((asof-due).days,0);history=historical[inv['customer_id']];normal=median(history) if history else None
        result.append({'invoice_id':inv['invoice_id'],'customer_id':inv['customer_id'],'due_date':str(due),
           'outstanding_balance':float(balance),'days_overdue':delay,'normal_payment_delay_days':normal,
           'days_beyond_normal':max(delay-normal,0) if normal is not None else None,'history_count':len(history),
           'currency':inv['currency'],'amount_basis':inv['amount_basis'],'collection_reason':'compare actual lateness with customer history; motive unknown'})
    return sorted(result,key=lambda r:(-(r['days_beyond_normal'] or 0),-r['outstanding_balance']))

def bookings_at(intake,cutoff,start,end):
    latest={}
    for event in intake.tables.get('booking_history',[]):
        if not event.get('event_at'):continue
        when=datetime.fromisoformat(event['event_at'])
        if when<=cutoff:
            previous=latest.get(event['booking_id'])
            if previous is None or when>datetime.fromisoformat(previous['event_at']):latest[event['booking_id']]=event
    result=[]
    for b in intake.tables.get('bookings',[]):
        r=latest.get(b['booking_id'])
        if not r or r['status_after'] not in ['Booked','Completed']:continue
        a,z=r.get('start_after'),r.get('end_after')
        if not a or not z:continue
        day=local_date(a,intake.zone)
        if not start<=day<end:continue
        result.append({'booking_id':b['booking_id'],'staff_id':r['staff_id_after'],'customer_id':b['customer_id'],
                       'appointment_date':str(day),'hours':(datetime.fromisoformat(z)-datetime.fromisoformat(a)).total_seconds()/3600,
                       'booked_value':float(num(r['expected_value_ex_gst_after'])) if num(r['expected_value_ex_gst_after']) is not None else None})
    return result

def future_workload(intake):
    result=[]
    monday=intake.asof.date()-timedelta(days=intake.asof.weekday())+timedelta(days=7)
    names={r['staff_id']:r['staff_name'] for r in intake.tables.get('staff',[])};capacity=capacity_rows(intake)
    periods=[('next_week',monday,monday+timedelta(days=7)),('next_7_days',intake.asof.date()+timedelta(days=1),intake.asof.date()+timedelta(days=8)),('next_14_days',intake.asof.date()+timedelta(days=1),intake.asof.date()+timedelta(days=15))]
    for label,start,end in periods:
        booked=bookings_at(intake,intake.asof,start,end)
        # Compare each historical target at the same weekday and local wall-clock lead time.
        for sid,name in names.items():
            current=[r for r in booked if r['staff_id']==sid]
            baselines=[]
            for w in range(1,5):
                shift=timedelta(weeks=w)
                historical=bookings_at(intake,intake.asof-shift,start-shift,end-shift)
                baselines.append(sum(r['hours'] for r in historical if r['staff_id']==sid))
            caps=[r for r in capacity if r['staff_id']==sid and str(start)<=r['work_date']<str(end)]
            available=sum(r['bookable_hours'] or 0 for r in caps) if caps and all(r['capacity_valid'] for r in caps) else None
            hours=sum(r['hours'] for r in current)
            result.append({'horizon':label,'staff_name':name,'period_start':str(start),'period_end_exclusive':str(end),'booked_hours':hours,
                'booked_value':sum(r['booked_value'] for r in current) if all(r['booked_value'] is not None for r in current) else None,
                'available_bookable_hours':available,'gap_hours':available-hours if available is not None else None,
                'booked_utilisation_pct':hours/available*100 if available else None,'same_lead_time_four_week_average_hours':sum(baselines)/4,
                'interpretation_limit':'Current booked position, not market demand or earned revenue. Current roster, not historical roster snapshots.'})
    return result

def customer_returns(intake):
    services=completed_services(intake);by=defaultdict(dict)
    for r in services:by[r['customer_id']][r['booking_id']]=r
    catalog={r['service_id']:r for r in intake.tables.get('services',[])}
    config={r['setting']:r['value'] for r in intake.tables.get('customer_profile',[])};minimum=int(config.get('adaptive_min_visits',3));result=[]
    for c in intake.tables.get('customers',[]):
        visits=sorted(by[c['customer_id']].values(),key=lambda r:r['visit_date'])
        dates=sorted({date.fromisoformat(r['visit_date']) for r in visits})
        due=c.get('owner_next_visit_date');basis='explicit_due_date' if due else 'unknown';interval=None
        if not due and len(dates)>=minimum:
            interval=median([(b-a).days for a,b in zip(dates,dates[1:])]);basis='adaptive_median_fixture_policy'
        if not due and interval is None and visits:
            interval=num(catalog.get(visits[-1]['service_id'],{}).get('default_return_days'));basis='service_default' if interval is not None else 'unknown'
        if not due and interval is None and visits:
            interval=num(c.get('default_return_days')) or num(config.get('default_return_days'));basis='business_default' if interval is not None else 'unknown'
        if not due and interval is not None:due=str(dates[-1]+timedelta(days=float(interval)))
        closed=any(f['customer_id']==c['customer_id'] and f.get('closed') is True for f in intake.tables.get('customer_followups',[]))
        result.append({'customer_id':c['customer_id'],'customer_name':c['customer_name'],'completed_visits':len(visits),
            'last_visit':str(dates[-1]) if dates else None,'expected_due_date':due,'due_basis':basis,
            'days_overdue':max((intake.asof.date()-date.fromisoformat(due)).days,0) if due else None,
            'followup_closed':int(closed),'interpretation_limit':'Closed follow-up is not proof of churn. Reason for non-return unknown.'})
    return result

def pricing_simulation(price,volume,new_price,cost=None,spare_hours=None,hours_per_unit=None):
    p,q,n=map(D,map(str,[price,volume,new_price]))
    if p<=0 or q<0 or n<=0:raise ValueError('Prices must be positive and volume nonnegative.')
    revenue_break=q*p/n
    gp_break=None if cost is None or n<=D(str(cost)) else q*(p-D(str(cost)))/(n-D(str(cost)))
    extra=max((gp_break if gp_break is not None else revenue_break)-q,D(0))
    return {'revenue_break_even_volume':float(revenue_break),'gross_profit_break_even_volume':float(gp_break) if gp_break is not None else None,
            'additional_hours_required':float(extra*D(str(hours_per_unit))) if hours_per_unit is not None else None,
            'capacity_feasible':extra*D(str(hours_per_unit))<=D(str(spare_hours)) if spare_hours is not None and hours_per_unit is not None else None,
            'assumption':'Unchanged unit cost and service duration; simulation is not a forecast.'}

def staff_return_outcomes(intake):
    """Eligible episodes only; a return to any member of the business counts."""
    rows=completed_services(intake);customers={r['customer_id']:r for r in intake.tables.get('customers',[])}
    services={r['service_id']:r for r in intake.tables.get('services',[])}
    config={r['setting']:r['value'] for r in intake.tables.get('customer_profile',[])}
    groups=defaultdict(list)
    for r in rows:groups[r['customer_id']].append(r)
    result=[]
    for cid,episodes in groups.items():
        dates=sorted({date.fromisoformat(r['visit_date']) for r in episodes});first=customers.get(cid,{}).get('first_completed_visit_date')
        for r in episodes:
            day=date.fromisoformat(r['visit_date']);prior=[d for d in dates if d<=day]
            # Use only history available at the service episode, never future gaps.
            interval=median([(b-a).days for a,b in zip(prior,prior[1:])]) if len(prior)>=int(config.get('adaptive_min_visits',3)) else None
            basis='adaptive_prior_history' if interval is not None else 'service_default'
            if interval is None:interval=num(services.get(r['service_id'],{}).get('default_return_days'))
            if interval is None:interval=num(config.get('default_return_days'));basis='business_default'
            deadline=day+timedelta(days=float(interval)) if interval is not None else None
            future=[d for d in dates if d>day];next_visit=future[0] if future else None
            eligible=deadline is not None and deadline<=intake.asof.date()
            result.append({'booking_service_id':r['booking_service_id'],'staff_name':r['staff_name'],'customer_id':cid,'service_date':str(day),
                'customer_type':'new' if first==str(day) else 'existing' if first and first<str(day) else 'unknown',
                'eligible_episode':int(eligible),'returned_to_business':int(next_visit<=deadline) if eligible and next_visit else 0 if eligible else None,
                'expected_by':str(deadline) if deadline else None,'interval_basis':basis,
                'interpretation_limit':'Service-episode association, not customer ownership or causation. Current explicit due date is not retroactively applied to old episodes.'})
    return result

def booking_outcomes(intake):
    settings={r['setting']:r['value'] for r in intake.tables.get('customer_profile',[])}
    late_hours=float(settings.get('late_cancellation_hours',24))
    recovery={r['cancelled_booking_id']:r for r in intake.tables.get('slot_recovery',[])}
    history=defaultdict(list)
    for h in intake.tables.get('booking_history',[]):history[h['booking_id']].append(h)
    result=[]
    for b in intake.tables.get('bookings',[]):
        if not b.get('appointment_start'):continue
        start=datetime.fromisoformat(b['appointment_start'])
        if start>intake.asof:continue
        cancelled=[h for h in history[b['booking_id']] if h['event_type']=='cancelled' and datetime.fromisoformat(h['event_at'])<=intake.asof]
        when=datetime.fromisoformat(max(cancelled,key=lambda h:h['event_at'])['event_at']) if cancelled else None
        lead=(start-when).total_seconds()/3600 if when else None
        result.append({'booking_id':b['booking_id'],'staff_id':b.get('staff_id'),'appointment_date':str(start.astimezone(intake.zone).date()),
            'status':b['status'],'cancelled':int(b['status']=='Cancelled'),'no_show':int(b['status']=='No-show'),
            'cancellation_lead_hours':lead,'late_cancellation':int(0<=lead<=late_hours) if lead is not None else None,
            'recovered_minutes':float(num(recovery[b['booking_id']]['recovered_minutes'])) if b['booking_id'] in recovery else None,
            'expected_booking_value':float(num(b['expected_value_ex_gst'])) if num(b['expected_value_ex_gst']) is not None else None,
            'interpretation_limit':'Booking value is exposure, not guaranteed lost revenue. Missing recovery record is unknown recovery.'})
    return result
