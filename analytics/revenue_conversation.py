"""Persisted revenue scope and reconciled displays over the cleaned snapshot."""
import re
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field
from analyst_engine import QueryBlocked, query_period
from .diagnostics import packet


class RevenueView(BaseModel):
    staff: list[str] | None = Field(default=None, description='Null inherits previous people; [] explicitly means whole business. Explicit names replace the previous people.')
    start_date: str | None = Field(default=None, description='Inclusive ISO date; null inherits previous revenue period')
    end_date: str | None = Field(default=None, description='Inclusive ISO date; null inherits previous revenue period')
    category: Literal['service','product','part','all'] | None = Field(default=None, description='Null inherits previous category; never default a product follow-up to service')
    breakdown: Literal['total','item'] | None = Field(default=None, description='Item for product composition; null inherits previous display')
    chart: Literal['none','bar','pie'] | None = Field(default=None, description='Null inherits prior chart; pie for composition, not time series')
    details: bool = False


def prior_revenue_scope(history):
    """Use the latest data turn only; do not resurrect an older topic."""
    for turn in reversed(history):
        if turn.get('status') in ['context','explanation']:continue
        p=turn.get('plan',{})
        if p.get('financial'):return dict(p['financial'])
        if p.get('trend'):
            return dict(p['trend'])
        # Compatibility with conversations started before scope persistence.
        # Accept only one straightforward executed financial query, with no
        # other predicates that could be lost when rebuilding the scope.
        queries=[r['sql'] for r in turn.get('retrieved_scopes',[]) if r.get('table')=='financial_lines']
        if not queries:queries=p.get('queries',[])
        if len(queries)!=1:return None
        import sqlglot
        from sqlglot import exp
        try:tree=sqlglot.parse_one(queries[0],read='sqlite')
        except Exception:return None
        if len(list(tree.find_all(exp.Table)))!=1 or next(tree.find_all(exp.Table)).name!='financial_lines':return None
        where=tree.args.get('where')
        if not where:return None
        if any(c.name not in ['staff_name','item_type','posted_date'] for c in where.find_all(exp.Column)):return None
        if any(isinstance(n,(exp.Or,exp.Not,exp.NEQ,exp.Like)) for n in where.walk()):return None
        staff=[];category=None
        for n in where.walk():
            if isinstance(n,(exp.EQ,exp.In)) and isinstance(n.this,exp.Column):
                values=[n.expression] if isinstance(n,exp.EQ) else n.expressions
                if not all(isinstance(v,exp.Literal) and v.is_string for v in values):return None
                if n.this.name=='staff_name':staff=[v.this for v in values]
                if n.this.name=='item_type' and len(values)==1:category=values[0].this
        period=query_period([{'sql':queries[0]}])
        if not period or category not in ['service','product','part']:return None
        return dict(staff=staff,start_date=period[0],end_date=period[1],category=category,breakdown='total',chart='none')
    return None


def resolve_revenue_scope(plan, question, history, staff_rows):
    previous=prior_revenue_scope(history)
    request=plan.financial
    names=[r['staff_name'] for r in staff_rows if re.search(r'(?<!\w)'+re.escape(r['staff_name'])+r'(?!\w)',question,re.I)]
    # Guard the common elliptical participant change even if the planner
    # incorrectly selects its default staff-performance module.
    rest=re.sub(r'^\s*(?:and\s+)?what about\s+','',question,flags=re.I)
    for name in names:rest=re.sub(r'\b'+re.escape(name)+r'\b','',rest,flags=re.I)
    people_only=bool(names and re.match(r'^\s*(?:and\s+)?what about\b',question,re.I) and not re.sub(r'\band\b|\bplease\b|[\s,?!.&]','',rest,flags=re.I))
    if previous and people_only:
        if previous.get('grain'):
            from analyst_ai import TrendRequest
            plan.trend=TrendRequest(**{**previous,'staff':names})
            plan.financial=plan.diagnostic=plan.revenue=None
            plan.queries=[]
            return
        request=RevenueView(**{**previous,'staff':names})
    if request is None:return
    values=request.model_dump()
    for field in ['staff','start_date','end_date','category','breakdown','chart']:
        if values[field] is None:values[field]=(previous or {}).get(field)
    values['breakdown']=values['breakdown'] or 'total'
    values['chart']=values['chart'] or 'none'
    if any(values[k] is None for k in ['staff','start_date','end_date','category']):
        raise QueryBlocked('Please specify the people, revenue type and period for this request.')
    known={r['staff_name'] for r in staff_rows}
    if not set(values['staff'])<=known:raise QueryBlocked('A requested staff name was not found in the cleaned data.')
    if date.fromisoformat(values['start_date'])>date.fromisoformat(values['end_date']):raise QueryBlocked('Revenue dates are reversed.')
    plan.financial=RevenueView(**values)
    plan.diagnostic=plan.revenue=plan.trend=plan.customer=None
    plan.booking_id='';plan.queries=[]
    plan.context_start=values['start_date'];plan.context_end=values['end_date']
    plan.context_entity=', '.join(values['staff']) or 'Salon'
    plan.scope=f"{plan.context_entity}: {values['category']} revenue, {values['start_date']} to {values['end_date']}"


