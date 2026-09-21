"""Scoped read-only tools with declared grains. No question-specific routing."""
import json
import re
from datetime import date
import pandas as pd
import sqlglot
from sqlglot import exp
from analyst_engine import QueryBlocked
from analytics.diagnostics import packet, comparable_periods, staff_diagnostic, period_diagnostic
from analytics.calculations import local_date


class ScopeRepairNeeded(QueryBlocked):
    pass

# Data definitions, not instructions for which investigation to run.
DEFINITIONS={
 'financial_lines':('posted_date','posted transaction item; net revenue includes refunds/discounts; direct costs already include allocations; gross profit excludes wages/overheads'),
 'service_sales':('posted_date','service-only financial lines; cannot establish product or all-business financial totals'),
 'customer_visits':('visit_date','one completed booking; customer_type uses master first visit and prior observed visits; unknown is not new'),
 'completed_services':('visit_date','one completed service, not appointment; count distinct booking_id for appointments; hours are booked service duration, not attendance'),
 'staff_daily':('visit_date','one staff/day; sum hours before calculating utilisation; service revenue only'),
 'capacity_daily':('work_date','one availability record; bookable hours already exclude unavailable time; do not subtract reported leave again'),
 'booking_records':('appointment_date','one booking, including future/cancelled; not every booking is completed'),
 'booking_outcomes':('appointment_date','one booking outcome; cancelled/no-show flags are not lost revenue'),
 'staff_return_outcomes':('service_date','one service episode with eligibility and return observation; immature episodes cannot prove churn'),
 'customer_returns':('', 'current customer snapshot of last visit and expected due date; NOT historical visit frequency or cohort retention'),
 'customer_records':('', 'one customer master record; first_completed_visit_date can predate exported booking history'),
 'future_workload':('', 'future scheduled hours and equal-lead-time historical bookings; not earned revenue or proof of demand; period_start identifies horizon'),
 'inventory_coverage':('', 'current stock and movement; configured coverage estimate; unknown/suppressed values remain qualified'),
 'landed_receipts':('received_at','one receipt item with allocated charges; compare same item, unit and currency'),
 'sale_cost_allocations':('posted_at','cost provenance already represented in financial direct_cost; not an additional expense'),
 'customer_value':('', 'one customer; trailing-period revenue/profit/transactions, not arbitrary requested-period history'),
 'receivables':('', 'current outstanding balances, explicit amount basis; not extra revenue'),
 'inventory_movements':('occurred_at','one signed stock movement, not exclusively sales'),
 'quotes':('issued_at','one quote; open outcomes are immature'),
 'supplier_credits':('credited_on','one supplier credit'),
 'price_history':('effective_on','one recorded price change; not proof of its commercial effect'),
}


def catalog(db):
    result={}
    for name,cols in db.schema.items():
        if name=='service_sales':continue
        frame=db.frames[name];dc,definition=DEFINITIONS.get(name,('', 'cleaned canonical records'))
        values={c:frame[c].dropna().unique().tolist()[:8] for c in cols if c in ['item_type','transaction_type','customer_type','status','horizon','cost_provenance']}
        result[name]=dict(columns=cols,date_column=dc,definition=definition,categorical_values=values)
        if dc in frame:
            dates=frame[dc].dropna().astype(str)
            if len(dates):result[name]['available_dates']=[dates.min()[:10],dates.max()[:10]]
    return result


def _column(frame,column):
    if column not in frame.columns:raise QueryBlocked(f'Unknown column {column}. Available columns: '+', '.join(frame.columns))
    return frame[column]


def _filter(frame,item):
    s=_column(frame,item.column);values=item.values
    if item.operator=='not_null':return frame[s.notna()]
    if not values:raise QueryBlocked('A filter needs a value.')
    if pd.api.types.is_numeric_dtype(s):
        try:values=[float(v) for v in values]
        except ValueError:raise QueryBlocked('Numeric filters require numeric values.')
    else:
        s=s.astype('string').str.casefold();values=[str(v).casefold() for v in values]
    op=item.operator
    mask={'eq':lambda:s.eq(values[0]),'ne':lambda:s.ne(values[0]),'in':lambda:s.isin(values),
          'gt':lambda:s.gt(values[0]),'gte':lambda:s.ge(values[0]),'lt':lambda:s.lt(values[0]),
          'lte':lambda:s.le(values[0]),'contains':lambda:s.astype('string').str.contains(str(values[0]),regex=False,na=False)}[op]()
    return frame[mask.fillna(False)]


