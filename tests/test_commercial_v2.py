import json
from types import SimpleNamespace
import pytest
from analyst_engine import Database, QueryBlocked
from analytics.runtime import load_snapshot, CombinedContextStore
from business_context import ContextStore
from commercial.v2_models import *
from commercial.v2_data import query_data, read_sql
from commercial.v2_runtime import investigate, resolve_scope, optional_chart

@pytest.fixture
def db():
    value=Database.from_intake(load_snapshot(),rules_override='')
    yield value
    value.close()

def scope(**kwargs):
    return AnalysisScope(**(dict(objective='Measure revenue',subject='revenue',entities=['Sam'],start_date='2026-05-01',end_date='2026-08-31',comparison_start='',comparison_end='',category='product',measures=['net_revenue'],display='text')|kwargs))

def query(**kwargs):
    return QueryData(**(dict(dataset='financial_lines',purpose='Measure',dimensions=[],measures=[Measure(column='net_revenue',operation='sum',name='revenue')])|kwargs))

def final(**kwargs):
    return FinishAnswer(**(dict(answer='Sam recorded AUD 990.00 product revenue.',evidence=[],sources=['E1'],explanation='',next_step='',confidence='strongly supported',limitations='',context_used=[],chart=ChartRequest())|kwargs))

class NativeClient:
    def __init__(self,steps,reviews=None):
        self.steps=iter(steps);self.reviews=iter(reviews or [Review(blocking_errors=[],evidence_needed=[])])
        self.responses=self;self.inputs=[]
    def create(self,**kwargs):
        self.inputs.append(kwargs)
        name,arg=next(self.steps);call_id='call_'+str(len(self.inputs))
        payload=dict(type='function_call',name=name,arguments=arg.model_dump_json(),call_id=call_id)
        return SimpleNamespace(output=[SimpleNamespace(**payload,model_dump=lambda **_:payload)],usage=None)
    def parse(self,**kwargs):return SimpleNamespace(output_parsed=next(self.reviews),usage=None)

def test_scope_and_category_preserved(db):
    old=scope();new=resolve_scope(AnalysisScope(entities=['Sarah','Matthew']),old.model_dump(),'modify',{})
    assert new.category=='product' and new.start_date=='2026-05-01' and new.entities==['Sarah','Matthew']
    p=query_data(db,query(),old)[0]
    assert p['rows'][0]['revenue']==990
    assert read_sql(db,ReadSQL(purpose='Fallback',sql='SELECT SUM(net_revenue) AS revenue FROM financial_lines'),old)[0]['rows'][0]['revenue']==990
    with pytest.raises(QueryBlocked,match='conflicts'):
        query_data(db,query(filters=[DataFilter(column='item_type',operator='eq',values=['service'])]),old)
    with pytest.raises(QueryBlocked):query_data(db,query(dataset='service_sales'),old)

def test_group_ratios_and_missing_costs(db):
    request=query(dimensions=['staff_name'],measures=[Measure(column='net_revenue',operation='sum',name='revenue'),Measure(column='direct_cost',operation='sum',name='cost')],ratios=[Ratio(numerator='cost',denominator='revenue',scale=100,name='cost_pct')])
    p=query_data(db,request,scope(entities=['Sarah','Matthew'],category='all'))[0]
    for r in p['rows']:
        if r['cost'] is not None:assert r['cost_pct']==pytest.approx(r['cost']/r['revenue']*100)
    db.frames['financial_lines'].loc[:,'direct_cost']=float('nan')
    p=query_data(db,request,scope(entities=[],category='all'))[0]
    assert all(r['cost'] is None and r['cost_pct'] is None for r in p['rows'])

def test_periods_and_customer_grain(db):
    with pytest.raises(QueryBlocked,match='equal duration'):
        query_data(db,query(period='compare'),scope(start_date='2026-09-01',end_date='2026-09-17',comparison_start='2026-08-01',comparison_end='2026-08-31'))
    p=query_data(db,query(period='compare'),scope(start_date='2026-09-01',end_date='2026-09-17',comparison_start='2026-08-01',comparison_end='2026-08-17'))[0]
    assert 'revenue_change' in p['rows'][0]
    frame=db.frames['customer_visits']
    assert frame.booking_id.is_unique
    rows=frame[frame.booking_id.eq('B00004')]
    assert len(rows)>0 and all(rows.customer_type.eq('returning'))
    with pytest.raises(QueryBlocked,match='snapshot'):
        query_data(db,query(dataset='customer_returns',time_grain='month'),scope(entities=[]))

def test_chart_is_optional_and_pie_reconciles(db):
    packet=query_data(db,query(dimensions=['item_name']),scope())[0];packet['evidence_id']='E1'
    chart=ChartRequest(kind='pie',source='E1',x='item_name',y='revenue')
    assert optional_chart(final(chart=chart),[packet])[0]['kind']=='pie'
    assert optional_chart(final(chart=chart.model_copy(update={'y':'unknown'})),[packet])[0]['kind']=='none'

def test_native_review_can_request_more_data(db):
    framed=FrameQuestion(intent='lookup',relation='new',scope=scope(),hypotheses=[])
    client=NativeClient([('frame_question',framed),('query_data',query()),('finish_answer',final()),('query_data',query(dimensions=['item_name'])),('finish_answer',final(sources=['E1','E2']))],
        [Review(blocking_errors=['Verify product composition.'],evidence_needed=['Break down products.']),Review(blocking_errors=[],evidence_needed=[])])
    result=investigate(client,'test',db,'Show product revenue',[],CombinedContextStore(db.intake,ContextStore()))
    assert result['status']=='answered' and len(result['results'])==2 and len(result['audit_reviews'])==2
    assert all('tools' in r for r in client.inputs)
    assert all(c['entity'] in ['Sam','Salon'] for c in result['contexts'])

