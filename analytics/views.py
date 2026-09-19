"""Approved SQL views at declared grains. Test expectations are never loaded here."""
from collections import defaultdict
from datetime import date,timedelta
import pandas as pd
from .calculations import (financial_lines,completed_services,capacity_rows,stock_coverage,landed_receipts,
    quote_queue,receivables,future_workload,customer_returns,capability_rows,enabled,staff_return_outcomes,booking_outcomes,pricing_simulation)
from .costing import allocate_costs

VIEW_MODULES={'staff_return_outcomes':'customers','booking_outcomes':'bookings','pricing_simulations':'pricing','customer_concentration':'customers','financial_lines':'revenue','completed_services':'staff_capacity','capacity_daily':'staff_capacity',
 'staff_daily':'staff_capacity','inventory_coverage':'inventory','landed_receipts':'suppliers','sale_cost_allocations':'gross_margin',
 'quote_followup_queue':'quotes','receivables':'receivables','future_workload':'bookings','customer_returns':'customers',
 'customer_value':'customers','service_sales':'services','attachment_pairs':'services','quote_conversion':'quotes'}

def build_views(intake):
    finance=financial_lines(intake) if enabled(intake,'revenue') else [];services=completed_services(intake);capacity=capacity_rows(intake)
    allocations=allocate_costs(intake) if enabled(intake,'gross_margin') else []
    byline=defaultdict(list)
    for r in allocations:byline[r['transaction_item_id']].append(r)
    for r in finance:
        aa=byline[r['transaction_item_id']]
        if not enabled(intake,'gross_margin'):r.update(direct_cost=None,gross_profit=None,cost_provenance='not_in_plan')
        elif r['direct_cost'] is None and aa and all(x['allocated_cost'] is not None for x in aa):
            r['direct_cost']=sum(a['allocated_cost'] for a in aa);r['gross_profit']=r['net_revenue']-r['direct_cost']
            r['cost_provenance']=' + '.join(sorted({a['provenance'] for a in aa}))
    daily=defaultdict(lambda:{'bookable_hours':0,'completed_hours':0,'service_revenue_aud':0,'completed_appointments':set(),'capacity_valid':True,'has_capacity':False})
    for c in capacity:
        if c['work_date']>str(intake.asof.date()):continue
        r=daily[c['staff_name'],c['work_date']];r['has_capacity']=True;r['bookable_hours']+=c['bookable_hours'] or 0;r['capacity_valid'] &= bool(c['capacity_valid'])
    for s in services:
        r=daily[s['staff_name'],s['visit_date']];r['completed_hours']+=s['completed_service_hours'];r['completed_appointments'].add(s['booking_id'])
    for f in finance:
        if f['item_type']=='service':daily[f['staff_name'],f['posted_date']]['service_revenue_aud']+=f['net_revenue']
    staff_daily=[]
    for (name,day),r in sorted(daily.items(),key=lambda item:str(item[0])):
        staff_daily.append({'staff_name':name,'visit_date':day,'bookable_hours':r['bookable_hours'] if r['capacity_valid'] and r['has_capacity'] else None,
            'completed_hours':r['completed_hours'],'service_revenue_aud':r['service_revenue_aud'] if enabled(intake,'revenue') else None,'completed_appointments':len(r['completed_appointments'])})
    rows={'staff_return_outcomes':staff_return_outcomes(intake),'booking_outcomes':booking_outcomes(intake),'financial_lines':finance,'completed_services':services,'capacity_daily':capacity,'staff_daily':staff_daily,
          'inventory_coverage':stock_coverage(intake),'landed_receipts':landed_receipts(intake),'sale_cost_allocations':allocations,
          'quote_followup_queue':quote_queue(intake),'receivables':receivables(intake),'future_workload':future_workload(intake),
          'customer_returns':customer_returns(intake),'capability_status':capability_rows(intake)}
    # Trailing 12 calendar months, not an arbitrary fixed 365-day proxy.
    end=intake.asof.date();start=end.replace(year=end.year-1) if not (end.month==2 and end.day==29) else end.replace(year=end.year-1,day=28)
    cv=defaultdict(list)
    for r in finance:
        if str(start)<=r['posted_date']<=str(end):cv[r['customer_id']].append(r)
    total=sum(r['net_revenue'] for group in cv.values() for r in group)
    rows['customer_value']=[{'customer_id':cid,'period_start':str(start),'period_end':str(end),'net_revenue':sum(x['net_revenue'] for x in group),
        'gross_profit':sum(x['gross_profit'] for x in group) if all(x['gross_profit'] is not None for x in group) else None,
        'transaction_count':len({x['transaction_id'] for x in group}),'revenue_share_pct':sum(x['net_revenue'] for x in group)/total*100 if total else None} for cid,group in cv.items()]
    ranked=sorted(rows['customer_value'],key=lambda r:r['net_revenue'],reverse=True)
    rows['customer_concentration']=[{'top_customers':n,'revenue_share_pct':sum(r['net_revenue'] for r in ranked[:n])/total*100 if total else None,'exposure_note':'Historical concentration, not a forecast of loss.'} for n in [1,5,10]]
    rows['pricing_simulations']=[{'scenario_id':r['scenario_id'],'service_id':r['service_id'],**pricing_simulation(r['baseline_price'],r['baseline_volume'],r['proposed_price'],r['unit_cost'],r['spare_bookable_hours'],r['hours_per_service'])} for r in intake.tables.get('pricing_scenarios',[])]
    rows['service_sales']=[r for r in finance if r['item_type']=='service']
    # Descriptive co-occurrence, no arbitrary significance threshold or automatic recommendation.
    baskets=defaultdict(set)
    for r in finance:
        if r['transaction_type']=='Sale' and r['quantity']>0:baskets[r['transaction_id']].add(r['item_id'])
    counts=defaultdict(int);pairs=defaultdict(int)
    for basket in baskets.values():
        for a in basket:
            counts[a]+=1
            for b in basket:
                if a!=b:pairs[a,b]+=1
    rows['attachment_pairs']=[{'item_a':a,'item_b':b,'pair_transactions':v,'eligible_a_transactions':counts[a],'all_transactions':len(baskets),
        'support':v/len(baskets),'confidence':v/counts[a],'lift':v*len(baskets)/(counts[a]*counts[b]),
        'interpretation_limit':'Descriptive association only. Assess sample size, like-for-like opportunity and commercial value before recommending.'} for (a,b),v in pairs.items()]
    qgroups=defaultdict(list);followed={f['quote_id'] for f in intake.tables.get('quote_followups',[])}
    for q in intake.tables.get('quotes',[]):qgroups[q['quote_id'] in followed].append(q)
    rows['quote_conversion']=[{'followed_up':int(flag),'issued_quotes':len(group),'won_quotes':sum(q['status']=='Won' for q in group),
        'open_quotes':sum(q['status']=='Open' for q in group),'won_share_of_issued_pct':sum(q['status']=='Won' for q in group)/len(group)*100,
        'interpretation_limit':'Descriptive issued-quote cohort, open outcomes immature. Follow-up association is not causal.'} for flag,group in qgroups.items()]
    frames={}
    for name,records in rows.items():
        if name in VIEW_MODULES and not enabled(intake,VIEW_MODULES[name]):continue
        if records:frames[name]=pd.DataFrame(records)
    # Expose selected canonical operational records only within their enabled modules.
    raw_modules={'inventory_movements':'inventory','supplier_credits':'suppliers','vehicles':'customers','services':'services','service_components':'services','staff_skills':'staff_capacity','suppliers':'suppliers',
      'purchase_orders':'suppliers','quotes':'quotes','quote_versions':'quotes','quote_followups':'quotes',
      'insights':'insights','actions':'insights','review_checkpoints':'insights','price_history':'pricing'}
    for name,module in raw_modules.items():
        if enabled(intake,module) and intake.tables.get(name):
            frame=pd.DataFrame(intake.tables[name])
            from piece1_validation.adapter import SCHEMA
            for field,typ in SCHEMA[name].items():
                if field in frame and typ=='number':frame[field]=pd.to_numeric(frame[field],errors='coerce')
            frames[name]=frame
    return frames
