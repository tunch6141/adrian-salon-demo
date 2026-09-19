"""Read-only dynamic SQL over approved business data. No model-written Python executes."""
import hashlib
import json
import sqlite3
import time
from pathlib import Path
import pandas as pd
import sqlglot
from sqlglot import exp

ASOF = '2026-09-13 23:59:59'
RULES = '''Demo date 2026-09-13. This week Sep 7–13; prior four weeks Aug 10–Sep 6; next week Sep 14–20.
Dates inclusive. Source begins 2026-03-16, so March is partial. September completed revenue stops Sep 13.
Service revenue is completed service revenue, GST-exclusive AUD, attributed to appointment date; retail is separate, attributed to sale date.
completed_visits has ONE ROW PER COMPLETED APPOINTMENT. Retail is preaggregated per appointment before joining: do not duplicate service revenue.
booking_records includes cancelled and future appointments. For a snapshot, booking_created_at <= cutoff AND (cancelled_at IS NULL OR cancelled_at > cutoff). Never compare future booked revenue to completed revenue.
capacity_daily is rostered bookable capacity, NOT attendance or actual hours worked. No leave reasons or actual time clock exists.
Utilisation requires summed booked/completed hours divided by matched capacity, NOT mean of row percentages. No adjustments for leave from notes: notes may conflict with rosters.
Colour shampoo purchase rate: distinct colour-service customer/week buyers divided by distinct colour-service customer/week exposures, NOT all appointments. Zero denominator is unknown, not zero.
staff_daily joins daily capacity to completed work with zero-work days included, only through Sep 13. Historical completed utilisation = 100.0*SUM(completed_hours)/NULLIF(SUM(bookable_hours),0), never average percentages.
No profit, costs, recommendation records, inventory, enquiries or external benchmarks. No evidence means unknown. Data has only Sarah, Matthew, Sam.
Context is owner-reported, not verified causality. Never claim a reported cause is established. No automatic exclusions or capacity edits.
'''

class QueryBlocked(ValueError):
    pass

