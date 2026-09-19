"""Evidence packets for deterministic staff investigations and calendar comparisons."""
from datetime import date,timedelta
import hashlib,json
from .calculations import staff_summary,financial_lines

def packet(intake,name,rows,scope):
    content={'name':name,'scope':scope,'revision':intake.revision}
    return {'id':hashlib.sha256(json.dumps(content,sort_keys=True).encode()).hexdigest()[:16],
        'table':name,'sql':'Approved deterministic calculation: '+name+'; '+scope,
        'rows':rows,'row_count':len(rows),'snapshot_id':intake.revision,'evidence_level':'deterministic_calculation'}

def staff_diagnostic(db,staff,start,end):
    from analyst_engine import QueryBlocked
    names={r['staff_name'] for r in db.intake.tables.get('staff',[])}
    if not staff or not set(staff)<=names:raise QueryBlocked('Choose staff in the current business.')
    if 'staff_daily' not in db.schema or 'financial_lines' not in db.schema:raise QueryBlocked('Staff analysis requires revenue and staff-capacity entitlements and data.')
    a,b=date.fromisoformat(start),date.fromisoformat(end)
    if a>b:raise QueryBlocked('Comparison dates are reversed.')
    stop=str(b+timedelta(days=1));scope=f'{start} through {end}; '+', '.join(staff)
    summary=staff_summary(db.intake,start,stop,staff)
    for r in summary:r['period_end']=end
    # Posting-period service mix, separately aggregated from durations.
    catalog={r['item_id']:r['item_name'] for r in db.intake.tables.get('items',[])}
    mix={}
    for r in financial_lines(db.intake):
        if r['staff_name'] in staff and start<=r['posted_date']<stop and r['item_type']=='service':
            key=(r['staff_name'],r['item_id']);mix.setdefault(key,0);mix[key]+=r['net_revenue']
    rows=[{'staff_name':person,'service_id':iid,'service_name':catalog.get(iid),'service_revenue_aud':value,'period_start':start,'period_end':end} for (person,iid),value in mix.items()]
    return [packet(db.intake,'approved_staff_summary',summary,scope),packet(db.intake,'approved_service_mix',rows,scope)]

def period_diagnostic(db,staff,start,end,old_start,old_end,divisor):
    from analyst_engine import QueryBlocked
    if not 1<=divisor<=52 or not old_start<=old_end<start<=end:raise QueryBlocked('Invalid baseline period.')
    current=staff_diagnostic(db,staff,start,end);previous=staff_diagnostic(db,staff,old_start,old_end)
    before={r['staff_name']:r for r in previous[0]['rows']};rows=[]
    config={r['setting']:r['value'] for r in db.intake.tables.get('customer_profile',[])}
    coverage=config.get('coverage_start')
    complete=bool(coverage and old_start>=coverage and end<=str(db.intake.asof.date()))
    for r in current[0]['rows']:
        prior=before[r['staff_name']]
        for metric in ['service_revenue_aud','retail_revenue_aud','total_revenue_aud','completed_service_hours','bookable_hours','completed_appointments','revenue_per_service_hour','realised_utilisation_pct']:
            value,base=r[metric],prior[metric]
            if base is not None and metric not in ['revenue_per_service_hour','realised_utilisation_pct']:base/=divisor
            rows.append({'staff_name':r['staff_name'],'metric':metric,'current_start':start,'current_end':end,'baseline_start':old_start,'baseline_end':old_end,'baseline_divisor':divisor,
                'current_value':value,'baseline_value':base if complete else None,
                'difference':value-base if complete and value is not None and base is not None else None,
                'percentage_change':(value-base)/base*100 if complete and value is not None and base else None,
                'coverage':'available' if complete else 'insufficient baseline history'})
    return current+previous+[packet(db.intake,'approved_period_comparison',rows,f'{start} to {end} versus {old_start} to {old_end}')]

def calendar_periods(intake):
    today=intake.asof.date();monday=today-timedelta(days=today.weekday());last=monday-timedelta(days=7)
    month=today.replace(day=1)
    def shift_month(d,n):
        index=d.year*12+d.month-1+n
        return date(index//12,index%12+1,1)
    return {'as_of':intake.asof.isoformat(),'timezone':intake.zone.key,
      'last_complete_week':[str(last),str(monday-timedelta(days=1))],
      'weekly_baseline':[str(last-timedelta(weeks=4)),str(last-timedelta(days=1))],
      'current_week_elapsed':[str(monday),str(today)],
      'last_complete_month':[str(shift_month(month,-1)),str(month-timedelta(days=1))],
      'monthly_baseline':[str(shift_month(month,-4)),str(shift_month(month,-1)-timedelta(days=1))]}
