from copy import deepcopy
from unittest.mock import patch
import pytest
from analytics.runtime import load_snapshot, CombinedContextStore
from analyst_engine import Database
from analyst_ai import Plan, CustomerRequest, Diagnostic, investigate, preserve_name_correction
from analyst_ui import result_chart, display_frame
from business_context import ContextStore


def plan(**kwargs):
    return Plan(intent='lookup',scope='test',missing_information='',queries=[],context_entity='',context_start='',context_end='',draft=None,**kwargs)


def test_customer_followup_uses_first_visit_before_booking():
    db=Database.from_intake(load_snapshot())
    try:
        p=plan(customer=CustomerRequest(identifier='Synthetic Client 004',as_of_date='2026-06-22'))
        with patch('analyst_ai.structured',return_value=p) as ai:
            result=investigate(None,'test',db,'Is that client new or existing?',[],ContextStore())
        assert ai.call_count==1
        row=result['results'][0]['rows'][0]
        assert row['customer_id']=='C0004' and row['customer_status']=='existing'
        assert row['first_completed_visit_date']=='2025-12-01'
        assert 'existing on 2026-06-22' in result['answer']['claims'][0]['text']
    finally:db.close()


def test_name_correction_keeps_other_comparison_participant():
    p=plan(diagnostic=Diagnostic(staff=['Matthew'],start_date='2026-09-07',end_date='2026-09-13'))
    old=plan(diagnostic=Diagnostic(staff=['Jacintha','Sarah'],start_date='2026-09-07',end_date='2026-09-13'))
    preserve_name_correction(p,'sorry I meant Matthew, not Jacintha',[{'plan':old.model_dump()}],[{'staff_name':'Matthew'},{'staff_name':'Sarah'}])
    assert p.diagnostic.staff==['Matthew','Sarah']


def test_plural_chart_followup_retains_staff_and_change_needs_difference():
    from analyst_ai import TrendRequest,preserve_followup_scope
    from analyst_engine import bind_claim_values,QueryBlocked
    p=plan(trend=TrendRequest(staff=[],start_date='2026-05-01',end_date='2026-08-31',grain='month',category='service'))
    old=plan(diagnostic=Diagnostic(staff=['Sarah','Matthew'],start_date='2026-09-01',end_date='2026-09-15'))
    preserve_followup_scope(p,'Show their monthly service revenue as a chart',[{'plan':old.model_dump()}],[{'staff_name':'Sarah'},{'staff_name':'Matthew'}])
    assert p.trend.staff==['Sarah','Matthew']
    with pytest.raises(QueryBlocked,match='calculated difference'):
        bind_claim_values([{'rows':[{'net_revenue_aud':100}]}],dict(text='Revenue rose by [[0]].',evidence=[dict(result=0,row=0,column='net_revenue_aud',format='money')]),['',''])


def test_chart_survives_withheld_narration_and_numeric_table_rounds():
    item={'status':'facts_only','answer':None,'results':[{'table':'approved_revenue_trend','rows':[
        {'period_start':'2026-05-01','staff_name':'Sarah','net_revenue_aud':420},
        {'period_start':'2026-06-01','staff_name':'Sarah','net_revenue_aud':500}]}]}
    assert result_chart(item)['kind']=='line'
    assert display_frame([{'name':'Sarah','utilisation':82.352941}]).iloc[0]['utilisation']=='82.35'


def test_leave_counts_and_capacity_labels():
    from analyst_ui import numerical_prose
    from analyst_ai import Answer,validate_commercial_labels
    from analyst_engine import QueryBlocked
    assert numerical_prose('Sarah had two days of leave; Matthew had one day.')=='Sarah had 2 days of leave; Matthew had 1 day.'
    answer=Answer(claims=[dict(text='Matthew worked [[0]] bookable hours.',evidence=[],context_ids=[])],investigation='',recommendation='',measurement='',missing_information='',chart=dict(kind='none',result=0,x='',y=''))
    with pytest.raises(QueryBlocked,match='available capacity'):validate_commercial_labels(None,plan(),answer,[],[])


