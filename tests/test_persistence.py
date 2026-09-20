from copy import deepcopy
from pathlib import Path
import json
import uuid
from unittest.mock import patch
import pytest
from analytics.persistence import (raw_payload,checkpoint,build_snapshot,restore_snapshot,PipelineStore,
                                  load_active,save_review,import_raw)
from piece1_validation.adapter import Intake,digest
from piece1_validation.clarification import questions,proposed,decision
from piece1_validation.metrics import revenue
from analyst_engine import Database,QueryBlocked

SOURCE=Path(__file__).resolve().parents[1]/'piece1_validation/sample_raw'


def approved(raw,kind='staff',value='S01'):
    q=next(q for q in questions(Intake(raw)) if q['kind']==kind)
    text='Sarah S01' if kind=='staff' else 'AUD 35 excluding GST'
    d=decision(proposed(q,value,text),'Pipeline test owner')
    d['rule_id']=str(uuid.uuid4())
    return d


def record(raw,cp,version=None):
    return dict(raw=deepcopy(raw),raw_id=digest(raw),snapshot=build_snapshot(raw,cp),
                checkpoint=deepcopy(cp),version_id=version or str(uuid.uuid4()))


def test_raw_roundtrip_and_exact_revenue_from_saved_snapshot():
    raw=raw_payload(SOURCE); original=deepcopy(raw)
    cp=checkpoint({}); saved=record(raw,cp)
    with patch('analytics.persistence.Intake.__init__',side_effect=AssertionError('Must read saved clean data')):
        restored=restore_snapshot(json.loads(json.dumps(saved)))
    assert raw==original
    assert revenue(restored,'2026-09-07','2026-09-14','S01')['net_revenue']=='1410.00'
    db=Database.from_intake(restored)
    try:
        result=db.query("SELECT SUM(net_revenue) AS revenue FROM financial_lines WHERE staff_id='S01' AND posted_date BETWEEN '2026-09-07' AND '2026-09-13'")
        assert result['rows'][0]['revenue']==1410
        with pytest.raises(QueryBlocked):db.query('DELETE FROM financial_lines')
    finally:db.close()


def test_rule_reused_on_new_raw_and_linked_to_original_approval():
    raw=raw_payload(SOURCE);d=approved(raw)
    cp=checkpoint({'p1_decisions':[d]})
    incoming=deepcopy(raw)
    incoming['tables']['bookings']=incoming['tables']['bookings'].replace('B00004,','NEW-BOOKING,')
    # The same alias is valid even when source casing/spacing differs.
    variant=' '+d['raw_value'].swapcase()+' '
    incoming['tables']['bookings']=incoming['tables']['bookings'].replace(','+d['raw_value']+',',','+variant+',')
    result=restore_snapshot(record(incoming,cp))
    assert not [q for q in questions(result) if q['kind']=='staff']
    applications=[a for a in result.audit if a.get('approval',{} ) and a['approval'].get('rule_id')==d['rule_id']]
    assert applications and all(a['approval']['approved_at']==d['approved_at'] for a in applications)
    assert incoming!=raw and raw_payload(SOURCE)==raw
    newer=deepcopy(incoming)
    newer['tables']['bookings']=newer['tables']['bookings'].replace(','+variant+',',',Unknown new person,')
    assert any(q['kind']=='staff' for q in questions(restore_snapshot(record(newer,cp))))


def test_record_specific_cost_not_reused_after_source_changes():
    raw=raw_payload(SOURCE);d=approved(raw,'cost','35')
    i=Intake(raw)
    original=next(r['record'] for r in i.raw if r['table']=='inventory_items' and r['record']['item_id']==d['record_id'])
    d['source_row_hash']=digest(original)
    cp=checkpoint({'p1_decisions':[d]})
    assert not [q for q in questions(restore_snapshot(record(raw,cp))) if q['kind']=='cost']
    later=deepcopy(raw)
    later['tables']['inventory_items']=later['tables']['inventory_items'].replace(original['stock_as_of'],'2026-09-14T23:59:59+10:00')
    assert any(q['kind']=='cost' for q in questions(restore_snapshot(record(later,cp))))


def test_restart_uses_remote_approval_not_empty_session():
    raw=raw_payload(SOURCE);d=approved(raw);saved=record(raw,checkpoint({'p1_decisions':[d]}))
    store=PipelineStore('https://example.supabase.co','test')
    with patch('analytics.persistence.store_for',return_value=store),patch.object(store,'current',return_value=saved):
        state={};loaded=load_active(state,lambda k:'')
    assert state['p1_decisions']==[d] and loaded.version_id==saved['version_id']
    assert not any(q['kind']=='staff' for q in questions(loaded))


