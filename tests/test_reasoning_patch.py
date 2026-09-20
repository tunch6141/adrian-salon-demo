from copy import deepcopy
from unittest.mock import patch
import pytest
from analytics.runtime import load_snapshot,CombinedContextStore
from analytics.diagnostics import booking_lookup,revenue_trend,staff_diagnostic,period_diagnostic,comparable_periods
from analyst_engine import Database,QueryBlocked,bind_claim_values
from analyst_ai import Plan,Diagnostic,Answer,Review,investigate
from business_context import ContextStore
from piece1_validation.clarification import questions,decision,proposed

@pytest.fixture(scope='module')
def clean():
    original=load_snapshot()
    q=next(q for q in questions(original) if q['kind']=='staff')
    return load_snapshot({'p1_decisions':[decision(proposed(q,'S01','Sarah'),'Test owner')]})

@pytest.fixture
def db(clean):
    value=Database.from_intake(deepcopy(clean))
    yield value
    value.close()

def test_booking_uses_corrected_record_and_unique_short_identifier(db):
    before=deepcopy(db.intake.tables)
    row=booking_lookup(db,'B0004')[0]['rows'][0]
    assert (row['booking_id'],row['staff_id'],row['staff_name'])==('B00004','S01','Sarah')
    assert row['requested_booking_id']=='B0004' and 'unique' in row['id_match']
    assert booking_lookup(db,'B00004')[0]['rows'][0]['id_match']=='exact'
    assert booking_lookup(db,'B999999')[0]['rows']==[]
    assert db.intake.tables==before
    assert db.query("SELECT * FROM booking_records WHERE booking_id='B00004'")['rows'][0]['staff_name']=='Sarah'
    with pytest.raises(QueryBlocked):db.query('DELETE FROM booking_records')

def test_short_identifier_never_guesses_between_multiple_records(db):
    import pandas as pd
    frame=db.frames['booking_records']
    row=frame[frame.booking_id=='B00004'].copy();row['booking_id']='B000004'
    db.frames['booking_records']=pd.concat([frame,row],ignore_index=True)
    with pytest.raises(QueryBlocked):booking_lookup(db,'B0004')
    assert booking_lookup(db,'B00004')[0]['rows'][0]['booking_id']=='B00004'

def test_single_day_and_staff_comparison(db):
    r=staff_diagnostic(db,['Sarah'],'2026-09-17','2026-09-17')[0]['rows'][0]
    assert r['service_revenue_aud']==420 and r['completed_appointments']==6
    results=staff_diagnostic(db,['Matthew','Sarah'],'2026-08-01','2026-08-31')
    assert [r['service_revenue_aud'] for r in results[0]['rows']]==[11880,12200]  # source staff order
    diff=next(r for r in results[-1]['rows'] if r['metric']=='service_revenue_aud')
    assert diff['difference_first_minus_second']==-320
    with pytest.raises(QueryBlocked):period_diagnostic(db,['Sarah'],'2026-09-17','2026-09-17','2026-08-10','2026-09-06',4)
    assert comparable_periods('2026-09-07','2026-09-13','2026-08-10','2026-09-06',4)
    assert comparable_periods('2026-08-01','2026-08-31','2026-06-01','2026-06-30',1)

def test_weekly_trend_covers_full_may_to_august(db):
    results=revenue_trend(db,['Sarah'],'2026-05-01','2026-08-31','week','service')
    rows=results[0]['rows']
    assert len(rows)==19 and rows[0]['period_start']=='2026-05-01' and rows[-1]['period_end']=='2026-08-31'
    assert rows[0]['bucket_start']=='2026-04-27' and rows[-1]['bucket_start']=='2026-08-31'
    assert rows[0]['partial_calendar_bucket'] and rows[-1]['partial_calendar_bucket']
    exact=db.query("SELECT SUM(net_revenue) AS revenue FROM financial_lines WHERE staff_name='Sarah' AND item_type='service' AND posted_date BETWEEN '2026-05-01' AND '2026-08-31'")['rows'][0]['revenue']
    assert results[1]['rows'][0]['net_revenue_aud']==exact==sum(r['net_revenue_aud'] for r in rows)
    assert all(r['coverage']=='complete' for r in rows)

def test_missing_capacity_does_not_block_financial_core(clean):
    intake=deepcopy(clean);intake.tables.pop('staff_availability',None)
    db=Database.from_intake(intake)
    try:
        r=staff_diagnostic(db,['Sarah'],'2026-09-17','2026-09-17')[0]['rows'][0]
        assert r['service_revenue_aud']==420 and r['bookable_hours'] is None and r['realised_utilisation_pct'] is None
    finally:db.close()

def test_exact_cited_literal_is_normalised_but_fabrication_is_blocked():
    results=[{'rows':[{'amount':12200,'booking':'B00004'}]}]
    refs=[dict(result=0,row=0,column='amount',format='money'),dict(result=0,row=0,column='booking')]
    claim=dict(text='Booking B00004: AUD 12,200.00.',evidence=refs)
    assert bind_claim_values(results,claim,['',''])=='Booking B00004: AUD 12,200.00.'
    for text in ['Revenue AUD 12,201.00.','Booking B00005.','Revenue AUD 24,400.00.']:
        with pytest.raises(QueryBlocked):bind_claim_values(results,{**claim,'text':text},['',''])

def test_context_only_lookup_runs_writer_and_review(db):
    p=Plan(intent='lookup',scope='Sarah notes',missing_information='',queries=[],context_entity='Sarah',context_start='2026-09-07',context_end='2026-09-13',draft=None)
    a=Answer(claims=[dict(text='The owner reported leave from [[context0_start]] to [[context0_end]].',evidence=[],context_ids=['CTX1'])],investigation='',recommendation='',measurement='',missing_information='',chart=dict(kind='none',result=0,x='',y=''))
    with patch('analyst_ai.structured',side_effect=[p,a,Review(approved=True,issues=[])]) as calls:
        result=investigate(None,'gpt-4.1-mini',db,'What context is recorded for Sarah?',[],CombinedContextStore(db.intake,ContextStore()))
    assert result['status']=='answered' and not result['results']
    assert '2026-09-08' in result['answer']['claims'][0]['text']
    assert calls.call_count==3

def test_invalid_optional_baseline_keeps_valid_current_answer(db):
    p=Plan(intent='analysis',scope='Sarah day',missing_information='',queries=[],context_entity='Sarah',context_start='2026-09-17',context_end='2026-09-17',draft=None,
        diagnostic=Diagnostic(staff=['Sarah'],start_date='2026-09-17',end_date='2026-09-17',comparison_start_date='2026-08-10',comparison_end_date='2026-09-06',comparison_divisor=4))
    a=Answer(claims=[dict(text='Sarah recorded [[0]] service revenue.',evidence=[dict(result=0,row=0,column='service_revenue_aud',format='money')],context_ids=[])],investigation='',recommendation='',measurement='',missing_information='',chart=dict(kind='none',result=0,x='',y=''))
    with patch('analyst_ai.structured',side_effect=[p,a,Review(approved=True,issues=[])]):
        result=investigate(None,'gpt-4.1-mini',db,'Sarah on September seventeenth?',[],ContextStore())
    assert result['status']=='answered' and result['execution_notes']
    assert all(r['table']!='approved_period_comparison' for r in result['results'])
