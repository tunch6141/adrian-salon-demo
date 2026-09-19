from unittest.mock import patch
import pytest
from analyst_ai import Plan, Answer, Review, QueryRepair, investigate
from analyst_engine import Database
from analytics.runtime import load_snapshot
from business_context import ContextStore

@pytest.fixture
def db():
    database=Database.from_intake(load_snapshot())
    yield database
    database.close()

GOOD="SELECT SUM(net_revenue) AS revenue FROM financial_lines WHERE staff_id='S01' AND posted_date BETWEEN '2026-09-07' AND '2026-09-13'"
BAD='SELECT * FROM financial_lines JOIN staff_daily ON 1=1'

def plan(queries):
    return Plan(intent='analysis',scope='Sarah 7–13 September',missing_information='',queries=queries,context_entity='Sarah',context_start='2026-09-07',context_end='2026-09-13',draft=None)

def test_rejected_join_repaired_with_verified_revenue(db):
    answer=Answer(claims=[dict(text='Sarah recorded [[0]] net revenue.',evidence=[dict(result=0,row=0,column='revenue',format='money')],context_ids=[])],investigation='',recommendation='',measurement='',missing_information='',chart=dict(kind='none',result=0,x='',y=''))
    with patch('analyst_ai.structured',side_effect=[plan([BAD]),QueryRepair(query=GOOD),answer,Review(approved=True,issues=[])]) as call:
        result=investigate(None,'mock',db,'How did Sarah perform from 7 to 13 September 2026?',[],ContextStore())
    assert result['status']=='answered'
    assert '1,410.00' in result['answer']['claims'][0]['text']
    assert result['results'][0]['sql']==GOOD
    assert call.call_args_list[1].args[4]['rejected_query']==BAD

def test_failed_repair_preserves_prior_evidence_and_stops(db):
    with patch('analyst_ai.structured',side_effect=[plan([GOOD,BAD]),QueryRepair(query='DELETE FROM financial_lines')]) as call:
        result=investigate(None,'mock',db,'Sarah performance',[],ContextStore())
    assert call.call_count==2
    assert result['status']=='facts_only' and result['answer'] is None
    assert result['results'][0]['rows'][0]['revenue']==1410
    assert db.query(GOOD)['rows'][0]['revenue']==1410

def test_repairs_have_a_shared_budget(db):
    with patch('analyst_ai.structured',side_effect=[plan([BAD,BAD,BAD]),QueryRepair(query=GOOD),QueryRepair(query=GOOD)]) as call:
        result=investigate(None,'mock',db,'Sarah performance',[],ContextStore())
    assert call.call_count==3 and len(result['results'])==2
    assert result['status']=='facts_only'