def resolve_entities(db,entities):
    pairs=[('staff','staff_id','staff_name'),('customers','customer_id','customer_name'),('items','item_id','item_name'),('suppliers','supplier_id','supplier_name')]
    resolved=[]
    for entity in entities or []:
        matches=[]
        for table,key,label in pairs:
            for r in db.intake.tables.get(table,[]):
                if str(entity).casefold() in {str(r.get(key,'')).casefold(),str(r.get(label,'')).casefold()}:
                    matches.append(dict(key=key,value=r[key],name=r.get(label,r[key]),name_column=label))
        unique={(r['key'],r['value']):r for r in matches}
        if len(unique)!=1:raise QueryBlocked(f'Identity {entity!r} is unknown or ambiguous; ask for the exact record rather than omitting it.')
        resolved.extend(unique.values())
    return resolved


def scoped_frame(db,dataset,scope,filters=(),period='current',whole_business_context=False):
    if dataset=='service_sales':raise QueryBlocked('Use financial_lines, with item_type=service when needed. One financial source keeps category coverage explicit.')
    if dataset not in db.frames:raise QueryBlocked(f'Dataset {dataset!r} is unavailable. Choose from the supplied catalogue.')
    frame=db.frames[dataset].copy();original=len(frame)
    entities=resolve_entities(db,scope.entities)
    applied=[]
    if not whole_business_context:
        for key in {e['key'] for e in entities}:
            group=[e for e in entities if e['key']==key]
            col=key if key in frame else group[0]['name_column'] if group[0]['name_column'] in frame else None
            if col is None:raise QueryBlocked(f'{dataset} cannot attribute data to the selected entities. Request whole_business_context only for explicitly contextual evidence.')
            values=[e['value'] if col==key else e['name'] for e in group]
            frame=frame[frame[col].astype('string').str.casefold().isin([str(v).casefold() for v in values])]
            applied.append(dict(column=col,values=values))
    category=scope.category or 'all'
    if dataset=='service_sales' and category not in ['all','service']:raise QueryBlocked('service_sales excludes the requested category. Use financial_lines.')
    if category!='all' and 'item_type' in frame:
        frame=frame[frame.item_type.eq(category)];applied.append(dict(column='item_type',values=[category]))
    dc=DEFINITIONS.get(dataset,('', ''))[0]
    if dc and dc in frame:
        frame[dc]=frame[dc].map(lambda v:str(local_date(str(v),db.intake.zone)) if pd.notna(v) else None)
    start,end=(scope.comparison_start,scope.comparison_end) if period=='comparison' else (scope.start_date,scope.end_date)
    if period!='snapshot' and dc and start and end:
        days=frame[dc].astype('string').str[:10]
        frame=frame[days.ge(start)&days.le(end)];applied.append(dict(column=dc,start=start,end=end))
    for f in filters:
        if f.column==dc and start and end and f.values and period!='snapshot':
            days=[str(v)[:10] for v in f.values]
            if (f.operator in ['eq','in'] and all(d<start or d>end for d in days)) or (f.operator in ['lt','lte'] and days[0]<start) or (f.operator in ['gt','gte'] and days[0]>end):
                raise QueryBlocked('The date filter is outside the active period. Use period=comparison for baseline data, or change frame_question; an empty intersection is not evidence of zero.')
        for existing in applied:
            if f.column==existing['column'] and 'values' in existing and f.operator in ['eq','in']:
                if not {str(v).casefold() for v in f.values}<={str(v).casefold() for v in existing['values']}:
                    raise QueryBlocked('A query filter conflicts with the active scope. Correct frame_question instead of silently changing the subject.')
        frame=_filter(frame,f);applied.append(f.model_dump())
    meta=dict(dataset=dataset,definition=DEFINITIONS.get(dataset,('', 'cleaned canonical records'))[1],
              filters=applied,source_rows=len(frame),available_rows=original,
              period=[start,end] if dc and period!='snapshot' else 'snapshot',
              attribution='whole business context' if whole_business_context else 'selected scope',
              category=category,entities=[e['name'] for e in entities] if not whole_business_context else [])
    return frame,meta


