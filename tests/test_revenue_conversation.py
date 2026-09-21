from unittest.mock import patch
import pandas as pd
import pytest
from analyst_ai import Plan, Diagnostic, investigate
from analyst_engine import Database, validate_chart
from analyst_ui import build_chart
from analytics.runtime import load_snapshot
from analytics.revenue_conversation import RevenueView, prior_revenue_scope
from business_context import ContextStore


def plan(**kwargs):
    return Plan(intent='lookup',scope='',missing_information='',queries=[],context_entity='',context_start='',context_end='',draft=None,**kwargs)


@pytest.fixture
def db():
    value=Database.from_intake(load_snapshot())
    yield value
    value.close()


def ask(db,question,p,history):
    with patch('analyst_ai.structured',return_value=p) as ai:
        result=investigate(None,'test',db,question,history,ContextStore())
    assert ai.call_count==1
    assert result['status']=='answered'
    history.append(dict(question=question,plan=result['plan'],status=result['status']))
    return result


def test_total_pie_transactions_and_new_people_share_scope(db):
    history=[]
    first=ask(db,"Show Sam's product revenue from May to August",plan(financial=RevenueView(staff=['Sam'],start_date='2026-05-01',end_date='2026-08-31',category='product')),history)
    expected=db.query("SELECT SUM(net_revenue) AS revenue, COUNT(DISTINCT transaction_id) AS transactions FROM financial_lines WHERE staff_name='Sam' AND item_type='product' AND posted_date BETWEEN '2026-05-01' AND '2026-08-31'")['rows'][0]
    total=first['results'][0]['rows'][0]
    assert total['net_revenue_aud']==expected['revenue']==990
    assert total['transaction_count']==expected['transactions']==33
    second=ask(db,'What are the 33 product transactions? Show me a pie chart with revenue please',plan(financial=RevenueView(breakdown='item',chart='pie',details=True)),history)
    assert second['plan']['financial']['staff']==['Sam']
    assert sum(r['net_revenue_aud'] for r in second['results'][1]['rows'])==990
    details=second['results'][2]['rows']
    assert len({r['transaction_id'] for r in details})==33
    assert sum(r['net_revenue'] for r in details)==990
    assert {r['staff_name'] for r in details}=={'Sam'}
    validate_chart(second['results'],second['answer']['chart'])
    assert build_chart(pd.DataFrame(second['results'][1]['rows']),second['answer']['chart']).to_dict()['mark']['type']=='arc'
    # Even an erroneous default performance plan cannot reset this follow-up.
    third=ask(db,'what about Sarah and Matthew?',plan(diagnostic=Diagnostic(staff=['Sarah','Matthew'],start_date='2026-09-07',end_date='2026-09-13')),history)
    scope=third['plan']['financial']
    assert scope['staff']==['Sarah','Matthew'] and scope['category']=='product'
    assert (scope['start_date'],scope['end_date'])==('2026-05-01','2026-08-31')
    assert third['plan']['diagnostic'] is None
    chart=third['answer']['chart'];validate_chart(third['results'],chart)
    assert chart['kind']=='pie'
    assert build_chart(pd.DataFrame(third['results'][1]['rows']),chart).to_dict()['facet']['column']['field']=='staff_name'
    for row in third['results'][0]['rows']:
        assert sum(r['net_revenue_aud'] for r in third['results'][1]['rows'] if r['staff_name']==row['staff_name'])==row['net_revenue_aud']


def test_explicit_new_period_category_and_whole_business_replace_scope(db):
    history=[dict(status='answered',plan=plan(financial=RevenueView(staff=['Sam'],start_date='2026-05-01',end_date='2026-08-31',category='product')).model_dump())]
    result=ask(db,'Show whole business service revenue in September',plan(financial=RevenueView(staff=[],start_date='2026-09-01',end_date='2026-09-30',category='service',chart='none')),history)
    scope=result['plan']['financial']
    assert scope['staff']==[] and scope['category']=='service' and scope['start_date']=='2026-09-01'
    assert 'reporting date' in result['answer']['missing_information']


def test_legacy_sql_scope_and_unrelated_topic_boundary():
    sql="SELECT SUM(net_revenue) FROM financial_lines WHERE staff_name='Sam' AND item_type='product' AND posted_date >= '2026-05-01' AND posted_date < '2026-09-01'"
    history=[dict(status='answered',plan={'queries':[sql]})]
    scope=prior_revenue_scope(history)
    assert scope['staff']==['Sam'] and scope['end_date']=='2026-08-31'
    assert prior_revenue_scope(history+[dict(status='answered',plan={'booking_id':'B00004'})]) is None
    assert prior_revenue_scope([dict(plan={'queries':[sql+" AND customer_id='C0002'"]})]) is None


def test_refunds_and_zero_total_do_not_draw_misleading_pie(db):
    frame=db.frames['financial_lines']
    mask=(frame.staff_name=='Sam') & (frame.item_type=='product')
    frame.loc[mask,'net_revenue']=-30
    result=ask(db,'Product revenue by item as a pie',plan(financial=RevenueView(staff=['Sam'],start_date='2026-05-01',end_date='2026-08-31',category='product',chart='pie')),[])
    assert result['answer']['chart']['kind']=='bar'
    assert 'negative' in result['answer']['missing_information']
    validate_chart(result['results'],result['answer']['chart'])
