from copy import deepcopy
from datetime import datetime,date
from pathlib import Path
from tempfile import TemporaryDirectory
import csv,json
import pytest
from analytics.runtime import load_snapshot,CombinedContextStore
from analytics.calculations import staff_summary,quote_queue,receivables,stock_coverage,landed_receipts,customer_returns,pricing_simulation,bookings_at,future_workload,staff_return_outcomes
from analytics.costing import allocate_costs
from analytics.views import build_views
from analyst_engine import Database,QueryBlocked,service_diagnostic
from piece1_validation.amendments import sale_record
from piece1_validation.clarification import questions,decision,proposed,context_note
from business_context import ContextStore
from scripts.build_handoff_dataset import build

@pytest.fixture(scope='module')
def snapshot():return load_snapshot()

def test_reference_numbers(snapshot):
    s=staff_summary(snapshot,'2026-09-07','2026-09-14',['Sarah'])[0]
    assert (s['service_revenue_aud'],s['retail_revenue_aud'],s['completed_service_hours'],s['bookable_hours'])==(1380,30,18,22)
    assert s['realised_utilisation_pct']==pytest.approx(18/22*100)
    assert s['revenue_per_service_hour']==pytest.approx(1380/18)

def test_complete_history_and_schema(snapshot):
    assert len(snapshot.tables)==42
    assert len(snapshot.issues)==3
    assert min(b['appointment_start'][:10] for b in snapshot.tables['bookings'])=='2025-06-02'
    keys={b['booking_id'] for b in snapshot.tables['bookings']}
    assert {h['booking_id'] for h in snapshot.tables['booking_history']}==keys
    assert {b['booking_id'] for b in snapshot.tables['booking_services']}<=keys
    docs={r['transaction_id'] for r in snapshot.tables['transactions']}
    assert {r['transaction_id'] for r in snapshot.tables['transaction_items']}<=docs
    assert len(keys)==len(snapshot.tables['bookings'])

def test_reproducible_dataset():
    expected=json.loads((Path(__file__).resolve().parents[1]/'data/handoff_2026_09_18/test_manifest.json').read_text())
    with TemporaryDirectory() as temp:
        got=build(Path(temp))
        assert got==expected

def test_confirmed_state_is_shared(snapshot):
    q=next(q for q in questions(snapshot) if q['kind']=='staff')
    d=decision(proposed(q,'S01','Sarah'),'Adrian')
    state={'p1_decisions':[d]}
    new=load_snapshot(state)
    assert len(new.issues)==2 and new.revision!=snapshot.revision
    sale=sale_record('S01','2026-09-16','500','AUD excluding GST','service','Missing cash sale','CASH-NEW','Adrian','Sarah made AUD500 cash')
    new=load_snapshot({**state,'p1_sales':[sale]})
    before=staff_summary(snapshot,'2026-09-16','2026-09-17',['Sarah'])[0]
    after=staff_summary(new,'2026-09-16','2026-09-17',['Sarah'])[0]
    assert after['service_revenue_aud']==before['service_revenue_aud']+500
    assert after['revenue_per_service_hour'] is None
    assert staff_summary(new,'2026-09-07','2026-09-14',['Sarah'])[0]['total_revenue_aud']==1410

def test_context_does_not_rewrite_metrics(snapshot):
    note=context_note('Sam was sick.','Sam','2026-09-08','2026-09-09','Adrian')
    new=load_snapshot({'p1_context':[note]})
    assert staff_summary(new,'2026-09-07','2026-09-14')==staff_summary(snapshot,'2026-09-07','2026-09-14')
    store=CombinedContextStore(new,ContextStore())
    assert any(n['explanation']=='Sam was sick.' for n in store.search('Sam','2026-09-07','2026-09-13'))
    assert not any(n['explanation']=='Sam was sick.' for n in store.search('Sarah','2026-09-07','2026-09-13'))