def _aggregate(frame,request,date_column):
    dimensions=list(request.dimensions)
    for c in dimensions:_column(frame,c)
    if request.time_grain!='none':
        if not date_column:raise QueryBlocked('This is a snapshot, not a dated history. Select a historical dataset for time grouping.')
        dates=pd.to_datetime(_column(frame,date_column),errors='coerce')
        if request.time_grain=='week':dates=dates-pd.to_timedelta(dates.dt.weekday,unit='D')
        frame=frame.assign(period_start=dates.dt.strftime('%Y-%m-01' if request.time_grain=='month' else '%Y-%m-%d'))
        dimensions=['period_start']+dimensions
    names=[m.name for m in request.measures]+[r.name for r in request.ratios]
    signatures=[(m.column,m.operation) for m in request.measures]
    if len(signatures)!=len(set(signatures)):
        raise QueryBlocked('Identical aggregations cannot measure different outcomes under different names. Group by the distinguishing category/status or use separately filtered queries.')
    if len(names)!=len(set(names)) or set(names)&set(dimensions):raise QueryBlocked('Output names must be unique and separate from dimensions.')
    if not request.measures:raise QueryBlocked('Choose measures for aggregation; use read_records for individual records.')
    for m in request.measures:
        s=_column(frame,m.column)
        if m.operation in ['sum','mean'] and not pd.api.types.is_numeric_dtype(s):raise QueryBlocked(f'{m.column} is not numeric; use count/count_distinct for IDs.')
        if m.column.endswith(('_pct','_rate','_share','_per_hour')) and m.operation in ['sum','mean']:
            raise QueryBlocked('Do not sum/average ratios. Aggregate the numerator and denominator, then request a ratio.')
    groups=frame.groupby(dimensions,dropna=False,sort=True) if dimensions else [((),frame)]
    rows=[];missing={}
    for key,group in groups:
        if dimensions and not isinstance(key,tuple):key=(key,)
        row=dict(zip(dimensions,key))
        for m in request.measures:
            s=group[m.column];missing[m.name]=missing.get(m.name,0)+int(s.isna().sum())
            if m.operation=='count_distinct':value=int(s.nunique())
            elif m.operation=='count':value=int(s.count())
            elif s.isna().any() or not len(s):value=None
            else:value=getattr(s,m.operation)()
            row[m.name]=value.item() if hasattr(value,'item') else value
        for ratio in request.ratios:
            if ratio.numerator not in row or ratio.denominator not in row:raise QueryBlocked('A ratio must use measures from this query.')
            n,d=row[ratio.numerator],row[ratio.denominator]
            row[ratio.name]=n/d*ratio.scale if n is not None and d not in [None,0] else None
        rows.append(row)
    return rows,missing,dimensions


def query_data(db,request,scope):
    if request.period=='compare':
        if not DEFINITIONS.get(request.dataset,('', ''))[0]:raise QueryBlocked('A snapshot cannot establish historical period changes. Select a dated dataset.')
        if request.time_grain!='none':raise QueryBlocked('For matched period totals use time_grain=none; use a separate trend query for time buckets.')
        if not all([scope.start_date,scope.end_date,scope.comparison_start,scope.comparison_end]):raise ScopeRepairNeeded('Declare both comparison periods in frame_question.')
        if not comparable_periods(scope.start_date,scope.end_date,scope.comparison_start,scope.comparison_end,1):raise ScopeRepairNeeded('Comparison periods must have equal duration or be complete calendar months. Use frame_question with separate named current and baseline windows, not query filters.')
        if scope.end_date>str(db.intake.asof.date()):raise QueryBlocked('Actuals stop at the reporting clock. Use matched elapsed dates, not a future month end.')
        current=query_data(db,request.model_copy(update={'period':'current'}),scope)[0]
        baseline=query_data(db,request.model_copy(update={'period':'comparison'}),scope)[0]
        dimensions=request.dimensions
        maps=[{tuple(r[c] for c in dimensions):r for r in p['rows']} for p in [current,baseline]]
        rows=[];metrics=[m.name for m in request.measures]+[r.name for r in request.ratios]
        for key in sorted(set(maps[0])|set(maps[1]),key=str):
            row=dict(zip(dimensions,key));a,b=maps[0].get(key,{}),maps[1].get(key,{})
            for name in metrics:
                x,y=a.get(name),b.get(name)
                row.update({name+'_current':x,name+'_baseline':y,name+'_change':x-y if x is not None and y is not None else None,
                            name+'_change_pct':(x-y)/y*100 if x is not None and y not in [None,0] else None})
            rows.append(row)
        p=packet(db.intake,request.dataset+'_comparison',rows,json.dumps(scope.model_dump()))
        p['metadata']=dict(current=current['metadata'],baseline=baseline['metadata'],definition='Matched scope and dimensions; current minus baseline. Missing groups remain unknown, not zero.')
        return [p]
    frame,meta=scoped_frame(db,request.dataset,scope,request.filters,request.period,request.whole_business_context)
    rows,missing,dimensions=_aggregate(frame,request,DEFINITIONS.get(request.dataset,('', ''))[0])
    meta.update(missing_values=missing,dimensions=dimensions,measures=[m.model_dump() for m in request.measures],ratios=[r.model_dump() for r in request.ratios],complete_result=len(rows)<=request.limit)
    # Return full aggregated scope total alongside grouped data so composition and
    # absence checks have an independent denominator. No extra model/tool round.
    totals,_,_=_aggregate(frame,request.model_copy(update={'dimensions':[],'time_grain':'none'}),'')
    meta['scoped_totals']=totals[0] if totals else {}
    # A small comparison also needs deterministic differences/ratios between
    # like-for-like groups. Never combine different measures or query scopes.
    comparisons=[]
    if len(dimensions)==1 and 2<=len(rows)<=6:
        for index,left in enumerate(rows):
            for right in rows[index+1:]:
                for measure in request.measures:
                    x,y=left[measure.name],right[measure.name]
                    if isinstance(x,(int,float)) and isinstance(y,(int,float)):
                        comparisons.append(dict(dimension=dimensions[0],left=left[dimensions[0]],right=right[dimensions[0]],measure=measure.name,
                            left_minus_right=x-y,left_divided_by_right=x/y if y else None,right_divided_by_left=y/x if x else None,
                            left_vs_right_change_pct=(x-y)/y*100 if y else None))
    if comparisons:meta['group_comparisons']=comparisons
    p=packet(db.intake,request.dataset,rows[:request.limit],json.dumps(meta,default=str));p['metadata']=meta
    return [p]


