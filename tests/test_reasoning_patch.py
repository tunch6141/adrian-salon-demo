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
    claim=dict(text='The booking record for B0004 is completed.',evidence=[dict(result=0,row=0,column='status')])
    assert bind_claim_values(booking_lookup(db,'B0004'),claim,['',''])=='The booking record for B00004 is completed.'
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
    totals=results[1]['rows'][0]
    assert totals['minimum_complete_bucket_revenue']==1030
    assert totals['maximum_complete_bucket_revenue']==2780
    assert totals['last_minus_first_complete_bucket']==1735
    with pytest.raises(QueryBlocked):
        bind_claim_values(results,dict(text='Revenue ranged up to [[0]].',evidence=[dict(result=0,row=11,column='net_revenue_aud',format='money')]),['2026-05-01','2026-08-31'])

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

def test_real_model_date_spellings_bind_only_to_trusted_dates():
    for spelling in ['17th Sep 2026','17th September 2026','17 September','September 17, 2026']:
        claim=dict(text='Sarah generated [[0]] on '+spelling+'.',evidence=[dict(result=0,row=0,column='amount',format='money')])
        assert bind_claim_values([{'rows':[{'amount':420}]}],claim,['2026-09-17','2026-09-17'])=='Sarah generated AUD 420.00 on 2026-09-17.'
    claim=dict(text='In August 2026 the total was [[0]].',evidence=[dict(result=0,row=0,column='amount',format='money')])
    assert bind_claim_values([{'rows':[{'amount':12200}]}],claim,['2026-08-01','2026-08-31'])=='In August 2026 the total was AUD 12,200.00.'
    claim=dict(text='The appointment starts on 22nd June 2026.',evidence=[dict(result=0,row=0,column='appointment_start')])
    assert '2026-06-22' in bind_claim_values([{'rows':[{'appointment_start':'2026-06-22T15:00:00+10:00'}]}],claim,['',''])
    with pytest.raises(QueryBlocked):
        bind_claim_values([{'rows':[{'appointment_start':'2026-06-22T15:00:00+10:00'}]}],{**claim,'text':'The appointment starts on 23rd June 2026.'},['',''])

def test_capacity_cannot_be_labelled_booked_hours():
    result=[{'rows':[{'bookable_hours':8}]}]
    claim=dict(text='There were [[0]] booked hours.',evidence=[dict(result=0,row=0,column='bookable_hours')])
    with pytest.raises(QueryBlocked):bind_claim_values(result,claim,['',''])
    assert bind_claim_values(result,{**claim,'text':'There were [[0]] bookable hours.'},['',''])=='There were 8 bookable hours.'

def test_context_only_lookup_runs_writer_and_review(db):
    p=Plan(intent='lookup',scope='Sarah notes',missing_information='',queries=[],context_entity='Sarah',context_start='2026-09-07',context_end='2026-09-13',draft=None)
    a=Answer(claims=[dict(text='The owner reported leave from [[context0_start]] to [[context0_end]].',evidence=[],context_ids=['CTX1'])],investigation='',recommendation='',measurement='',missing_information='',chart=dict(kind='none',result=0,x='',y=''))
    with patch('analyst_ai.structured',side_effect=[p,a,Review(approved=True,issues=[])]) as calls:
        result=investigate(None,'gpt-4.1-mini',db,'What context is recorded for Sarah?',[],CombinedContextStore(db.intake,ContextStore()))
    assert result['status']=='answered' and not result['results']
    assert '2026-09-08' in result['answer']['claims'][0]['text']
    assert calls.call_count==3

def test_live_output_schema_cannot_invent_context_references():
    from unittest.mock import MagicMock
    from pydantic import ValidationError
    from analyst_ai import structured
    client=MagicMock()
    sample=dict(claims=[dict(text='Revenue [[0]].',evidence=[dict(result=0,row=0,column='amount')],context_ids=[])],investigation='',recommendation='',measurement='',missing_information='',chart=dict(kind='none',result=0,x='',y=''))
    for contexts in [[],[dict(id='CTX1')]]:
        structured(client,'gpt-4.1-mini',Answer,'test',{'contexts':contexts,'results':[{'rows':[{'amount':420}]}]})
        schema=client.responses.parse.call_args.kwargs['text_format']
        schema.model_validate(sample)
        invalid=deepcopy(sample);invalid['claims'][0]['context_ids']=['invented']
        with pytest.raises(ValidationError):schema.model_validate(invalid)
        for change in [dict(column='missing'),dict(result=1),dict(row=1)]:
            invalid=deepcopy(sample);invalid['claims'][0]['evidence'][0].update(change)
            with pytest.raises(ValidationError):schema.model_validate(invalid)
        for text in ['Revenue was about AUD 1,000.','On 17th Sep 2026.','Booking B0004.']:
            invalid=deepcopy(sample);invalid['claims'][0]['text']=text
            with pytest.raises(ValidationError):schema.model_validate(invalid)
        if contexts:
            valid=deepcopy(sample);valid['claims'][0]['context_ids']=['CTX1'];schema.model_validate(valid)

def test_invalid_optional_baseline_keeps_valid_current_answer(db):
    p=Plan(intent='analysis',scope='Sarah day',missing_information='',queries=[],context_entity='Sarah',context_start='2026-09-17',context_end='2026-09-17',draft=None,
        diagnostic=Diagnostic(staff=['Sarah'],start_date='2026-09-17',end_date='2026-09-17',comparison_start_date='2026-08-10',comparison_end_date='2026-09-06',comparison_divisor=4))
    a=Answer(claims=[dict(text='Sarah recorded [[0]] service revenue.',evidence=[dict(result=0,row=0,column='service_revenue_aud',format='money')],context_ids=[])],investigation='',recommendation='',measurement='',missing_information='',chart=dict(kind='none',result=0,x='',y=''))
    with patch('analyst_ai.structured',side_effect=[p,a,Review(approved=True,issues=[])]):
        result=investigate(None,'gpt-4.1-mini',db,'Sarah on September seventeenth?',[],ContextStore())
    assert result['status']=='answered' and result['execution_notes']
    assert all(r['table']!='approved_period_comparison' for r in result['results'])

def test_method_followup_uses_previous_scope_without_inventing_comparison(db):
    base=dict(scope='Sarah day',missing_information='',queries=[],context_entity='Sarah',context_start='2026-09-17',context_end='2026-09-17',draft=None)
    prior=Plan(intent='analysis',**base,diagnostic=Diagnostic(staff=['Sarah'],start_date='2026-09-17',end_date='2026-09-17'))
    p=Plan(intent='method',**base)
    a=Answer(claims=[dict(text='The prior calculation did not use a weekly comparison.',evidence=[dict(result=0,row=0,column='comparison_used')],context_ids=[])],investigation='',recommendation='',measurement='',missing_information='',chart=dict(kind='none',result=0,x='',y=''))
    history=[dict(question="How's Sarah on September seventeenth?",plan=prior.model_dump(),answer=None,status='facts_only')]
    with patch('analyst_ai.structured',side_effect=[p,a,Review(approved=True,issues=[])]):
        result=investigate(None,'gpt-4.1-mini',db,'Are you comparing his day with weekly revenue?',history,ContextStore())
    assert result['status']=='answered'
    scope=result['results'][0]['rows'][0]
    assert scope['current_days']==1 and scope['comparison_used'] is False
    assert result['results'][1]['rows'][0]['service_revenue_aud']==420
