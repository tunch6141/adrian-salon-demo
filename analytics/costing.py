"""Analytical cost allocation. Never overwrites official accounting COGS."""
from collections import defaultdict
from datetime import datetime
from decimal import Decimal as D
from .calculations import landed_receipts,num

def allocate_costs(intake):
    receipts={r['receipt_item_id']:r for r in landed_receipts(intake)}
    lots=defaultdict(list);events=[];allocations=[];original=defaultdict(list);returned=defaultdict(lambda:D(0))
    items={r['item_id']:r for r in intake.tables.get('items',[])}
    for b in intake.tables.get('inventory_batches',[]):
        source=receipts.get(b['receipt_item_id']);unit=source['landed_unit_cost'] if source else None
        if unit is None:continue
        events.append((b['received_at'],0,'receipt',dict(b,unit=D(str(unit)),remaining=num(b['received_quantity']))))
    docs={r['transaction_id']:r for r in intake.tables.get('transactions',[])}
    for r in intake.tables.get('transaction_items',[]):
        doc=docs.get(r['transaction_id'])
        if doc and doc.get('posted_at') and doc['status']=='Posted' and datetime.fromisoformat(doc['posted_at'])<=intake.asof:
            events.append((doc['posted_at'],1,'line',r))
    # Physical adjustments consume stock; returned stock is handled by refund lines below.
    for r in intake.tables.get('inventory_movements',[]):
        if r['movement_type'] in ['supplier_return','damaged_writeoff','manual_adjustment','service_usage'] and num(r['quantity_delta']) is not None:
            events.append((r['occurred_at'],2,'movement',r))
    def consume(item,quantity,batch=None):
        taken=[];left=quantity
        candidates=[b for b in lots[item] if not batch or b['batch_id']==batch]
        for b in candidates:
            q=min(left,b['remaining'])
            if q>0:taken.append((b,q));b['remaining']-=q;left-=q
            if left<=0:break
        return taken,left
    for when,_,kind,r in sorted(events,key=lambda e:(datetime.fromisoformat(e[0]),e[1])):
        if datetime.fromisoformat(when)>intake.asof:continue
        iid=r['item_id']
        if kind=='receipt':lots[iid].append(r);continue
        if kind=='movement':
            delta=num(r['quantity_delta'])
            if delta<0:consume(iid,-delta,r.get('batch_id'))
            # Positive unexplained adjustments do not invent purchase cost or supplier.
            continue
        lid=r['transaction_item_id'];quantity=num(r['quantity']);cost=num(r.get('direct_cost'));refund=num(r.get('refund_ex_gst')) or 0
        if quantity is None or quantity<=0:continue
        slices=[]
        if refund>0:
            source=r.get('original_transaction_item_id');remaining=quantity;skip=returned[source]
            for old in original[source]:
                available=D(str(old['quantity']))
                if skip>=available:skip-=available;continue
                available-=skip;skip=D(0);q=min(remaining,available)
                if q<=0:continue
                # Restore original acquisition provenance, never cost a return from a later batch.
                slices.append((old.get('batch_id'),old.get('supplier_id'),q,-D(str(old['unit_cost'])) if old['unit_cost'] is not None else None,'return_reversal:'+old['provenance']))
                for b in lots[iid]:
                    if b['batch_id']==old.get('batch_id'):b['remaining']+=q
                remaining-=q
                if remaining<=0:break
            returned[source]+=quantity-remaining
            if remaining>0:slices.append((None,None,remaining,None,'unknown_return_allocation'))
            if cost is not None:
                slices=[(None,None,quantity,cost/quantity,'explicit_cost')]
        else:
            taken,left=consume(iid,quantity,r.get('batch_id'))
            if r.get('batch_id'):
                slices=[(b['batch_id'],b['supplier_id'],q,b['unit'],'exact_batch') for b,q in taken]
                if left:slices.append((r['batch_id'],None,left,None,'unknown_batch_quantity'))
            elif cost is not None:slices=[(None,None,quantity,cost/quantity,'explicit_cost')]
            elif taken:
                slices=[(b['batch_id'],b['supplier_id'],q,b['unit'],'FIFO_estimated') for b,q in taken]
                if left:slices.append((None,None,left,None,'unknown_receipt_shortage'))
            else:
                known=[b for b in lots[iid] if b['unit'] is not None]
                fallback=known[-1]['unit'] if known else num(items.get(iid,{}).get('unit_cost'))
                slices=[(None,None,quantity,fallback,'latest_cost_fallback' if fallback is not None else 'unknown')]
        for index,(batch,supplier,q,unit,provenance) in enumerate(slices):
            out={'allocation_id':lid+f':{index}','transaction_item_id':lid,'item_id':iid,'batch_id':batch,'supplier_id':supplier,
                 'quantity':float(q),'unit_cost':float(unit) if unit is not None else None,'allocated_cost':float(q*unit) if unit is not None else None,
                 'provenance':provenance,'posted_at':when,'accounting_note':'Analytical allocation; source accounting COGS remains unchanged.'}
            allocations.append(out)
            if not refund:original[lid].append(out)
    return allocations
