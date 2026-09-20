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
    if 'financial_lines' not in db.schema:raise QueryBlocked('Staff financial analysis requires the revenue entitlement and data.')
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
    results=[packet(db.intake,'approved_staff_summary',summary,scope),packet(db.intake,'approved_service_mix',rows,scope)]
    if len(summary)==2:
        a,b=summary
        differences=[]
        for metric in ['service_revenue_aud','retail_revenue_aud','total_revenue_aud','completed_appointments','completed_service_hours','bookable_hours','revenue_per_service_hour','realised_utilisation_pct']:
            x,y=a[metric],b[metric]
            differences.append({'first_staff':a['staff_name'],'second_staff':b['staff_name'],'metric':metric,
                'first_value':x,'second_value':y,'difference_first_minus_second':x-y if x is not None and y is not None else None,
                'percentage_difference_vs_second':100*(x-y)/y if x is not None and y else None})
        results.append(packet(db.intake,'approved_staff_differences',differences,scope))
    return results


def comparable_periods(start,end,old_start,old_end,divisor):
    """Equal elapsed durations, or whole calendar months with equal month count."""
    import calendar
    a,b,c,d=map(date.fromisoformat,(start,end,old_start,old_end))
    if not 1<=divisor<=52 or not c<=d<a<=b:return False
    if ((b-a).days+1)*divisor==(d-c).days+1:return True
    def months(x,y):
        if x.day==1 and y.day==calendar.monthrange(y.year,y.month)[1]:
            return (y.year-x.year)*12+y.month-x.month+1
        return None
    current,previous=months(a,b),months(c,d)
    return bool(current and previous and current*divisor==previous)

def period_diagnostic(db,staff,start,end,old_start,old_end,divisor):
    from analyst_engine import QueryBlocked
    if not comparable_periods(start,end,old_start,old_end,divisor):raise QueryBlocked('Comparison periods must have matching duration: a daily result cannot be compared with a weekly total or weekly average.')
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


def revenue_diagnostic(db,staff,start,end):
    """Approved inclusive-period lookup, independent of optional capacity or cost."""
    from analyst_engine import QueryBlocked
    from piece1_validation.metrics import revenue
    if not hasattr(db,'intake') or 'financial_lines' not in db.schema:
        raise QueryBlocked('Revenue requires the approved financial dataset and entitlement.')
    names={r['staff_name']:r['staff_id'] for r in db.intake.tables.get('staff',[])}
    if not set(staff)<=names.keys():raise QueryBlocked('Choose staff in the current business.')
    a,b=date.fromisoformat(start),date.fromisoformat(end)
    if a>b:raise QueryBlocked('Revenue dates are reversed.')
    rows=[]
    for name in staff or ['Whole business']:
        value=revenue(db.intake,str(a),str(b+timedelta(days=1)),names.get(name))
        row={'staff_name':name,'period_start':start,'period_end':end,'coverage':value['status'],
             'limitations':json.dumps(value.get('limitations',[]))}
        for output,key in [('service_revenue_aud','service_revenue'),('retail_revenue_aud','product_revenue'),
                           ('part_revenue_aud','part_revenue'),('total_net_revenue_aud','net_revenue')]:
            row[output]=float(value[key]) if value['status']=='Available' and value.get(key) is not None else None
        rows.append(row)
    return [packet(db.intake,'approved_revenue_summary',rows,f'{start} through {end}')]


def booking_lookup(db,booking_id):
    """Resolve an exact ID first; omit zero padding only if the match is unique."""
    import re
    from analyst_engine import QueryBlocked
    if 'booking_records' not in db.schema:raise QueryBlocked('Booking records are unavailable in the enabled cleaned dataset.')
    requested=booking_id.strip().upper()
    records=db.frames['booking_records'].where(db.frames['booking_records'].notna(),None).to_dict('records')
    matches=[r for r in records if str(r['booking_id']).upper()==requested]
    match_type='exact'
    def key(value):
        m=re.fullmatch(r'([A-Z]+)0*(\d+)',str(value).upper())
        return (m[1],int(m[2])) if m else None
    if not matches and key(requested):
        matches=[r for r in records if key(r['booking_id'])==key(requested)]
        match_type='unique match ignoring leading zero padding'
        if len(matches)>1:raise QueryBlocked('More than one booking matches that shortened ID. Enter the full booking ID.')
    for r in matches:r.update(requested_booking_id=requested,id_match=match_type)
    return [packet(db.intake,'booking_records',matches,'Booking lookup '+requested)]


def revenue_trend(db,staff,start,end,grain,category):
    """Calendar buckets clipped to requested dates, never an arbitrary head(10)."""
    from analyst_engine import QueryBlocked
    if 'financial_lines' not in db.schema:raise QueryBlocked('Revenue data is unavailable.')
    if grain not in ['day','week','month'] or category not in ['service','product','part','all']:
        raise QueryBlocked('Unsupported revenue grouping.')
    names={r['staff_name'] for r in db.intake.tables.get('staff',[])}
    if not set(staff)<=names:raise QueryBlocked('Choose staff in the current business.')
    a,b=date.fromisoformat(start),date.fromisoformat(end)
    if a>b or (b-a).days>3660:raise QueryBlocked('Choose a valid trend period of at most ten years.')
    config={r['setting']:r['value'] for r in db.intake.tables.get('customer_profile',[])}
    coverage=config.get('coverage_start')
    selected=staff or ['Whole business'];groups={}
    def bucket(day):
        return day-timedelta(days=day.weekday()) if grain=='week' else day.replace(day=1) if grain=='month' else day
    def next_bucket(day):
        if grain=='week':return day+timedelta(days=7)
        if grain=='day':return day+timedelta(days=1)
        return date(day.year+day.month//12,day.month%12+1,1)
    day=bucket(a)
    while day<=b:
        stop=next_bucket(day)-timedelta(days=1)
        lo,hi=max(a,day),min(b,stop)
        full=bool(coverage and str(lo)>=coverage and hi<db.intake.asof.date())
        for name in selected:
            groups[name,str(day)]={'staff_name':name,'period_start':str(lo),'period_end':str(hi),
                'bucket_start':str(day),'grain':grain,'category':category,'net_revenue_aud':0.0,
                'coverage':'complete' if full else 'partial or unknown coverage',
                'partial_calendar_bucket':lo!=day or hi!=stop}
        day=next_bucket(day)
    if len(groups)>500:raise QueryBlocked('This grouping exceeds the display limit. Choose a coarser interval.')
    for r in db.frames['financial_lines'].to_dict('records'):
        if not start<=r['posted_date']<=end or (category!='all' and r['item_type']!=category):continue
        if staff and r['staff_name'] not in staff:continue
        name=r['staff_name'] if staff else 'Whole business'
        groups[name,str(bucket(date.fromisoformat(r['posted_date'])))]['net_revenue_aud']+=r['net_revenue']
    rows=list(groups.values())
    for r in rows:r['net_revenue_aud']=round(r['net_revenue_aud'],2)
    totals=[{'staff_name':name,'period_start':start,'period_end':end,'category':category,
        'net_revenue_aud':round(sum(r['net_revenue_aud'] for r in rows if r['staff_name']==name),2),
        'buckets':sum(r['staff_name']==name for r in rows)} for name in selected]
    return [packet(db.intake,'approved_revenue_trend',rows,f'{start} through {end}'),
            packet(db.intake,'approved_trend_totals',totals,f'{start} through {end}')]