class Database:
    def __init__(self, tables):
        a = tables['appointments'].copy()
        for col in ['appointment_start','booking_created_at','cancelled_at','completed_at']:
            a[col] = pd.to_datetime(a[col])
        if a.appointment_id.duplicated().any():
            raise ValueError('Duplicate appointment IDs')
        s = tables['services']
        if 'service_name' not in a:
            a = a.merge(s[['service_id','service_name','colour_service']], on='service_id', validate='many_to_one')
        a['colour_service'] = a.colour_service.astype(str).str.lower().isin(['true','1'])
        a['visit_date'] = a.appointment_start.dt.strftime('%Y-%m-%d')
        a['week_start'] = (a.appointment_start.dt.normalize()-pd.to_timedelta(a.appointment_start.dt.weekday,unit='D')).dt.strftime('%Y-%m-%d')
        a['hours'] = a.booked_duration_minutes/60
        r = tables['retail_sales'].copy()
        r['sold_at'] = pd.to_datetime(r.sold_at)
        r = r[r.sold_at.le(pd.Timestamp(ASOF))]
        if not r.appointment_id.isin(a.appointment_id).all():
            raise ValueError('Retail references unknown appointments')
        shampoo = r[r.product_name.eq('Colour-care shampoo')].groupby('appointment_id').agg(shampoo_revenue=('retail_revenue_aud','sum'),shampoo_units=('quantity','sum'))
        a = a.merge(shampoo, on='appointment_id', how='left', validate='one_to_one')
        a[['shampoo_revenue','shampoo_units']] = a[['shampoo_revenue','shampoo_units']].fillna(0)
        a['shampoo_buyer'] = a.shampoo_units.gt(0).astype(int)
        cols=['appointment_id','customer_id','staff_name','service_name','visit_date','week_start','hours','service_revenue_aud','colour_service','shampoo_revenue','shampoo_units','shampoo_buyer','booking_channel']
        done = a[a.status.eq('completed') & a.completed_at.le(pd.Timestamp(ASOF))]
        frames = {'completed_visits':done[cols].copy(),
            'booking_records':a[cols+['booking_created_at','cancelled_at','status','quoted_service_amount_aud']].copy(),
            'capacity_daily':tables['staff_capacity'][['staff_name','work_date','bookable_hours']].copy(),
            'retail_transactions':r[['retail_sale_id','appointment_id','staff_name','sold_at','product_name','quantity','retail_revenue_aud']].copy()}
        daily = done.groupby(['staff_name','visit_date']).agg(completed_hours=('hours','sum'),service_revenue_aud=('service_revenue_aud','sum'),completed_appointments=('appointment_id','count')).reset_index()
        cap = tables['staff_capacity'][['staff_name','work_date','bookable_hours']].copy()
        cap['visit_date'] = pd.to_datetime(cap.work_date).dt.strftime('%Y-%m-%d')
        cap = cap.groupby(['staff_name','visit_date'],as_index=False).bookable_hours.sum()
        cap = cap[cap.visit_date.le(ASOF[:10])]
        daily = cap.merge(daily,on=['staff_name','visit_date'],how='left',validate='one_to_one').fillna(0)
        frames['staff_daily'] = daily
        self._open_frames(frames)

    @classmethod
    def from_intake(cls, intake):
        from analytics.views import build_views
        from analytics.rules import rules_for
        obj=cls.__new__(cls)
        obj.intake=intake
        obj.rules=rules_for(intake)
        obj._open_frames(build_views(intake))
        return obj

    def _open_frames(self, frames):
        self.frames=frames
        self.con=sqlite3.connect(':memory:')
        self.schema={}
        for name, frame in frames.items():
            for c in frame:
                if pd.api.types.is_datetime64_any_dtype(frame[c]):
                    frame[c]=frame[c].dt.strftime('%Y-%m-%d %H:%M:%S').where(frame[c].notna(),None)
            frame.to_sql(name,self.con,index=False)
            self.schema[name]=list(frame.columns)
        self.con.execute('PRAGMA query_only=ON')
        self.con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,1000000)
        self.con.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH,12000)
        functions={'sum','count','avg','min','max','round','coalesce','nullif','strftime','date','julianday','abs','lower','upper','substr','cast'}
        def authorizer(action,arg1,arg2,db,source):
            if action==sqlite3.SQLITE_SELECT:return sqlite3.SQLITE_OK
            if action==sqlite3.SQLITE_READ and arg1 in self.schema:return sqlite3.SQLITE_OK
            if action==sqlite3.SQLITE_FUNCTION and (arg2 or '').lower() in functions:return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        self.con.set_authorizer(authorizer)

    def query(self, sql):
        trees=sqlglot.parse(sql,read='sqlite')
        if len(trees)!=1 or not isinstance(trees[0],exp.Select):
            raise QueryBlocked('Only one SELECT query is allowed.')
        tree=trees[0]
        tables=list(tree.find_all(exp.Table))
        if len(tables)!=1 or tables[0].name not in self.schema:
            raise QueryBlocked('Query exactly one approved table. Joins and cross-products are disabled.')
        if any(tree.find_all(exp.Join)) or any(tree.find_all(exp.Subquery)) or tree.args.get('with_'):
            raise QueryBlocked('Joins, nested queries and CTEs are disabled in this pilot.')
        if any(tree.find_all(exp.Window)):
            raise QueryBlocked('Window calculations are not approved in this pilot.')
        # A SELECT must derive values from real columns, never just invent a constant result.
        for projection in tree.expressions:
            if not list(projection.find_all(exp.Column)) and not projection.find(exp.Count):
                raise QueryBlocked('Each result must derive from database columns.')
        deadline=time.monotonic()+2
        self.con.set_progress_handler(lambda: int(time.monotonic()>deadline),1000)
        # Prevent SQL SUM/AVG from quietly treating incomplete costs as a full margin.
        if hasattr(self,'intake'):
            guarded={'gross_profit','direct_cost','allocated_cost','landed_unit_cost'}
            columns={c.name for agg in list(tree.find_all(exp.Sum))+list(tree.find_all(exp.Avg)) for c in agg.find_all(exp.Column)} & guarded
            for col in columns:
                check=tree.copy()
                check.set('expressions',[exp.Count(this=exp.Star()).as_('_rows'),exp.Count(this=exp.column(col)).as_('_known')])
                check.set('order',None)
                try:
                    coverage=self.con.execute(check.sql(dialect='sqlite')).fetchall()
                except sqlite3.Error as exc:
                    raise QueryBlocked('Cost coverage must be explicit before aggregating margin.') from exc
                if any(row[0]!=row[1] for row in coverage):
                    raise QueryBlocked('Cost coverage is incomplete. Show known and missing costs separately; a complete margin is unavailable.')
        cur=self.con.execute(sql)
        rows=cur.fetchmany(501)
        if len(rows)>500:raise QueryBlocked('Result too large. Aggregate or narrow the dates.')
        names=[x[0] for x in cur.description]
        if len(names)!=len(set(names)):raise QueryBlocked('Column aliases must be unique.')
        data=[dict(zip(names,row)) for row in rows]
        revision=getattr(getattr(self,'intake',None),'revision','legacy')
        return {'snapshot_id':revision,'id':hashlib.sha256((revision+sql).encode()).hexdigest()[:16], 'sql':sql,'table':tables[0].name,'rows':data,'row_count':len(data)}

    def close(self):self.con.close()