def revenue_view_result(db,plan):
    """Total, item composition and details all derive from one filtered set."""
    if 'financial_lines' not in db.schema:raise QueryBlocked('Revenue is unavailable in the enabled cleaned dataset.')
    r=plan.financial
    selected=[v for v in db.frames['financial_lines'].to_dict('records')
        if r.start_date<=v['posted_date']<=r.end_date and (not r.staff or v['staff_name'] in r.staff)
        and (r.category=='all' or v['item_type']==r.category)]
    totals=[];items=[]
    for name in r.staff or ['Whole business']:
        lines=[v for v in selected if not r.staff or v['staff_name']==name]
        total=sum((Decimal(str(v['net_revenue'])) for v in lines),Decimal(0))
        totals.append(dict(staff_name=name,period_start=r.start_date,period_end=r.end_date,category=r.category,
            net_revenue_aud=float(total),transaction_count=len({v['transaction_id'] for v in lines}),line_count=len(lines)))
        groups={}
        for v in lines:
            key=(v['item_id'],v['item_name']);groups[key]=groups.get(key,Decimal(0))+Decimal(str(v['net_revenue']))
        composition=[dict(staff_name=name,item_id=k[0],item_name=k[1],net_revenue_aud=float(value)) for k,value in sorted(groups.items())]
        if sum((Decimal(str(v['net_revenue_aud'])) for v in composition),Decimal(0))!=total:
            raise QueryBlocked('The item breakdown does not reconcile to the selected revenue total.')
        items.extend(composition)
    results=[packet(db.intake,'approved_revenue_view',totals,plan.scope)]
    if r.breakdown=='item' or r.chart=='pie':results.append(packet(db.intake,'approved_revenue_items',items,plan.scope))
    notes=[]
    if any(i['table'] in ['transactions','transaction_items'] for i in db.intake.issues):
        notes.append('Revenue covers validated financial records only; unresolved financial data issues may affect completeness.')
    if r.end_date>db.intake.asof.date().isoformat():
        notes.append('Actual revenue is available only through the reporting date '+db.intake.asof.date().isoformat()+'.')
    if r.details:
        fields=['transaction_id','transaction_item_id','staff_name','posted_date','item_name','net_revenue']
        details=[{k:v[k] for k in fields} for v in sorted(selected,key=lambda v:(v['posted_date'],v['transaction_id']))]
        results.append(packet(db.intake,'approved_revenue_transactions',details[:500],plan.scope))
        if len(details)>500:notes.append('Transaction detail shows the first 500 lines; totals and composition include all matching lines.')
    chart=dict(kind='none',result=0,x='',y='',series='')
    if r.chart!='none':
        item_chart=r.breakdown=='item' or r.chart=='pie'
        rows=items if item_chart else totals
        kind=r.chart
        if kind=='pie' and (not rows or any(v['net_revenue_aud']<0 for v in rows) or any(v['net_revenue_aud']<=0 for v in totals)):
            kind='bar';notes.append('A pie chart cannot represent negative or zero-total net revenue. A bar chart preserves the signed values, including refunds.')
        if rows:chart=dict(kind=kind,result=1 if item_chart else 0,x='item_name' if item_chart else 'staff_name',y='net_revenue_aud',series='staff_name' if item_chart and len(totals)>1 else '')
    label={'all':'total net','product':'product','service':'service','part':'part'}[r.category]
    claims=[dict(text=f"{v['staff_name']}: AUD {v['net_revenue_aud']:,.2f} {label} revenue from {r.start_date} to {r.end_date}, across {v['transaction_count']} distinct posted transactions ({v['line_count']} item lines).",
        evidence=[dict(result=0,row=i,column='net_revenue_aud',format='money')],context_ids=[]) for i,v in enumerate(totals)]
    return dict(plan=plan.model_dump(),answer=dict(claims=claims,additional_queries=[],investigation='',recommendation='',measurement='',missing_information=' '.join(notes),chart=chart,context_review=[]),
        results=results,contexts=[],status='answered',issues=[],execution_notes=['Totals, composition and transaction details share identical cleaned-data filters and reconcile.'])
