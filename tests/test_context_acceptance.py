from copy import deepcopy
from unittest.mock import patch
import pytest
from analytics.runtime import load_snapshot, CombinedContextStore
from analyst_engine import Database, bind_claim_values, QueryBlocked
from analyst_ai import Plan, RevenueRequest, Answer, Review, investigate
from business_context import ContextStore


def test_only_cited_context_dates_are_bound_without_allowing_typed_amounts():
    contexts=[dict(id='leave',start_date='2026-09-08',end_date='2026-09-09')]
    claim=dict(text='The owner reported leave from 8 to 9 September 2026.',evidence=[],context_ids=['leave'])
    assert bind_claim_values([],claim,['2026-09-07','2026-09-13'],contexts)==(
        'The owner reported leave from 2026-09-08 to 2026-09-09.')
    for changed in [dict(context_ids=[]),dict(context_ids=['invented']),
                    dict(text='The owner reported leave on 10 September 2026.'),
                    dict(text='The owner reported AUD 250 lost revenue.')]:
        with pytest.raises(QueryBlocked):
            bind_claim_values([],{**claim,**changed},['2026-09-07','2026-09-13'],contexts)
    assert bind_claim_values([],{**claim,'text':'Owner-reported leave: [[context0_start]] to [[context0_end]].'},['',''],contexts).endswith('2026-09-08 to 2026-09-09.')


def test_relevant_context_reaches_writer_and_reviewer_without_changing_revenue():
    intake=load_snapshot()
    original=deepcopy(intake.tables)
    store=CombinedContextStore(intake,ContextStore(session_rows=[
        dict(id='unrelated',entity='Matthew',start_date='2026-09-08',end_date='2026-09-09',status='active',explanation='Unrelated'),
        dict(id='retracted',entity='Sarah',start_date='2026-09-08',end_date='2026-09-09',status='retracted',explanation='Withdrawn'),
        dict(id='wrong-period',entity='Sarah',start_date='2026-08-01',end_date='2026-08-02',status='active',explanation='Old')]))
    plan=Plan(intent='lookup',scope='Sarah revenue and context',missing_information='',queries=[],
        revenue=RevenueRequest(staff=['Sarah'],start_date='2026-09-07',end_date='2026-09-13'),
        context_entity='',context_start='',context_end='',draft=None)
    answer=Answer(claims=[
        dict(text='Sarah recorded [[0]] net revenue.',evidence=[dict(result=0,row=0,column='total_net_revenue_aud',format='money')],context_ids=[]),
        dict(text='The owner reported leave from 8 to 9 September 2026; this does not establish the cause of a revenue change.',evidence=[],context_ids=['CTX1'])],
        investigation='',recommendation='',measurement='',missing_information='',chart=dict(kind='none',result=0,x='',y=''))
    db=Database.from_intake(intake)
    try:
        with patch('analyst_ai.structured',side_effect=[plan,answer,Review(approved=True,issues=[])]) as calls:
            result=investigate(None,'gpt-4.1-mini',db,'Revenue and relevant notes?',[],store)
        assert result['status']=='answered'
        assert 'AUD 1,410.00' in result['answer']['claims'][0]['text']
        assert '2026-09-08 to 2026-09-09' in result['answer']['claims'][1]['text']
        for call in calls.call_args_list[1:]:
            assert {r['id'] for r in call.args[-1]['contexts']}=={'CTX1','CTX2'}
        assert intake.tables==original
    finally:
        db.close()


def test_unconfirmed_validation_context_is_excluded():
    note=dict(context_id='UNCONFIRMED',entity='Sarah',period_start='2026-09-07',period_end='2026-09-13',
              explanation='Unreviewed claim',source_name='Test',recorded_at='2026-09-20T00:00:00Z',confirmed=False)
    intake=load_snapshot({'p1_context':[note]})
    assert 'UNCONFIRMED' not in {r['id'] for r in intake.contexts}


def test_context_form_requires_owner_confirmation_before_saving():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_string('''
import streamlit as st
from analyst_ui import context_form
from business_context import ContextStore
rows=st.session_state.setdefault('test_rows',[])
st.session_state.setdefault('context_draft',dict(entity='Sarah',start_date='2026-09-08',end_date='2026-09-09',event_type='leave',explanation='Controlled test note'))
context_form(ContextStore(session_rows=rows))
''',default_timeout=30).run()
    next(x for x in app.text_input if x.label=='Reported by').set_value('Acceptance test owner')
    next(x for x in app.button if x.label=='Keep context for this session').click().run()
    assert not app.exception and app.session_state['test_rows']==[]
    app.checkbox[0].check()
    next(x for x in app.button if x.label=='Keep context for this session').click().run()
    assert not app.exception
    assert len(app.session_state['test_rows'])==1
    assert app.session_state['test_rows'][0]['source_name']=='Acceptance test owner'