def reference_value(results, ref):
    index,row,col=ref['result'],ref['row'],ref['column']
    if index<0 or index>=len(results) or row<0 or row>=len(results[index]['rows']):
        raise QueryBlocked('Invalid evidence reference')
    if col not in results[index]['rows'][row]:raise QueryBlocked('Unknown evidence column')
    return results[index]['rows'][row][col]


def validate_chart(results, chart):
    if chart['kind']=='none':return
    i=chart['result']
    if i<0 or i>=len(results):raise QueryBlocked('Chart has no result')
    rows=results[i]['rows']
    if not rows:raise QueryBlocked('Chart has no rows')
    x,y=chart['x'],chart['y']
    series=chart.get('series','')
    if series and any(series not in r for r in rows):raise QueryBlocked('Chart series is not a result column')
    if not series and len({str(r.get(x)) for r in rows})!=len(rows):raise QueryBlocked('Repeated x values require a series column or further aggregation')
    if any(x not in r or y not in r or not isinstance(r[y],(int,float)) for r in rows):
        raise QueryBlocked('Chart must reference numeric query results')
    if chart['kind']=='pie' and (any(r[y]<0 for r in rows) or sum(r[y] for r in rows)<=0):
        raise QueryBlocked('Pie chart requires positive composition values')


def service_diagnostic(db,staff,start,end):
    """Reusable expert analysis, parameterised by people/date; no scenario answers."""
    if hasattr(db,'intake'):
        from analytics.diagnostics import staff_diagnostic
        return staff_diagnostic(db,staff,start,end)
    from datetime import date
    if not staff or not set(staff)<=set(['Sarah','Matthew','Sam']):raise QueryBlocked('Unknown staff in comparison')
    start,end=date.fromisoformat(start).isoformat(),date.fromisoformat(end).isoformat()
    if start>end:raise QueryBlocked('Comparison dates are reversed')
    names=','.join("'"+name+"'" for name in sorted(set(staff)))
    where=f"visit_date BETWEEN '{start}' AND '{end}' AND staff_name IN ({names})"
    summary=db.query(f"SELECT staff_name,COUNT(*) AS completed_appointments,SUM(hours) AS completed_service_hours,SUM(service_revenue_aud) AS service_revenue_aud,SUM(service_revenue_aud)/NULLIF(SUM(hours),0) AS revenue_per_service_hour FROM completed_visits WHERE {where} GROUP BY staff_name ORDER BY staff_name")
    mix=db.query(f"SELECT staff_name,service_name,COUNT(*) AS appointments,SUM(hours) AS completed_service_hours,SUM(service_revenue_aud) AS service_revenue_aud,SUM(service_revenue_aud)/NULLIF(SUM(hours),0) AS revenue_per_service_hour FROM completed_visits WHERE {where} GROUP BY staff_name,service_name ORDER BY service_name,staff_name")
    for output in [summary,mix]:
        for row in output['rows']:row.update(period_start=start,period_end=end)
    result=[summary,mix]
    if len(summary['rows'])==2:
        left,right=summary['rows']
        gap={'left_staff':left['staff_name'],'right_staff':right['staff_name'],'comparison':'left minus right','revenue_difference_aud':left['service_revenue_aud']-right['service_revenue_aud'],'service_hours_difference':left['completed_service_hours']-right['completed_service_hours'],'revenue_per_hour_difference':left['revenue_per_service_hour']-right['revenue_per_service_hour']}
        # Exact additive service-category revenue differences, including absent categories.
        services=sorted(set(r['service_name'] for r in mix['rows']))
        differences=[]
        for name in services:
            per={r['staff_name']:r for r in mix['rows'] if r['service_name']==name}
            lv=per.get(left['staff_name'],{}).get('service_revenue_aud',0)
            rv=per.get(right['staff_name'],{}).get('service_revenue_aud',0)
            differences.append({'service_name':name,'left_staff':left['staff_name'],'right_staff':right['staff_name'],'left_revenue_aud':lv,'right_revenue_aud':rv,'left_minus_right_revenue_aud':lv-rv})
        assert abs(sum(r['left_minus_right_revenue_aud'] for r in differences)-gap['revenue_difference_aud'])<0.01
        for label,rows in [('staff_gap',[gap]),('service_revenue_gap',differences)]:
            result.append({'id':label+'_'+summary['id'],'table':'approved_'+label,'sql':'Python subtraction of the cited summary/mix SQL results (left minus right).','source_result_ids':[summary['id'],mix['id']],'rows':rows,'row_count':len(rows)})
    return result