def test_optional_data_and_entitlements(snapshot):
    new=deepcopy(snapshot)
    for table in ['inventory_items','inventory_movements','quotes','quote_followups','invoices','payments','purchase_receipts','purchase_receipt_items']:new.tables.pop(table,None)
    assert staff_summary(new,'2026-09-07','2026-09-14',['Sarah'])[0]['total_revenue_aud']==1410
    frames=build_views(new)
    assert 'financial_lines' in frames and 'receivables' not in frames
    new.tables.pop('staff_availability')
    assert staff_summary(new,'2026-09-07','2026-09-14',['Sarah'])[0]['realised_utilisation_pct'] is None
    for r in new.tables['capabilities']:
        if r['module']=='quotes':r['entitled']=False
    assert 'quotes' not in build_views(new)

def test_cost_allocation_and_freight(snapshot):
    receipts=landed_receipts(snapshot)
    assert sum(r['allocated_shared_charges'] for r in receipts if r['receipt_id']=='PR1')==pytest.approx(30)
    assert next(r for r in receipts if r['receipt_item_id']=='PR1P05')['landed_unit_cost']==pytest.approx(10.2)
    allocations=allocate_costs(snapshot)
    split=[a for a in allocations if a['transaction_item_id']=='BATCHL1']
    assert [(a['batch_id'],a['quantity']) for a in split]==[('PR1P05',80),('PR2P05',10)]
    assert {a['provenance'] for a in split}=={'FIFO_estimated'}
    assert next(a for a in allocations if a['transaction_item_id']=='BATCHL2')['provenance']=='explicit_cost'
    assert next(a for a in allocations if a['transaction_item_id']=='RETL1')['allocated_cost']==pytest.approx(-20.4)
    assert next(a for a in allocations if a['transaction_item_id']=='FALLBACKL')['provenance']=='latest_cost_fallback'

def test_inventory_reconciliation(snapshot):
    rows=stock_coverage(snapshot)
    assert all(r['ledger_difference']==0 for r in rows)
    assert next(r for r in rows if r['item_id']=='P08')['days_on_hand'] is None
    assert next(r for r in rows if r['item_id']=='P04')['excess_value_at_cost'] is None
    assert next(r for r in rows if r['item_id']=='P07')['anomaly_suppressed']==1

def test_quotes(snapshot):
    rows=quote_queue(snapshot);ids={r['quote_id'] for r in rows}
    assert 'Q030' not in ids and 'Q034' not in ids
    assert all(r['due_basis'] in ['source_date','default_after_issue','default_after_followup','followup_explicit','owner_override'] for r in rows)
    assert next(r for r in rows if r['quote_id']=='Q002')['due_date']=='2026-07-14'
    q=deepcopy(snapshot);row=next(r for r in q.tables['quotes'] if r['quote_id']=='Q002');row['owner_followup_date']='2026-09-20'
    assert next(r for r in quote_queue(q) if r['quote_id']=='Q002')['due_basis']=='owner_override'

def test_receivables(snapshot):
    rows=receivables(snapshot);by={r['customer_id']:r for r in rows}
    assert by['C0001']['outstanding_balance']==7400 and by['C0001']['normal_payment_delay_days']==0
    assert by['C0002']['days_beyond_normal']==0 and by['C0002']['normal_payment_delay_days']==15
    assert by['C0003']['days_overdue']==0 and by['C0003']['outstanding_balance']==1000

def test_return_hierarchy(snapshot):
    rows={r['customer_id']:r for r in customer_returns(snapshot)}
    assert rows['C0178']['due_basis']=='explicit_due_date'
    assert rows['C0001']['due_basis']=='adaptive_median_fixture_policy'
    assert rows['C0183']['due_basis']=='business_default'
    assert rows['C0184']['due_basis']=='unknown' and rows['C0184']['expected_due_date'] is None
    episodes=staff_return_outcomes(snapshot)
    assert any(r['eligible_episode']==0 and r['returned_to_business'] is None for r in episodes)

def test_future_snapshot_has_no_lookahead(snapshot):
    cutoff=datetime.fromisoformat('2026-09-10T18:00:00+10:00')
    rows=bookings_at(snapshot,cutoff,date(2026,9,21),date(2026,9,28))
    assert not any(r['booking_id']==next(h['booking_id'] for h in snapshot.tables['booking_history'] if h['event_type']=='rescheduled') for r in rows)
    rows=future_workload(snapshot)
    assert {r['horizon'] for r in rows}=={'next_week','next_7_days','next_14_days'}
    assert all(r['same_lead_time_four_week_average_hours']>=0 for r in rows)

