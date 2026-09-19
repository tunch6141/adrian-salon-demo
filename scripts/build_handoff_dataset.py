"""Deterministic, fictional data for the locked 18 September handoff. No network calls."""
from pathlib import Path
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal
from collections import defaultdict
import csv, json, hashlib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/handoff_2026_09_18'
ZONE = ZoneInfo('Australia/Melbourne')
ASOF = '2026-09-17T18:00:00+10:00'

def stamp(day, hour=9):
    return datetime.combine(date.fromisoformat(str(day)), datetime.min.time(), ZONE).replace(hour=hour).isoformat()

def build(destination=OUT):
    tables = defaultdict(list)
    for p in sorted((ROOT/'piece1_validation/sample_raw').glob('*.csv')):
        tables[p.stem] = list(csv.DictReader(p.open(encoding='utf-8-sig')))
    def add(table, **row):
        tables[table].append({'business_id':'B001', **row})
        return tables[table][-1]
    def profile(key, value, status='handoff_rule'):
        old=next((r for r in tables['customer_profile'] if r['setting']==key),None)
        if old:old.update(value=str(value),status=status)
        else:add('customer_profile',setting=key,value=str(value),status=status)
    profile('inventory_lookback_days',90)
    profile('inventory_low_stock_days',30)
    profile('inventory_target_days',60)
    profile('inventory_reorder_rules','coverage_and_known_lead_time')
    profile('quote_followup_days',3)
    profile('adaptive_min_visits',3,'fixture_policy')
    profile('coverage_start','2025-06-02','fixture_metadata')
    profile('dataset_version','handoff_2026_09_18','fixture_metadata')
    # Retain stable source IDs and the original three deliberately unresolved issues.
    # Add 55 historical weeks, before the original fixture, with customer movement.
    n=0
    for week in range(55):
        monday=date(2025,6,2)+timedelta(weeks=week)
        for staff in ('S01','S02','S03'):
            for day in range(5):
                d=monday+timedelta(days=day); hours=6 if day==4 else 8
                add('staff_availability',availability_id=f'HAV-{week}-{staff}-{day}',staff_id=staff,work_date=str(d),shift_start=stamp(d),shift_end=stamp(d,9+hours),rostered_minutes=hours*60,nonbookable_minutes=0,bookable_minutes=hours*60)
                # Deliberately varied service mixes, no overlapping staff appointments.
                for slot in range(2):
                    n+=1; bid=f'HB{n:05}';tid=f'HT{n:05}'; lid=f'HL{n:05}'
                    item='SV02' if (week+day+slot+int(staff[-1]))%3==0 else 'SV01'
                    duration=120 if item=='SV02' else 60; price=180 if item=='SV02' else 70
                    start=datetime.fromisoformat(stamp(d,9+slot*3)); end=start+timedelta(minutes=duration)
                    created=start-timedelta(days=10 if slot==0 else 2)
                    # C0001 loses frequency, C0002 grows. Other customers have repeated histories.
                    cid='C0001' if slot==0 and week<25 else ('C0002' if slot==0 and week>=35 else f'C{3+(n%160):04}')
                    add('bookings',booking_id=bid,customer_id=cid,staff_id=staff,appointment_start=start.isoformat(),appointment_end=end.isoformat(),booking_created_at=created.isoformat(),status='Completed',expected_value_ex_gst=price,booking_source='online' if slot else 'phone')
                    add('booking_services',booking_service_id='BS'+bid,booking_id=bid,service_id=item,staff_id=staff,duration_minutes=duration)
                    for typ,when,status in [('created',created,'Booked'),('completed',end,'Completed')]:
                        add('booking_history',event_id=bid+'-'+typ,booking_id=bid,event_type=typ,event_at=when.isoformat(),status_after=status,start_after=start.isoformat(),end_after=end.isoformat(),staff_id_after=staff,expected_value_ex_gst_after=price)
                    add('transactions',transaction_id=tid,booking_id=bid,customer_id=cid,posted_at=end.isoformat(),status='Posted',transaction_type='Sale')
                    add('transaction_items',transaction_item_id=lid,transaction_id=tid,item_id=item,staff_id=staff,quantity=1,gross_amount_ex_gst=price,discount_ex_gst=0,refund_ex_gst=0,net_amount_ex_gst=price,direct_cost=30 if item=='SV02' else 5,original_transaction_item_id='')
    # Source uses explicit service variants. Components without prices are descriptive only.
    for iid,name,family,duration,price,cost in [('SV01','Haircut','Cut',60,70,5),('SV02','Colour package','Colour',120,180,30),('SV03','Long hair colour package','Colour',150,220,40),('SV04','Treatment add-on','Treatment',30,45,8),('SV05','Cut and treatment bundle','Cut',90,100,13)]:
        add('services',service_id=iid,service_name=name,service_family=family,default_duration_minutes=duration,list_price_ex_gst=price,direct_cost=cost,default_return_days=42 if family=='Cut' else 56)
        if not any(r['item_id']==iid for r in tables['items']):
            add('items',item_id=iid,sku=iid,item_name=name,item_type='service',default_duration_minutes=duration,list_price_ex_gst=price,unit_cost=cost,active=True)
    for parent,child,value in [('SV02','Colour',''),('SV02','Cut',''),('SV05','SV01',65),('SV05','SV04',35)]:
        add('service_components',component_id=parent+'-'+child,service_id=parent,component_name=child,component_price_ex_gst=value)
    for sid,service in [('S01','SV02'),('S02','SV01'),('S03','SV03')]:
        add('staff_skills',skill_id=sid+service,staff_id=sid,service_id=service,qualified=True)
    for c in tables['customers']:
        c['default_return_days']='60'
    # Explicit/service/business/unknown return cases are source-configured, not fabricated outcomes.
    tables['customers'][177]['owner_next_visit_date']='2026-10-01'
    tables['customers'][176]['default_return_days']=''
    tables['customers'][179]['default_return_days']=''
    add('vehicles',vehicle_id='V001',customer_id='C0178',rego='SYN001',make='Synthetic',model='Test vehicle',next_service_date='2026-10-01',next_service_mileage=120000,recorded_odometer=113000,industry_example='automotive_extension_only')
    # Package and attachment transactions outside the frozen acceptance week.
    for j in range(24):
        d=date(2026,7,6)+timedelta(days=(j//3)*7)
        sid=f'S0{1+j%3}'; bid=f'PKB{j:03}';tid=f'PKT{j:03}'
        # Existing Monday hours end at 17:00, so use a separately recorded Saturday roster.
        d+=timedelta(days=5)
        start=datetime.fromisoformat(stamp(d,9)); end=start+timedelta(minutes=180)
        add('staff_availability',availability_id=f'PKAV{j}',staff_id=sid,work_date=str(d),shift_start=start.isoformat(),shift_end=end.isoformat(),rostered_minutes=180,nonbookable_minutes=0,bookable_minutes=180)
        add('bookings',booking_id=bid,customer_id=f'C{100+j:04}',staff_id=sid,appointment_start=start.isoformat(),appointment_end=end.isoformat(),booking_created_at=(start-timedelta(days=12)).isoformat(),status='Completed',expected_value_ex_gst=265,booking_source='phone')
        add('transactions',transaction_id=tid,booking_id=bid,customer_id=f'C{100+j:04}',posted_at=end.isoformat(),status='Posted',transaction_type='Sale')
        for typ,when,status in [('created',start-timedelta(days=12),'Booked'),('completed',end,'Completed')]:
            add('booking_history',event_id=bid+typ,booking_id=bid,event_type=typ,event_at=when.isoformat(),status_after=status,start_after=start.isoformat(),end_after=end.isoformat(),staff_id_after=sid,expected_value_ex_gst_after=265)
        services=[('SV03',150,220,40),('SV04',30,45,8)] if j%4 else [('SV05',90,100,13)]
        for item,duration,price,cost in services:
            add('booking_services',booking_service_id=bid+item,booking_id=bid,service_id=item,staff_id=sid,duration_minutes=duration)
            discount=5 if j==5 else 0; realised=price-10 if j==6 else price
            add('transaction_items',transaction_item_id=tid+item,transaction_id=tid,item_id=item,staff_id=sid,quantity=1,gross_amount_ex_gst=realised,discount_ex_gst=discount,refund_ex_gst=0,net_amount_ex_gst=realised-discount,direct_cost=cost,original_transaction_item_id='')
        # Match booked interval to actual service durations, including package-only appointments.
        minutes=sum(r[1] for r in services); end=start+timedelta(minutes=minutes)
        b=tables['bookings'][-1];b['appointment_end']=end.isoformat();b['expected_value_ex_gst']=sum(r[2] for r in services)
        tables['transactions'][-1]['posted_at']=end.isoformat()
        for e in tables['booking_history'][-2:]:
            e['end_after']=end.isoformat();e['expected_value_ex_gst_after']=b['expected_value_ex_gst']
            if e['event_type']=='completed':e['event_at']=end.isoformat()
    # Same SKU from multiple suppliers, freight allocation and quantity-price differences.
    for sid,name,lead,terms,moq in [('SUP1','Synthetic Local Supply',5,30,10),('SUP2','Synthetic Wholesale',14,14,40)]:
        add('suppliers',supplier_id=sid,supplier_name=name,normal_lead_days=lead,payment_terms_days=terms,minimum_order_quantity=moq,currency='AUD',unit_of_measure='bottle')
    for i,(d,supplier,qty,cost,freight) in enumerate([('2026-06-15','SUP1',100,10,30),('2026-07-15','SUP2',100,9,60),('2026-08-15','SUP1',20,12,24),('2026-09-10','SUP2',100,10,50)]):
        rid=f'PR{i+1}'; lead=5 if supplier=='SUP1' else 14
        add('purchase_orders',order_id='PO'+rid,supplier_id=supplier,ordered_at=stamp(date.fromisoformat(d)-timedelta(days=lead)),expected_at=stamp(d),status='Received')
        add('purchase_receipts',receipt_id=rid,order_id='PO'+rid,supplier_id=supplier,received_at=stamp(d,8),freight_ex_gst=freight,duty_ex_gst=0,other_charges_ex_gst=0,currency='AUD')
        for item,q,unit in [('P05',qty,cost),('P06',qty,5)]:
            batch=rid+item; value=q*unit; total=qty*(cost+5)
            landed=Decimal(str(unit))+Decimal(str(freight))*Decimal(str(value))/Decimal(str(total))/q
            add('purchase_receipt_items',receipt_item_id=batch,receipt_id=rid,item_id=item,quantity=q,purchase_unit_cost=unit,direct_freight_ex_gst=0,direct_duty_ex_gst=0,direct_other_ex_gst=0,unit_of_measure='bottle')
            add('inventory_batches',batch_id=batch,receipt_item_id=batch,item_id=item,supplier_id=supplier,received_at=stamp(d,8),received_quantity=q,landed_unit_cost=str(landed))
    for item,name,qty,cost,suppressed in [('P05','Batch tracked shampoo',0,10,False),('P06','Batch tracked conditioner',0,5,False),('P07','Irregular specialist stock',40,25,True),('P08','No movement sample',15,8,False)]:
        add('items',item_id=item,sku=item,item_name=name,item_type='product',default_duration_minutes=0,list_price_ex_gst=30,unit_cost=cost,active=True)
        add('inventory_items',item_id=item,quantity_on_hand=qty,unit_cost=cost,supplier_lead_days=14,quantity_on_order=0,stock_as_of=ASOF,anomaly_suppressed=suppressed,movement_reliability='owner_flagged_irregular' if item=='P07' else 'unassessed')
    def movement(item,when,kind,qty,link='',batch='',reason=''):
        return add('inventory_movements',movement_id=f'EXTM{len(tables["inventory_movements"]):05}',item_id=item,occurred_at=when,movement_type=kind,quantity_delta=qty,unit_cost=10 if item=='P05' else 5,transaction_item_id=link,batch_id=batch,reason=reason)
    for b in tables['inventory_batches']:movement(b['item_id'],b['received_at'],'purchase_received',b['received_quantity'],batch=b['batch_id'])
    movement('P07',stamp('2026-06-01'),'opening_balance',42)
    movement('P07',stamp('2026-08-01'),'service_usage',-2)
    movement('P08',stamp('2026-06-01'),'opening_balance',15)
    # Exact, explicit, FIFO and fallback costing are deliberately separate cases.
    for j,(day,qty,batch,explicit) in enumerate([('2026-06-20',20,'PR1P05',''),('2026-07-20',90,'',''),('2026-08-20',2,'',13),('2026-09-11',10,'PR4P05','')]):
        tid=f'BATCHT{j}';lid=f'BATCHL{j}'
        add('transactions',transaction_id=tid,booking_id='',customer_id='C0170',posted_at=stamp(day),status='Posted',transaction_type='Sale')
        add('transaction_items',transaction_item_id=lid,transaction_id=tid,item_id='P05',staff_id='S02',quantity=qty,gross_amount_ex_gst=qty*30,discount_ex_gst=0,refund_ex_gst=0,net_amount_ex_gst=qty*30,direct_cost=qty*explicit if explicit else '',original_transaction_item_id='',batch_id=batch)
        movement('P05',stamp(day),'sale',-qty,lid,batch)
    # A later return reverses the original FIFO allocation, with its physical disposition.
    add('transactions',transaction_id='RET1',booking_id='',customer_id='C0170',posted_at=stamp('2026-08-22'),status='Posted',transaction_type='Refund')
    add('transaction_items',transaction_item_id='RETL1',transaction_id='RET1',item_id='P05',staff_id='S02',quantity=2,gross_amount_ex_gst=0,discount_ex_gst=0,refund_ex_gst=60,net_amount_ex_gst=-60,direct_cost='',original_transaction_item_id='BATCHL1',batch_id='')
    movement('P05',stamp('2026-08-22'),'customer_return',2,'RETL1',reason='unsellable return held then written off')
    movement('P05',stamp('2026-08-22',10),'damaged_writeoff',-2,'RETL1',reason='returned stock damaged')
    movement('P06',stamp('2026-08-25'),'supplier_return',-5,reason='credit pending')
    movement('P06',stamp('2026-08-26'),'manual_adjustment',-1)
    for r in tables['inventory_items']:
        r.setdefault('anomaly_suppressed',False);r.setdefault('movement_reliability','unassessed')
        if r['item_id'] in ['P05','P06','P07','P08']:
            r['quantity_on_hand']=sum(Decimal(str(m['quantity_delta'])) for m in tables['inventory_movements'] if m['item_id']==r['item_id'])
    # CRM history includes comparable followed and not-followed quotes and versioned prices.
    for j in range(36):
        qid=f'Q{j:03}'; issued=date(2026,7,1)+timedelta(days=j*2)
        status=['Won','Lost','Open','Expired'][j%4]
        add('enquiries',enquiry_id='EN'+qid,customer_id=f'C{1+j:04}',received_at=stamp(issued,8),source='phone',service_id='SV02')
        add('quotes',quote_id=qid,enquiry_id='EN'+qid,customer_id=f'C{1+j:04}',staff_id=f'S0{1+j%3}',service_id='SV02',issued_at=stamp(issued,10),status=status,value_ex_gst=180+(j%3)*10,direct_cost=30,expires_on=str(issued+timedelta(days=45)),source_followup_date=str(issued+timedelta(days=5)) if j%5==0 else '',owner_followup_date='',snoozed_until='2026-09-22' if j==34 else '',no_more_followup=j==30,lost_reason='timing unsuitable' if status=='Lost' and j%2 else '',linked_transaction_id='T00001' if j==0 else '',closed_at=stamp(issued+timedelta(days=7)) if status in ['Won','Lost','Expired'] else '')
        add('quote_versions',quote_version_id=qid+'-1',quote_id=qid,version=1,created_at=stamp(issued,10),amount_ex_gst=200)
        add('quote_versions',quote_version_id=qid+'-2',quote_id=qid,version=2,created_at=stamp(issued+timedelta(days=1),10),amount_ex_gst=180+(j%3)*10)
        if j%3:
            for attempt in range(1,1+j%3):
                add('quote_followups',quote_followup_id=qid+f'-F{attempt}',quote_id=qid,contacted_at=stamp(issued+timedelta(days=attempt*3)),channel='phone',summary='Synthetic quote review',outcome='no answer' if attempt==1 else 'discussed',next_action_date='',attempt=attempt,staff_id=f'S0{1+j%3}')
    # Accounting fixtures are a separate optional invoice ledger, never added to sale revenue.
    for cid,delay in [('C0001',0),('C0002',15),('C0003',3)]:
        for j in range(6):
            issued=date(2026,1,2)+timedelta(days=30*j);due=issued+timedelta(days=14);iid=f'INV-{cid}-{j}'
            add('invoices',invoice_id=iid,customer_id=cid,issued_on=str(issued),due_on=str(due),invoice_amount=1000,currency='AUD',amount_basis='including_GST',credit_amount=0)
            add('payments',payment_id='PAY'+iid,invoice_id=iid,paid_on=str(due+timedelta(days=delay)),amount=1000)
    for cid,amount,due,paid in [('C0001',8400,'2026-08-16',1000),('C0002',2000,'2026-09-05',0),('C0003',1200,'2026-09-30',200)]:
        iid='OPEN-'+cid
        add('invoices',invoice_id=iid,customer_id=cid,issued_on='2026-08-01',due_on=due,invoice_amount=amount,currency='AUD',amount_basis='including_GST',credit_amount=0)
        if paid:add('payments',payment_id='PART'+cid,invoice_id=iid,paid_on='2026-09-01',amount=paid)
    # Source-recorded actions with more than one checkpoint; these are fictional history.
    for i,status in enumerate(['Monitoring','Snoozed','Dismissed','New']):
        add('insights',insight_id=f'INS{i}',fingerprint=['stock:P06:excess','inventory:P07:irregular','pricing:SV01:test','capacity:next_week'][i],module=['inventory','inventory','pricing','staff_capacity'][i],status=status,presented_at=stamp('2026-08-01'),snoozed_until='2026-10-01' if status=='Snoozed' else '',summary='Synthetic commercial review',estimated_impact_ex_gst=500,impact_is_estimate=True)
    add('actions',action_id='ACT1',insight_id='INS0',customer_id='',action_type='purchasing_review',started_on='2026-08-01',objective='Reduce excess stock',approved_by='Adrian',baseline_json='{"excess_stock_value":8200}',status='Monitoring')
    add('actions',action_id='ACT2',insight_id='INS2',customer_id='C0002',action_type='pricing_experiment',started_on='2026-08-01',objective='Test preferred pricing',approved_by='Adrian',baseline_json='{"discount_pct":5,"price":70,"volume":20}',status='Completed')
    for j,value in enumerate([7100,5900]):
        add('review_checkpoints',checkpoint_id=f'CHK{j}',action_id='ACT1',reviewed_on=['2026-08-15','2026-09-01'][j],snapshot_json=json.dumps({'excess_stock_value':value}),conclusion='Observed reduction after purchasing review; causation not established',owner_decision='Continue',next_review_date=['2026-09-01','2026-10-01'][j])
    add('business_context',context_id='CTX-STRATEGY',staff_id='',customer_id='C0002',period_start='2026-08-01',period_end='2026-10-01',event_type='commercial_hypothesis',explanation='Owner believes this customer has strategic potential and approved a five percent pricing trial. This is a human hypothesis.',source_type='owner_reported',source_name='Adrian',recorded_at=stamp('2026-08-01'),confirmed=True,causality_verified=False)
    add('price_history',price_event_id='PRICE1',service_id='SV01',effective_on='2026-08-01',old_price=70,new_price=66.5,event_type='pricing_experiment',action_id='ACT2')
    # A latest-known cost fallback has no batch or explicit transaction cost.
    add('transactions',transaction_id='FALLBACKT',booking_id='',customer_id='C0170',posted_at=stamp('2026-08-28'),status='Posted',transaction_type='Sale')
    add('transaction_items',transaction_item_id='FALLBACKL',transaction_id='FALLBACKT',item_id='P07',staff_id='S02',quantity=1,gross_amount_ex_gst=30,discount_ex_gst=0,refund_ex_gst=0,net_amount_ex_gst=30,direct_cost='',original_transaction_item_id='',batch_id='')
    movement('P07',stamp('2026-08-28'),'sale',-1,'FALLBACKL')
    next(r for r in tables['inventory_items'] if r['item_id']=='P07')['quantity_on_hand']=39
    # Supplier credit is a separate recorded fact, never assumed from a physical return.
    add('supplier_credits',supplier_credit_id='SC1',supplier_id='SUP1',item_id='P06',credited_on='2026-09-01',quantity=5,amount_ex_gst=25,reason='accepted returned stock')
    add('business_context',context_id='CTX-COLLECTION',staff_id='',customer_id='C0001',period_start='2026-09-17',period_end='2026-09-25',event_type='collection_promise',explanation='Customer promised to pay the remaining invoice balance on 25 September. Owner-reported promise, not a cash forecast.',source_type='owner_reported',source_name='Adrian',recorded_at=stamp('2026-09-17'),confirmed=True,causality_verified=False)
    add('actions',action_id='ACT-COLLECT',insight_id='INS4',customer_id='C0001',action_type='collection_followup',started_on='2026-09-17',objective='Review promised invoice payment',approved_by='Adrian',baseline_json='{"outstanding_balance":7400}',status='Monitoring')
    add('insights',insight_id='INS4',fingerprint='receivables:C0001:late',module='receivables',status='Monitoring',presented_at=stamp('2026-09-17'),snoozed_until='',summary='Payment later than customer history',estimated_impact_ex_gst='',impact_is_estimate=False)
    add('review_checkpoints',checkpoint_id='CHK-COLLECT',action_id='ACT-COLLECT',reviewed_on='',snapshot_json='{}',conclusion='',owner_decision='Review on promised date',next_review_date='2026-09-25')
    # No-history and one-visit customers exercise graceful due-date fallback.
    for cid in ['C0183','C0184']:
        add('customers',customer_id=cid,source_customer_id='SRC'+cid,customer_name='Synthetic Fallback '+cid,mobile='',email=cid.lower()+'@example.invalid',contact_permission='yes',owner_next_visit_date='',owner_next_visit_value_ex_gst='',default_return_days='')
    add('services',service_id='SV06',service_name='Consultation',service_family='Consultation',default_duration_minutes=30,list_price_ex_gst=35,direct_cost=0,default_return_days='')
    add('items',item_id='SV06',sku='SV06',item_name='Consultation',item_type='service',default_duration_minutes=30,list_price_ex_gst=35,unit_cost=0,active=True)
    start=stamp('2026-07-04');end=datetime.fromisoformat(start)+timedelta(minutes=30);created=stamp('2026-06-25')
    add('staff_availability',availability_id='FALLAV',staff_id='S03',work_date='2026-07-04',shift_start=start,shift_end=end.isoformat(),rostered_minutes=30,nonbookable_minutes=0,bookable_minutes=30)
    add('bookings',booking_id='FALLB',customer_id='C0183',staff_id='S03',appointment_start=start,appointment_end=end.isoformat(),booking_created_at=created,status='Completed',expected_value_ex_gst=35,booking_source='phone')
    add('booking_services',booking_service_id='FALLBS',booking_id='FALLB',service_id='SV06',staff_id='S03',duration_minutes=30)
    for typ,when,status in [('created',created,'Booked'),('completed',end.isoformat(),'Completed')]:
        add('booking_history',event_id='FALLB'+typ,booking_id='FALLB',event_type=typ,event_at=when,status_after=status,start_after=start,end_after=end.isoformat(),staff_id_after='S03',expected_value_ex_gst_after=35)
    add('transactions',transaction_id='FALLT',booking_id='FALLB',customer_id='C0183',posted_at=end.isoformat(),status='Posted',transaction_type='Sale')
    add('transaction_items',transaction_item_id='FALLL',transaction_id='FALLT',item_id='SV06',staff_id='S03',quantity=1,gross_amount_ex_gst=35,discount_ex_gst=0,refund_ex_gst=0,net_amount_ex_gst=35,direct_cost=0,original_transaction_item_id='')
    for reduction in [5,10]:
        for spare in [0,20]:
            add('pricing_scenarios',scenario_id=f'PRICE-{reduction}-{spare}',service_id='SV01',baseline_price=70,baseline_volume=20,proposed_price=70*(1-reduction/100),unit_cost=5,spare_bookable_hours=spare,hours_per_service=1,description='Synthetic feasibility input, not an approved change')
    # Explicit source history boundary supports first-visit attribution in the fictional dataset.
    first={}
    for b in tables['bookings']:
        if b['status']=='Completed':
            day=b['appointment_start'][:10]
            first[b['customer_id']]=min(first.get(b['customer_id'],day),day)
    for c in tables['customers']:c['first_completed_visit_date']=first.get(c['customer_id'],'')

    # Capability availability is derived at runtime; fixture entitlements are explicit.
    for module in ['services','suppliers','pricing','quotes','receivables','insights']:
        add('capabilities',module=module,entitled=True,data_health='Available')
    raw=destination/'raw';raw.mkdir(parents=True,exist_ok=True)
    dictionary=[]
    for name,rows in sorted(tables.items()):
        fields=list(dict.fromkeys(k for row in rows for k in row))
        with (raw/(name+'.csv')).open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
        for field in fields:dictionary.append({'table':name,'field':field,'nullable':any(r.get(field) in ('',None) for r in rows)})
    (destination/'field_dictionary.json').write_text(json.dumps(dictionary,indent=2)+'\n')
    manifest={'specification':'2026-09-18','synthetic':True,'as_of':ASOF,'history_start':'2025-06-02','tables':{k:len(v) for k,v in sorted(tables.items())},'frozen_acceptance':{'period':['2026-09-07','2026-09-14'],'staff_id':'S01','service_revenue':1380,'retail_revenue':30,'completed_hours':18,'bookable_hours':22},'scenarios':{
        'data_quality':['known alias','ambiguous S Wong','missing P04 cost','conflicting customer contact','name-only non-merge','exact duplicate','mixed dates/case'],
        'staff':['approved leave already deducted','different service mix','skills','service handoff across staff','new and existing customer returns'],
        'services':['exact variants','unpriced components','priced package','service-service attachment','service-product attachment','explicit discount','price variance'],
        'inventory':['fast movement','slow/no movement','low stock','excess stock','owner-suppressed irregular movement','resellable return','unsellable return and writeoff','supplier return','unexplained adjustment'],
        'suppliers':['same SKU two suppliers','volume price differences','purchase-value freight allocation','exact batch','split FIFO sale','explicit source cost','multiple batch costs'],
        'quotes':['enquiries','versions','won lost open expired','source due date','three-day repeat default','snooze','no more follow-up','attempt histories','missing lost reason'],
        'customer':['12-month concentration','growing and declining accounts','explicit due date','adaptive cadence','service/business fallback','automotive date and mileage'],
        'actions':['stable fingerprints','monitoring snoozed dismissed new','owner baseline','multiple checkpoints','extension'],
        'receivables':['fully paid history','normally prompt now late','habitually late','partial payment','not yet due']},'limitations':['No live customer data','No external demand evidence','No forecast or production entitlement pricing','Existing legacy fixture preserved']}
    manifest['raw_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(raw.glob('*.csv'))}
    (destination/'test_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest

if __name__=='__main__':
    result=build();print(json.dumps(result['tables'],indent=2))