def validate_claim_numbers(results,claim,context_ids,periods):
    """Reject invented numeric aggregates; a valid citation alone is insufficient."""
    import re
    values=[]
    for ref in claim['evidence']:
        value=reference_value(results,ref)
        if isinstance(value,(int,float)):values.append(float(value))
        elif isinstance(value,str):
            # Numeric portions of cited dates/labels can be quoted, not used as metrics.
            values.extend(float(n) for n in re.findall(r'\d+(?:\.\d+)?',value))
    # Full dates are checked by review; allow date years explicitly present in scope.
    for period in periods:
        if period:
            values.extend(float(n) for n in re.findall(r'\d+',period))
    text=re.sub(r'\b\d{4}-\d{2}-\d{2}\b','',claim['text'])
    numbers=re.findall(r'(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?',text)
    for token in numbers:
        n=float(token.replace(',',''))
        # Permit faithful display rounding, but no model-generated sums or differences.
        decimals=len(token.split('.')[1]) if '.' in token else 0
        tolerance=0.5*(10**(-decimals))+1e-8
        if not any(abs(v-n)<tolerance for v in values):
            raise QueryBlocked('A number in the answer is not present in its cited results. Retrieve a calculated total or difference.')


def bind_claim_values(results,claim,periods):
    """Bind numeric facts from result cells, instead of auditing model-typed numbers."""
    import re
    refs=claim['evidence']
    text=claim['text']
    without_slots=re.sub(r'\[\[(?:\d+|start|end)\]\]','',text)
    if re.search(r'\d',without_slots):
        raise QueryBlocked('Use evidence placeholders for numbers, including years; do not type numerical facts.')
    def replace(match):
        key=match.group(1)
        if key in ['start','end']:
            value=periods[0 if key=='start' else 1]
            if not value:raise QueryBlocked('No date is available for that placeholder')
            return value
        i=int(key)
        if i>=len(refs):raise QueryBlocked('Answer placeholder references a missing citation')
        ref=refs[i];value=reference_value(results,ref)
        style=ref.get('format','plain')
        if value is None:return 'not available'
        if isinstance(value,(int,float)):
            if style=='money':return f'AUD {value:,.2f}'
            if style=='percent':return f'{value:,.2f}%'
            return f'{value:,.2f}'.rstrip('0').rstrip('.')
        return str(value)
    rendered=re.sub(r'\[\[(\d+|start|end)\]\]',replace,text)
    if '[[' in rendered:raise QueryBlocked('Malformed evidence placeholder')
    return rendered


def period_diagnostic(db,staff,start,end,comparison_start,comparison_end,divisor=1):
    if hasattr(db,'intake'):
        from analytics.diagnostics import period_diagnostic as canonical_period
        return canonical_period(db,staff,start,end,comparison_start,comparison_end,divisor)
    from datetime import date
    if divisor<1 or divisor>52:raise QueryBlocked('Invalid baseline divisor')
    for value in [start,end,comparison_start,comparison_end]:date.fromisoformat(value)
    if not (comparison_start<=comparison_end<start<=end):raise QueryBlocked('Comparison period must finish before the current period')
    focus=service_diagnostic(db,staff,start,end)
    baseline=service_diagnostic(db,staff,comparison_start,comparison_end)
    result=focus+baseline
    base={r['staff_name']:r for r in baseline[0]['rows']}
    rows=[]
    metrics=['service_revenue_aud','completed_service_hours','completed_appointments','revenue_per_service_hour']
    for current in focus[0]['rows']:
        old=base.get(current['staff_name'])
        if not old:continue
        for metric in metrics:
            previous=old[metric]/(1 if metric=='revenue_per_service_hour' else divisor)
            actual=current[metric]
            rows.append({'staff_name':current['staff_name'],'metric':metric,'current_start':start,'current_end':end,'baseline_start':comparison_start,'baseline_end':comparison_end,'baseline_divisor':divisor,'current_value':actual,'baseline_value':previous,'difference':actual-previous,'percentage_change':100*(actual-previous)/previous if previous else None})
    result.append({'id':'period_comparison_'+focus[0]['id'],'table':'approved_period_comparison','sql':'Python current minus baseline; baseline totals divided by stated divisor. Rate uses ratio of sums.','source_result_ids':[focus[0]['id'],baseline[0]['id']],'rows':rows,'row_count':len(rows)})
    return result