def test_failed_save_never_changes_active_checkpoint():
    raw=raw_payload(SOURCE);saved=record(raw,checkpoint({}));state={'pipeline_record':saved,
        'pipeline_version':saved['version_id'],'p1_pending':{'expected_version':saved['version_id']}}
    d=approved(raw);store=PipelineStore('https://example.supabase.co','test')
    with patch('analytics.persistence.store_for',return_value=store),patch.object(store,'publish',side_effect=ValueError('offline')):
        with pytest.raises(ValueError):save_review(state,lambda k:'',{'decisions':[d]},'Tester','correction',str(uuid.uuid4()))
    assert not state.get('p1_decisions') and state['pipeline_record']==saved


def test_new_import_reuses_checkpoint_without_owner_prompt_and_duplicate_is_noop():
    raw=raw_payload(SOURCE);d=approved(raw);saved=record(raw,checkpoint({'p1_decisions':[d]}))
    state={'pipeline_record':saved,'pipeline_version':saved['version_id']}
    store=PipelineStore('https://example.supabase.co','test')
    new=deepcopy(raw);new['tables']['bookings']+='\n'
    with patch('analytics.persistence.store_for',return_value=store),patch.object(store,'publish',return_value=record(new,saved['checkpoint'])) as publish:
        assert import_raw(state,lambda k:'',raw) is False
        publish.assert_not_called()
        assert import_raw(state,lambda k:'',new) is True
        assert publish.call_args.args[1]==saved['checkpoint']
        assert publish.call_args.args[4]=='automatic_import'


def test_configured_outage_never_falls_back_to_bundled_csv():
    store=PipelineStore('https://example.supabase.co','test')
    with patch('analytics.persistence.store_for',return_value=store),patch.object(store,'current',side_effect=ValueError('offline')),patch('analytics.persistence.load_snapshot') as local:
        with pytest.raises(ValueError):load_active({},lambda k:'')
        local.assert_not_called()


def test_raw_rejects_wrong_business_or_unknown_columns():
    raw=raw_payload(SOURCE)
    raw['tables']['businesses']=raw['tables']['businesses'].replace('B001','B002')
    with pytest.raises(ValueError):raw_payload(raw)
    raw=raw_payload(SOURCE);raw['tables']['staff']='staff_id,arbitrary\nS01,value\n'
    with pytest.raises(ValueError):raw_payload(raw)

def test_persistent_streamlit_review_survives_another_browser_session():
    from streamlit.testing.v1 import AppTest
    root=Path(__file__).resolve().parents[1]
    store=PipelineStore('https://example.supabase.co','test')
    saved=[record(raw_payload(SOURCE),checkpoint({}))]
    events=[]
    def publish(raw,cp,expected,actor,kind,event_id):
        assert expected==saved[0]['version_id']
        saved[0]=record(raw,cp)
        events.append(dict(event_id=event_id,approved_at='2026-09-20T00:00:00Z',actor=actor,
            kind=kind,version_id=saved[0]['version_id'],previous_version_id=expected,
            details={'changes':{'decisions':cp['decisions']},'unresolved_issue_count':2}))
        return deepcopy(saved[0])
    with patch('analytics.persistence.store_for',return_value=store),patch('piece1_validation.pipeline_ui.store_for',return_value=store),patch.object(store,'current',side_effect=lambda:deepcopy(saved[0])),patch.object(store,'publish',side_effect=publish),patch.object(store,'history',side_effect=lambda:deepcopy(events)):
        app=AppTest.from_file(str(root/'pages/1_Data_Validation.py'),default_timeout=60)
        app.secrets['DEMO_PASSWORD']='test';app.run()
        app.text_input(key='piece1_password').set_value('test').run()
        app.text_input(key='p1_owner').set_value('Pipeline test owner').run()
        app.selectbox(key='p1_choice:staff:B00004').set_value('S01').run()
        app.button(key='p1_review').click().run()
        assert not events  # A proposal cannot publish.
        app.button(key='p1_discard').click().run()
        assert not events  # Rejection cannot publish.
        app.button(key='p1_review').click().run()
        app.button(key='p1_confirm').click().run()
        assert not app.exception and len(events)==1
        assert saved[0]['checkpoint']['decisions'][0]['approved_by']=='Pipeline test owner'
        other=AppTest.from_file(str(root/'pages/1_Data_Validation.py'),default_timeout=60)
        other.secrets['DEMO_PASSWORD']='test';other.run()
        other.text_input(key='piece1_password').set_value('test').run()
        assert not other.exception
        assert len(other.session_state['p1_decisions'])==1
        assert 'Who is S Wong?' not in other.selectbox(key='p1_issue').options
        assert any('Saved in Supabase' in c.value for c in other.caption)


