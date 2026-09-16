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
        cur=self.con.execute(sql)
        rows=cur.fetchmany(501)
        if len(rows)>500:raise QueryBlocked('Result too large. Aggregate or narrow the dates.')
        names=[x[0] for x in cur.description]
        if len(names)!=len(set(names)):raise QueryBlocked('Column aliases must be unique.')
        data=[dict(zip(names,row)) for row in rows]
        return {'id':hashlib.sha256(sql.encode()).hexdigest()[:12], 'sql':sql,'table':tables[0].name,'rows':data,'row_count':len(data)}

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
    if any(x not in r or y not in r or not isinstance(r[y],(int,float)) for r in rows):
        raise QueryBlocked('Chart must reference numeric query results')
    if chart['kind']=='pie' and (any(r[y]<0 for r in rows) or sum(r[y] for r in rows)<=0):
        raise QueryBlocked('Pie chart requires positive composition values')