def test_fresh_synthesis_does_not_bypass_evidence_gate(db):
    from commercial.v2_runtime import tool_schema
    from unittest.mock import patch
    framed=FrameQuestion(intent='lookup',relation='new',scope=scope(),hypotheses=[])
    invalid=final(answer='Revenue was AUD 999999.')
    client=NativeClient([('frame_question',framed),('query_data',query()),('finish_answer',invalid),('finish_answer',final())])
    with patch('commercial.v2_runtime.MAX_ROUNDS',3):
        result=investigate(client,'test',db,'Show product revenue',[],ContextStore())
    assert result['status']=='answered'
    assert result['timing']['calls'][-2]['stage']=='fresh_synthesis'
    schema=tool_schema('finish_answer',result['results'])['parameters']
    assert schema['properties']['sources']['items']['enum']==['E1']
    assert schema['properties']['context_used']['maxItems']==0

def test_reported_context_numbers_are_quotes_not_calculated_facts():
    from commercial.v2_runtime import validate_report
    result=dict(evidence_id='E1',rows=[dict(revenue=990)])
    note=dict(id='NOTE',explanation='The owner reported two days of leave.',start_date='2026-08-10',end_date='2026-08-11')
    validate_report(final(answer='The owner reported 2 days of leave.',context_used=['NOTE']),[result],scope(),[note])
    with pytest.raises(QueryBlocked):
        validate_report(final(answer='The owner reported 3 days of leave.',context_used=['NOTE']),[result],scope(),[note])


def test_missing_citation_is_repaired_but_unretrieved_number_is_rejected():
    from commercial.v2_runtime import validate_report
    packets=[dict(evidence_id='E1',rows=[dict(revenue=100)]),
             dict(evidence_id='E2',rows=[dict(revenue=990)])]
    report=final(answer='Product revenue was AUD 990.',sources=['E1'])
    assert validate_report(report,packets,scope(),[])==[0,1]
    assert report.sources==['E1','E2']
    with pytest.raises(QueryBlocked):
        validate_report(final(answer='Product revenue was AUD 999999.',sources=['E1']),packets,scope(),[])


def test_grouped_comparison_preserves_independent_full_scope_totals(db):
    from commercial.v2_runtime import validate_report
    period=scope(entities=[],category='all',start_date='2026-09-01',end_date='2026-09-17',
                 comparison_start='2026-08-01',comparison_end='2026-08-17')
    packet=query_data(db,query(period='compare',dimensions=['item_type'],limit=1),period)[0]
    packet['evidence_id']='E1'
    totals=packet['metadata']['scoped_totals']
    assert totals['revenue_current']==pytest.approx(20345)
    assert totals['revenue_baseline']==pytest.approx(20655)
    assert totals['revenue_change']==pytest.approx(-310)
    validate_report(final(answer='Whole-business revenue fell AUD 310 to AUD 20,345.'),[packet],period,[])


def test_dated_queries_cannot_bypass_scope_and_horizons_cannot_overlap(db):
    with pytest.raises(QueryBlocked,match='dated history'):
        query_data(db,query(period='snapshot'),scope())
    next_week=scope(entities=[],category='all',start_date='2026-09-21',end_date='2026-09-27')
    result=query_data(db,query(dataset='future_workload',measures=[Measure(column='booked_hours',operation='sum',name='booked'),Measure(column='available_bookable_hours',operation='sum',name='available')]),next_week)[0]
    assert result['rows']==[dict(booked=43.,available=114.)]
    assert result['metadata']['source_rows']==3
    with pytest.raises(QueryBlocked,match='Identical aggregations'):
        query_data(db,query(dataset='customer_visits',measures=[Measure(column='booking_id',operation='count',name='visits'),Measure(column='booking_id',operation='count_distinct',name='customers')]),scope(entities=[],category='all'))

def test_empty_evidence_and_renamed_duplicate_counts_cannot_support_a_claim(db):
    from commercial.v2_runtime import validate_report
    with pytest.raises(QueryBlocked,match='No retrieved record'):
        validate_report(final(answer='Customers are leaving.',sources=[]),[],scope(),[])
    with pytest.raises(QueryBlocked,match='Identical aggregations'):
        query_data(db,query(dataset='booking_records',measures=[Measure(column='booking_id',operation='count',name='bookings'),Measure(column='booking_id',operation='count',name='cancellations')]),scope(entities=[],category='all'))

def test_named_calendar_windows_and_scope_repair(db):
    from commercial.v2_runtime import tool_schema
    framed=FrameQuestion(intent='lookup',relation='new',scope=scope(start_date='2026-01-01',end_date='2026-09-17'),hypotheses=[],current_window='current_month_elapsed',baseline_window='previous_month_matched_elapsed')
    client=NativeClient([('frame_question',framed),('query_data',query()),('finish_answer',final(answer='The requested product revenue was retrieved.'))])
    result=investigate(client,'test',db,'Check this month',[],ContextStore())
    s=result['analytical_state']['scope']
    assert s['start_date']=='2026-09-01' and s['comparison_end']=='2026-08-17'
    assert 'customer_returns' not in tool_schema('compare_periods',db=db)['parameters']['properties']['dataset']['enum']