def test_analyst_receives_changed_cleaned_financial_evidence():
    from piece1_validation.amendments import sale_record
    from analyst_ai import Plan,Answer,Review,investigate
    from business_context import ContextStore
    raw=raw_payload(SOURCE)
    sale=sale_record('S01','2026-09-07','100','AUD excluding GST','service',
                     'Controlled test service','TEST-ONLY-100','Test owner','Missing sale AUD 100')
    intake=restore_snapshot(record(raw,checkpoint({'p1_sales':[sale]})))
    db=Database.from_intake(intake)
    plan=Plan(intent='lookup',scope='Sarah revenue',missing_information='',queries=[
        "SELECT SUM(net_revenue) AS revenue FROM financial_lines WHERE staff_id='S01' AND posted_date BETWEEN '2026-09-07' AND '2026-09-13'"],
        context_entity='Sarah',context_start='2026-09-07',context_end='2026-09-13',draft=None)
    answer=Answer(claims=[dict(text='Sarah recorded [[0]] net revenue.',evidence=[dict(result=0,row=0,column='revenue',format='money')],context_ids=[])],
        investigation='',recommendation='',measurement='',missing_information='',chart=dict(kind='none',result=0,x='',y=''))
    try:
        with patch('analyst_ai.structured',side_effect=[plan,answer,Review(approved=True,issues=[])]):
            result=investigate(object(),'gpt-4.1-mini',db,'What was Sarah revenue?',[],ContextStore())
        assert result['status']=='answered'
        assert '1,510.00' in result['answer']['claims'][0]['text']
        assert raw==raw_payload(SOURCE)
    finally:db.close()

def test_revenue_module_matches_known_service_retail_total_and_refunds():
    from analytics.diagnostics import revenue_diagnostic
    from analyst_ai import RevenueRequest,Plan,Answer,Review,investigate
    from business_context import ContextStore
    intake=restore_snapshot(record(raw_payload(SOURCE),checkpoint({})))
    db=Database.from_intake(intake)
    try:
        rows=revenue_diagnostic(db,['Sarah'],'2026-09-07','2026-09-13')[0]['rows']
        assert rows[0]['service_revenue_aud']==1380
        assert rows[0]['retail_revenue_aud']==30
        assert rows[0]['total_net_revenue_aud']==1410
        plan=Plan(intent='lookup',scope='Sarah revenue',missing_information='',queries=[],
            revenue=RevenueRequest(staff=['Sarah'],start_date='2026-09-07',end_date='2026-09-13'),
            context_entity='Sarah',context_start='2026-09-07',context_end='2026-09-13',draft=None)
        answer=Answer(claims=[dict(text='Sarah recorded [[0]] net revenue from 7 to 13 September 2026.',
            evidence=[dict(result=0,row=0,column='total_net_revenue_aud',format='money')],context_ids=[])],
            investigation='',recommendation='',measurement='',missing_information='',chart=dict(kind='none',result=0,x='',y=''))
        with patch('analyst_ai.structured',side_effect=[plan,answer,Review(approved=True,issues=[])]):
            result=investigate(object(),'gpt-4.1-mini',db,'Sarah revenue?',[],ContextStore())
        assert result['status']=='answered'
        assert 'AUD 1,410.00' in result['answer']['claims'][0]['text']
        assert result['results'][0]['table']=='approved_revenue_summary'
        with pytest.raises(QueryBlocked):db.query("SELECT SUM(net_revenue) FROM financial_lines WHERE item_type='retail'")
    finally:db.close()


def test_scope_dates_are_verified_but_unbound_money_still_rejected():
    from analyst_engine import bind_claim_values
    claim={'text':'Revenue was [[0]] from 7 to 13 September 2026.',
           'evidence':[{'result':0,'row':0,'column':'amount','format':'money'}]}
    values=[{'rows':[{'amount':1410}]}]
    assert bind_claim_values(values,claim,['2026-09-07','2026-09-13'])=='Revenue was AUD 1,410.00 from 2026-09-07 to 2026-09-13.'
    for text in ('Revenue was 1410.','Revenue was [[0]] on 8 September 2026.','Revenue was [[0]] in 2025.'):
        with pytest.raises(QueryBlocked):bind_claim_values(values,{**claim,'text':text},['2026-09-07','2026-09-13'])