def test_pricing_capacity_and_breakeven():
    r=pricing_simulation(100,10,90,50,0,1)
    assert r['gross_profit_break_even_volume']==12.5 and r['capacity_feasible'] is False
    assert pricing_simulation(100,10,40,50)['gross_profit_break_even_volume'] is None

def test_read_only_and_canonical_diagnostics(snapshot):
    db=Database.from_intake(snapshot)
    try:
        for sql in ['DELETE FROM financial_lines','SELECT 999 AS revenue','SELECT * FROM sqlite_master','SELECT * FROM financial_lines; DROP TABLE financial_lines']:
            with pytest.raises(Exception):db.query(sql)
        result=service_diagnostic(db,['Sarah'],'2026-09-07','2026-09-13')
        assert result[0]['rows'][0]['service_revenue_aud']==1380
        assert db.query("SELECT SUM(net_revenue) AS revenue FROM financial_lines WHERE staff_id='S01' AND posted_date BETWEEN '2026-09-07' AND '2026-09-13'")['rows'][0]['revenue']==1410
    finally:db.close()

def test_missing_financial_tables_are_not_zero(snapshot):
    new=deepcopy(snapshot);new.tables.pop('transactions')
    r=staff_summary(new,'2026-09-07','2026-09-14',['Sarah'])[0]
    assert r['total_revenue_aud'] is None and r['revenue_per_service_hour'] is None

def test_local_calendar_boundary_changes_period_not_value(snapshot):
    from zoneinfo import ZoneInfo
    from analytics.calculations import financial_lines
    new=deepcopy(snapshot)
    tx=next(r for r in new.tables['transactions'] if r['transaction_id']=='T00639')
    tx['posted_at']='2026-09-07T00:30:00+10:00'
    mel=next(r for r in financial_lines(new) if r['transaction_id']=='T00639')
    new.zone=ZoneInfo('Australia/Perth')
    perth=next(r for r in financial_lines(new) if r['transaction_id']=='T00639')
    assert mel['posted_date']=='2026-09-07' and perth['posted_date']=='2026-09-06'
    assert mel['net_revenue']==perth['net_revenue']
    assert datetime(2026,12,1,tzinfo=ZoneInfo('Australia/Melbourne')).utcoffset().total_seconds()==39600
    assert datetime(2026,12,1,tzinfo=ZoneInfo('Australia/Perth')).utcoffset().total_seconds()==28800

def test_customer_context_does_not_leak_to_unrelated_staff(snapshot):
    store=CombinedContextStore(snapshot,ContextStore())
    rows=store.search('Sarah','2026-08-01','2026-09-30')
    assert not any(r['id']=='CTX-STRATEGY' for r in rows)
    assert any(r['id']=='CTX-STRATEGY' for r in store.search('Customer C0002','2026-08-01','2026-09-30'))

def test_disabled_revenue_does_not_leak_through_other_views(snapshot):
    new=deepcopy(snapshot)
    for r in new.tables['capabilities']:
        if r['module']=='revenue':r['entitled']=False
    views=build_views(new)
    assert 'financial_lines' not in views
    assert 'customer_value' not in views
    assert views['staff_daily']['service_revenue_aud'].isna().all()
    assert staff_summary(new,'2026-09-07','2026-09-14',['Sarah'])[0]['service_revenue_aud'] is None

def test_incomplete_cost_cannot_be_summed_as_complete_margin(snapshot):
    new=deepcopy(snapshot)
    line=next(r for r in new.tables['transaction_items'] if r['transaction_item_id']=='L00760')
    line['direct_cost']=None
    item=next(r for r in new.tables['items'] if r['item_id']==line['item_id']);item['unit_cost']=None
    db=Database.from_intake(new)
    try:
        with pytest.raises(QueryBlocked,match='Cost coverage'):
            db.query("SELECT SUM(gross_profit) AS profit FROM financial_lines WHERE staff_id='S01'")
        assert db.query("SELECT SUM(net_revenue) AS revenue FROM financial_lines WHERE staff_id='S01'")['rows']
    finally:db.close()