def read_records(db,request,scope):
    frame,meta=scoped_frame(db,request.dataset,scope,request.filters)
    for col in request.columns:_column(frame,col)
    selected=frame[request.columns] if request.columns else frame
    meta['complete_result']=len(selected)<=request.limit
    rows=json.loads(selected.head(request.limit).to_json(orient='records',date_format='iso'))
    p=packet(db.intake,request.dataset,rows,json.dumps(meta,default=str));p['metadata']=meta
    return [p]


def staff_performance(db,request,scope):
    if request.compare_periods and not comparable_periods(scope.start_date,scope.end_date,scope.comparison_start,scope.comparison_end,1):
        raise ScopeRepairNeeded('Use frame_question to select matched current and baseline windows before staff comparison.')
    people=resolve_entities(db,scope.entities)
    if any(p['key']!='staff_id' for p in people):raise QueryBlocked('Staff performance requires staff identities.')
    names=[p['name'] for p in people] or [p['staff_name'] for p in db.intake.tables.get('staff',[])]
    results=period_diagnostic(db,names,scope.start_date,scope.end_date,scope.comparison_start,scope.comparison_end,1) if request.compare_periods else staff_diagnostic(db,names,scope.start_date,scope.end_date)
    for result in results:result['metadata']=dict(period=[scope.start_date,scope.end_date],entities=names,category='service and product separately',definition='Matched staff hours, capacity and posted revenue. Service revenue per completed service hour is not revenue per attendance hour.')
    return results


def read_sql(db,request,scope):
    trees=sqlglot.parse(request.sql,read='sqlite')
    if len(trees)!=1 or not isinstance(trees[0],exp.Select):raise QueryBlocked('Only one SELECT is permitted.')
    tree=trees[0];tables=list(tree.find_all(exp.Table))
    if len(tables)!=1:raise QueryBlocked('Use one view per query; use dated canonical relationship views instead of joins.')
    name=tables[0].name
    # Apply scope via literal predicates, without giving model SQL another connection.
    _,meta=scoped_frame(db,name,scope)
    for rule in meta['filters']:
        col=exp.column(rule['column'],table=tables[0].alias or None)
        if 'values' in rule:predicate=exp.In(this=col,expressions=[exp.Literal.string(str(v)) for v in rule['values']])
        else:predicate=exp.Between(this=exp.Anonymous(this='SUBSTR',expressions=[col,exp.Literal.number(1),exp.Literal.number(10)]),low=exp.Literal.string(rule['start']),high=exp.Literal.string(rule['end']))
        tree=tree.where(predicate)
    result=db.query(tree.sql(dialect='sqlite'));result['metadata']=meta|dict(definition=meta['definition']+'; model SQL filters/aggregates must also be inspected',complete_result=False)
    return [result]