def test_source_context_correction_retraction_and_history_preserve_raw():
    intake=load_snapshot();original=deepcopy(intake.contexts)
    backing=ContextStore();store=CombinedContextStore(intake,backing)
    note=next(r for r in store.all_rows() if r['id']=='CTX1')
    draft={k:note[k] for k in ['entity','start_date','end_date','event_type','explanation']}
    draft.update(entity='Matthew',explanation='Corrected leave note')
    changed=deepcopy(store.correct(note,draft,'Owner','Wrong staff member'))
    assert intake.contexts==original
    assert not any(r['id']=='CTX1' for r in store.search('Sarah'))
    assert any(r['explanation']=='Corrected leave note' for r in store.search('Matthew'))
    event=store.history(changed['id'])[0]
    assert event['before_record']['entity']=='Sarah' and event['after_record']['entity']=='Matthew'
    assert event['actor']=='Owner' and event['after_record']['change_reason']=='Wrong staff member'
    store.correct(changed,draft,'Owner','Withdrawn',retract=True)
    assert not any(r['id']==changed['id'] for r in store.search())
    with pytest.raises(ValueError,match='changed'):store.correct(changed,draft,'Owner','Stale edit')


def test_context_update_form_requires_approval_and_saves_reason():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_string('''
import streamlit as st
from analyst_ui import context_form
from business_context import ContextStore
rows=st.session_state.setdefault('rows',[dict(id='note',entity='Sarah',start_date='2026-09-08',end_date='2026-09-09',event_type='leave',explanation='Old note',source_name='Owner',recorded_at='2026-09-20T00:00:00Z',status='active')])
context_form(ContextStore(session_rows=rows,events=st.session_state.setdefault('events',[])))
''',default_timeout=30).run()
    next(x for x in app.text_input if x.label=='Changed by').set_value('Sammy')
    next(x for x in app.text_input if x.label=='Reason for change').set_value('Wrong name')
    next(x for x in app.selectbox if x.label=='Corrected applies to').set_value('Matthew')
    next(x for x in app.button if x.label=='Confirm context change').click().run()
    assert app.session_state['rows'][0]['entity']=='Sarah'
    next(x for x in app.checkbox if x.label.startswith('I approve')).check()
    next(x for x in app.button if x.label=='Confirm context change').click().run()
    assert not app.exception
    assert app.session_state['rows'][0]['entity']=='Matthew'
    assert app.session_state['events'][0]['actor']=='Sammy'


def test_revised_approval_changes_clean_data_and_future_alias_only():
    from analytics.persistence import raw_payload, checkpoint, build_snapshot
    from piece1_validation.clarification import questions,proposed,decision
    from piece1_validation.adapter import Intake
    from piece1_validation.correction_revision import prepare_revision,current_rules
    raw=raw_payload();untouched=deepcopy(raw)
    q=next(q for q in questions(Intake(raw)) if q['kind']=='staff')
    old=decision(proposed(q,'S01','Sarah'),'Original owner');old['rule_id']='original'
    cp=checkpoint({'p1_decisions':[old]})
    revised,changes=prepare_revision(raw,cp,old,'S03','Sammy','I checked the appointment; it was Sam')
    assert revised['decisions'][0]==old and len(revised['decisions'])==2
    assert revised['decisions'][1]['supersedes_rule_id']=='original'
    assert revised['decisions'][1]['previous_value']=='S01'
    assert changes and raw==untouched
    clean=build_snapshot(raw,revised)
    assert next(r for r in clean['tables']['bookings'] if r['booking_id']=='B00004')['staff_id']=='S03'
    assert current_rules(raw,revised['decisions'])[0]['value']=='S03'
    incoming=deepcopy(raw);incoming['tables']['bookings']=incoming['tables']['bookings'].replace('B00004,','NEXT-UPLOAD,')
    assert next(r for r in build_snapshot(incoming,revised)['tables']['bookings'] if r['booking_id']=='NEXT-UPLOAD')['staff_id']=='S03'
