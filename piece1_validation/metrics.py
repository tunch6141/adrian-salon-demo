"""Evidence-bearing revenue from cleaned transaction lines; no joins to booking lines."""
from datetime import date,datetime
from decimal import Decimal as D,ROUND_HALF_UP
from zoneinfo import ZoneInfo

def amount(x):return format(x.quantize(D('.01'),rounding=ROUND_HALF_UP),'f')
def revenue(intake,start,end,staff_id=None):
    """Half-open local date interval [start,end). Partial coverage never labelled exact."""
    lo,hi=date.fromisoformat(start),date.fromisoformat(end)
    if lo>=hi:raise ValueError('End must be after start')
    tables=intake.tables
    modules=[r for r in tables.get('capabilities',[]) if r['module']=='revenue']
    if not modules or not modules[0]['entitled']:
        return {'status':'Not in plan' if modules else 'Permission unavailable','net_revenue':None}
    required=['transactions','transaction_items','items']
    if any(t not in tables for t in required):return {'status':'Missing data','net_revenue':None,'missing_tables':[t for t in required if t not in tables]}
    if staff_id is not None and staff_id not in {r['staff_id'] for r in tables.get('staff',[])}:raise ValueError('Unknown staff')
    settings={r['setting']:r['value'] for r in tables.get('customer_profile',[])}
    if settings.get('revenue_basis')!='ex_gst' or settings.get('refund_period')!='refund_posted_date':
        return {'status':'Unapproved metric configuration','net_revenue':None}
    if not tables.get('businesses') or not tables['businesses'][0].get('as_of'):
        return {'status':'Missing data','net_revenue':None,'missing_fields':['businesses.as_of']}
    tx={r['transaction_id']:r for r in tables['transactions']};items={r['item_id']:r for r in tables['items']}
    badlines={i['record_id'] for i in intake.issues if i['table']=='transaction_items' and i.get('record_id') and i['code'] in ['broken_reference','missing_financial_value','inconsistent_revenue','invalid_refund_link','conflicting_duplicate']}
    invalid_docs={i['record_id'] for i in intake.issues if i['table']=='transactions' and i.get('record_id')}
    limitations=[];evidence=[];net=D(0);cost=D(0);cost_ok=True;sales=set();breakdown={k:D(0) for k in ['service','product','part']}
    # Excluded rows/headers/unknown periods can hide revenue anywhere; conservative coverage flag.
    for i in intake.issues:
        if i['table'] in ['transactions','transaction_items'] and i['code'] in ['missing_key','malformed_row','conflicting_duplicate']:
            limitations.append({'reason':i['code'],'record_id':i.get('record_id')})
    selected=set()
    asof=datetime.fromisoformat(tables['businesses'][0]['as_of'])
    known_dates=[datetime.fromisoformat(t['posted_at']).astimezone(ZoneInfo(tables['businesses'][0]['timezone'])).date() for t in tx.values() if t.get('posted_at')]
    if known_dates and lo<min(known_dates):
        limitations.append({'reason':'period_precedes_available_financial_history','earliest_posting_date':min(known_dates).isoformat()})
    if hi>asof.astimezone(ZoneInfo(tables['businesses'][0]['timezone'])).date():
        limitations.append({'reason':'period_extends_beyond_reporting_clock','as_of':asof.isoformat()})
    for t in tx.values():
        if not t.get('posted_at'):
            limitations.append({'reason':'unknown_posting_date','record_id':t['transaction_id']});continue
        instant=datetime.fromisoformat(t['posted_at']);day=instant.astimezone(ZoneInfo(tables['businesses'][0]['timezone'])).date()
        if not lo<=day<hi or instant>asof:continue
        if t['transaction_id'] in invalid_docs:
            limitations.append({'reason':'invalid_document','record_id':t['transaction_id']});continue
        if t['status']=='Posted':selected.add(t['transaction_id'])
    for l in tables['transaction_items']:
        tid=l['transaction_id']
        if tid not in tx:
            limitations.append({'reason':'orphan_transaction_line','record_id':l['transaction_item_id']});continue
        if tid not in selected:continue
        if staff_id and not l.get('staff_id'):
            limitations.append({'reason':'unknown_staff_attribution','record_id':l['transaction_item_id']});continue
        if staff_id and l['staff_id']!=staff_id:continue
        if l['transaction_item_id'] in badlines:
            limitations.append({'reason':'invalid_line','record_id':l['transaction_item_id']});continue
        item=items.get(l['item_id']);kind=item.get('item_type') if item else None
        if kind not in breakdown:
            limitations.append({'reason':'unapproved_item_type','record_id':l['transaction_item_id']});continue
        value=D(l['net_amount_ex_gst']);net+=value;breakdown[kind]+=value
        if l.get('direct_cost') is None:cost_ok=False
        else:cost+=D(l['direct_cost'])
        if tx[tid]['transaction_type']=='Sale':sales.add(tid)
        evidence.append({'transaction_id':tid,'transaction_item_id':l['transaction_item_id'],'net_amount_ex_gst':l['net_amount_ex_gst']})
    # A posted document without any valid lines must not look like a zero-valued sale.
    all_line_docs={l['transaction_id'] for l in tables['transaction_items']}
    for tid in selected-all_line_docs:limitations.append({'reason':'document_without_lines','record_id':tid})
    complete=not limitations
    margin_entitled=any(r['module']=='gross_margin' and r['entitled'] is True for r in tables.get('capabilities',[]))
    cost_ok=cost_ok and margin_entitled
    return {'status':'Available' if complete else 'Partially Available','period_start':start,'period_end_exclusive':end,'staff_id':staff_id,'currency':'AUD','tax_basis':'excluding GST','net_revenue':amount(net) if complete else None,'supported_net_revenue':amount(net),'service_revenue':amount(breakdown['service']),'product_revenue':amount(breakdown['product']),'part_revenue':amount(breakdown['part']),'sale_transaction_count':len(sales),'average_transaction_value':amount(net/D(len(sales))) if complete and sales else None,'gross_profit':amount(net-cost) if complete and cost_ok else None,'gross_margin_pct':amount((net-cost)/net*100) if complete and cost_ok and net!=0 else None,'limitations':limitations,'evidence':evidence,'metric_version':'revenue_v1_posting_date_refunds','batch_id':intake.batch_id}
