"""Owner-reviewed missing sales. No writing to original source files."""
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
from zoneinfo import ZoneInfo
import re,uuid,hashlib,json

def money_request(text):
    return bool(re.search(r'\b(revenue|sale|sales|cash|payment|refund|income)\b',text,re.I) and re.search(r'forgot|miss(?:ed|ing)?|unrecorded|not recorded|update|add|correct|record|paid|received',text,re.I))

def sale_record(staff,day,amount,tax_basis,item_type,description,reference,owner,source_text,record_id=None,recorded_at=None):
    if staff not in ['S01','S02','S03']:raise ValueError('Select a known staff member.')
    d=date.fromisoformat(str(day))
    if not date(2026,6,22)<=d<=date(2026,9,16):raise ValueError('This fixture accepts missing sales between 22 June and 16 September 2026, the last completed day.')
    try:a=Decimal(str(amount))
    except InvalidOperation:raise ValueError('Enter a monetary amount.')
    if not a.is_finite() or a<=0 or a>Decimal('1000000') or a.as_tuple().exponent < -2:raise ValueError('Use a positive amount with at most two decimal places.')
    if tax_basis not in ['AUD excluding GST','AUD including 10% GST']:raise ValueError('Confirm whether the amount includes GST.')
    if item_type not in ['service','product','part']:raise ValueError('Choose the revenue category.')
    if not all(str(x).strip() for x in [description,reference,owner,source_text]):raise ValueError('Supply description, unique sale reference, approver and original explanation.')
    identifier=str(uuid.UUID(record_id)) if record_id else str(uuid.uuid4())
    net=(a/Decimal('1.1') if tax_basis=='AUD including 10% GST' else a).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    recorded_at=recorded_at or datetime.now(timezone.utc).isoformat();stamp=datetime.fromisoformat(recorded_at)
    if stamp.tzinfo is None:raise ValueError('Approval timestamp requires a timezone.')
    return {'id':identifier,'staff_id':staff,'sale_date':str(d),'entered_amount':format(a,'f'),'tax_basis':tax_basis,'net_amount_ex_gst':format(net,'f'),'item_type':item_type,'description':str(description).strip(),'source_reference':str(reference).strip(),'approved_by':str(owner).strip(),'recorded_at':recorded_at,'source_text':str(source_text),'source_type':'owner_confirmed_missing_sale'}

def validate_sales(rows):
    if not isinstance(rows,list) or len(rows)>100:raise ValueError('Invalid manual-sales collection.')
    safe=[];seen={};refs=set()
    for r in rows:
        if not isinstance(r,dict):raise ValueError('Malformed sale.')
        fields=['id','staff_id','sale_date','entered_amount','tax_basis','item_type','description','source_reference','approved_by','source_text','recorded_at']
        if not all(isinstance(r.get(f),str) for f in fields):raise ValueError('Incomplete manual-sale record.')
        s=sale_record(r['staff_id'],r['sale_date'],r['entered_amount'],r['tax_basis'],r['item_type'],r['description'],r['source_reference'],r['approved_by'],r['source_text'],r['id'],r['recorded_at'])
        if s['id'] in seen:
            if seen[s['id']]!=s:raise ValueError('Conflicting versions of the same sale ID.')
            continue
        ref=s['source_reference'].casefold()
        if ref in refs:raise ValueError('That sale reference has already been recorded. Do not add it twice.')
        refs.add(ref);seen[s['id']]=s;safe.append(s)
    return safe

def apply_sales(intake,rows):
    rows=validate_sales(rows)
    existing={r['transaction_id'] for r in intake.tables['transactions']}
    applied=getattr(intake,'_applied_sales',{})
    for s in rows:
        tid='MANUAL-'+s['id'];lid=tid+'-LINE';iid=tid+'-ITEM'
        if tid in existing:
            if applied.get(tid)!=s:raise ValueError('Existing sale ID has different or unverified contents. Reconcile it before applying an amendment.')
            continue
        posted=datetime.combine(date.fromisoformat(s['sale_date']),datetime.min.time(),ZoneInfo('Australia/Melbourne')).isoformat()
        intake.tables['items'].append({'business_id':'B001','item_id':iid,'sku':None,'item_name':s['description'],'item_type':s['item_type'],'default_duration_minutes':None,'list_price_ex_gst':s['net_amount_ex_gst'],'unit_cost':None,'active':True})
        intake.tables['transactions'].append({'business_id':'B001','transaction_id':tid,'booking_id':None,'customer_id':None,'posted_at':posted,'status':'Posted','transaction_type':'Sale','source_type':s['source_type'],'source_reference':s['source_reference'],'date_precision':'day'})
        intake.tables['transaction_items'].append({'business_id':'B001','transaction_item_id':lid,'transaction_id':tid,'item_id':iid,'staff_id':s['staff_id'],'quantity':'1','gross_amount_ex_gst':s['net_amount_ex_gst'],'discount_ex_gst':'0','refund_ex_gst':'0','net_amount_ex_gst':s['net_amount_ex_gst'],'direct_cost':None,'original_transaction_item_id':None})
        intake.audit.append({'table':'transactions','source_row':None,'field':'transaction_id','original':None,'clean':tid,'action':'owner_confirmed_missing_sale','reason':s['source_text'],'approval':s})
        intake.lineage.append({'table':'transactions','record_id':tid,'source_file':'owner-confirmed amendment','source_row':None,'raw_sha256':hashlib.sha256(json.dumps(s,sort_keys=True).encode()).hexdigest()})
        existing.add(tid)
        applied[tid]=s
    intake._applied_sales=applied
    if rows:
        base=getattr(intake,'_pre_sales_batch',intake.batch_id);intake._pre_sales_batch=base
        intake.batch_id=hashlib.sha256((base+json.dumps(rows,sort_keys=True)).encode()).hexdigest()
    intake.health=intake.table_health()
    return intake
