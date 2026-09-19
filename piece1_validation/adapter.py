"""Deterministic single-business CSV intake. No model, network or test-oracle access."""
from pathlib import Path
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
import csv, hashlib, json, re, sqlite3, uuid

from analytics.contracts import EXTENSION_KEYS

SCHEMA=json.loads(Path(__file__).with_name('schema.json').read_text())
KEYS={
 'businesses':'business_id','staff':'staff_id','customers':'customer_id','items':'item_id',
 'bookings':'booking_id','booking_services':'booking_service_id','booking_history':'event_id',
 'transactions':'transaction_id','transaction_items':'transaction_item_id',
 'staff_availability':'availability_id','nonbookable_blocks':'block_id',
 'inventory_items':'item_id','inventory_movements':'movement_id',
 'customer_followups':'followup_id','business_context':'context_id','mapping_rules':'mapping_id',
 'audit_log':'audit_id','customer_import_batch':'source_customer_id',
 'capabilities':'module','customer_profile':'setting','slot_recovery':'cancelled_booking_id'}
KEYS.update(EXTENSION_KEYS)
DATES={'received_at','ordered_at','expected_at','issued_at','created_at','closed_at','presented_at','appointment_start','appointment_end','booking_created_at','event_at','start_after','end_after','posted_at','shift_start','shift_end','start_at','end_at','occurred_at','contacted_at','recorded_at','approved_at','stock_as_of','as_of'}
STATUSES={'booked':'Booked','completed':'Completed','done':'Completed','cancelled':'Cancelled','canceled':'Cancelled','no-show':'No-show','no show':'No-show'}
CHANNELS={'web app':'online','online':'online','phone':'phone','walk_in':'walk_in','walk-in':'walk_in','sms':'sms','email':'email','website':'website','other':'other'}

def serial(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def digest(x):return hashlib.sha256(serial(x).encode()).hexdigest()
def money(value):
    text=str(value).strip()
    if text.startswith('AUD '):text=text[4:]
    result=Decimal(text)
    if not result.is_finite():raise ValueError('Non-finite number')
    return format(result,'f')
def phone(value):
    if not value:return None
    s=re.sub(r'[\s()\-]','',str(value))
    if s.startswith('04') and len(s)==10:s='+61'+s[1:]
    if not re.fullmatch(r'\+\d{8,15}',s):raise ValueError('Unrecognised phone format')
    return s
def timestamp(value, zone="Australia/Melbourne"):
    try:d=datetime.fromisoformat(value)
    except ValueError:d=datetime.strptime(value,'%d/%m/%Y %H:%M').replace(tzinfo=ZoneInfo(zone))
    if d.tzinfo is None:raise ValueError('ISO timestamp must include timezone')
    return d.isoformat()

class Intake:
    def __init__(self,source,decisions=()):
        self.source=Path(source);self.tables={};self.issues=[];self.audit=[];self.lineage=[];self.raw=[];self.headers={};self.identity=[]
        self.zone='Australia/Melbourne'
        business_path=self.source/'businesses.csv'
        if business_path.exists():
            with business_path.open(encoding='utf-8-sig') as f:
                business=next(csv.DictReader(f),{})
                self.zone=business.get('timezone') or self.zone
                ZoneInfo(self.zone)
        self.decisions=list(decisions)
        for d in self.decisions:
            if not all(d.get(k) for k in ['table','field','raw_value','approved_by','approved_at','reason']):raise ValueError('Every decision requires scope, approver, time and reason')
            timestamp(d['approved_at'])
        for table,fields in SCHEMA.items():
            path=self.source/(table+'.csv')
            if not path.exists():continue
            with path.open(encoding='utf-8-sig',newline='') as f:
                reader=csv.DictReader(f);rows=list(reader);self.headers[table]=reader.fieldnames or []
            self.tables[table]=[];seen={};blocked=set()
            for n,raw in enumerate(rows,2):
                self.raw.append({'table':table,'row':n,'record':raw})
                if None in raw:
                    self.issue(table,n,None,'malformed_row','Extra CSV cells');continue
                keyfield=KEYS[table];key=(raw.get(keyfield) or '').strip()
                if not key:
                    self.issue(table,n,keyfield,'missing_key','Row excluded');continue
                if key in seen:
                    if raw==seen[key]:self.log(table,n,keyfield,key,key,'deduplicate','Exact duplicate source record')
                    else:
                        self.issue(table,n,keyfield,'conflicting_duplicate','Both versions excluded pending clarification',record_id=key)
                        blocked.add(key)
                    continue
                seen[key]=raw
                clean={}
                for field,kind in fields.items():
                    original=raw.get(field);value=original
                    decision=next((d for d in reversed(self.decisions) if d['table']==table and d['field']==field and str(d['raw_value'])==str(original) and (not d.get('record_id') or d['record_id']==key)),None)
                    if decision:
                        value=decision.get('value');self.log(table,n,field,original,value,'owner_approved',decision['reason'],decision)
                    try:
                        value=self.normalise(table,field,kind,value)
                    except (ValueError,TypeError,InvalidOperation):
                        self.issue(table,n,field,'invalid_value','Value left unavailable',original,key);value=None
                    clean[field]=value
                    if value is not None and str(value)!=str(original) and not decision:
                        # Normal numeric serialization and booleans are covered by lineage, not correction noise.
                        if str(value).lower()!=str(original).lower() or (field=='email' and value!=original):
                            self.log(table,n,field,original,value,'safe_normalisation','Approved fixture adapter rule')
                self.tables[table].append(clean)
                self.lineage.append({'table':table,'record_id':key,'source_file':path.name,'source_row':n,'raw_sha256':digest(raw)})
            self.tables[table]=[r for r in self.tables[table] if str(r[keyfield]) not in blocked]
        business_ids={r.get('business_id') for t,rows in self.tables.items() for r in rows if r.get('business_id')}
        if business_ids != {'B001'}:raise ValueError('This adapter supports the B001 fixture only; cross-business intake rejected')
        self.validate_relations()
        self.resolve_customers()
        self.health=self.table_health()
        self.batch_id=digest({'raw':self.raw,'headers':self.headers,'decisions':self.decisions,'schema':SCHEMA,'adapter_version':'1.0'})

    def normalise(self,table,field,kind,value):
        if value is None or str(value).strip()=='':return None
        value=str(value).strip()
        if field in DATES:return timestamp(value,self.zone)
        if field in {'work_date','period_start','period_end','owner_next_visit_date','next_action_date'}:
            return datetime.strptime(value,'%Y-%m-%d').date().isoformat()
        if field=='email':return value.lower()
        if field=='mobile':return phone(value)
        if table=='staff' and field=='staff_name':
            approved={'sarah':'Sarah','matthew':'Matthew','sam':'Sam'}
            return approved.get(value.casefold(),value)
        if table=='bookings' and field=='status':return STATUSES[value.casefold()] if value.casefold() in STATUSES else self.fail()
        if field=='booking_source':return CHANNELS[value.casefold()] if value.casefold() in CHANNELS else self.fail()
        if kind=='number':return money(value)
        if kind=='boolean':
            if value.lower() not in ['true','false']:raise ValueError('Expected boolean')
            return value.lower()=='true'
        return value
    @staticmethod
    def fail():raise ValueError('Unapproved category')
    def log(self,table,row,field,old,new,action,reason,approval=None):
        self.audit.append(dict(table=table,source_row=row,field=field,original=old,clean=new,action=action,reason=reason,approval=approval))
    def issue(self,table,row,field,code,message,raw_value=None,record_id=None):
        self.issues.append(dict(table=table,source_row=row,field=field,code=code,message=message,raw_value=raw_value,record_id=record_id))
    def validate_relations(self):
        staff={r['staff_id'] for r in self.tables.get('staff',[])}
        aliases={r['raw_value'].casefold():r['canonical_id'] for r in self.tables.get('mapping_rules',[]) if r['entity']=='staff' and r['status']=='approved'}
        for table,rows in self.tables.items():
            if table in ['staff','mapping_rules','audit_log']:continue
            for r in rows:
                key=r.get(KEYS[table]);lin=next((x for x in self.lineage if x['table']==table and x['record_id']==key),{})
                for field in ['staff_id','staff_id_after']:
                    if field not in r or not r[field] or r[field] in staff:continue
                    old=r[field];target=aliases.get(old.casefold())
                    if target in staff:
                        r[field]=target;self.log(table,lin.get('source_row'),field,old,target,'approved_mapping','Previously approved staff alias')
                    else:
                        r[field]=None;self.issue(table,lin.get('source_row'),field,'unknown_staff','Clarify staff identity; other fields retained',old,key)
        # Financial relationships are mandatory for exact revenue, optional cost remains independent.
        tx={r['transaction_id'] for r in self.tables.get('transactions',[])}
        items={r['item_id'] for r in self.tables.get('items',[])}
        lines={r['transaction_item_id']:r for r in self.tables.get('transaction_items',[])}
        for r in lines.values():
            key=r['transaction_item_id']
            for f,allowed in [('transaction_id',tx),('item_id',items)]:
                if r[f] not in allowed:self.issue('transaction_items',None,f,'broken_reference','Revenue coverage incomplete',r[f],key)
            fields=['gross_amount_ex_gst','discount_ex_gst','refund_ex_gst','net_amount_ex_gst']
            if any(r[f] is None for f in fields):self.issue('transaction_items',None,'net_amount_ex_gst','missing_financial_value','Revenue coverage incomplete',record_id=key)
            elif Decimal(r[fields[0]])-Decimal(r[fields[1]])-Decimal(r[fields[2]])!=Decimal(r[fields[3]]):
                self.issue('transaction_items',None,'net_amount_ex_gst','inconsistent_revenue','Line excluded; no silent recalculation',record_id=key)
            elif any(Decimal(r[f])<0 for f in fields[:3]):
                self.issue('transaction_items',None,'net_amount_ex_gst','inconsistent_revenue','Gross, discount and refund use nonnegative magnitudes',record_id=key)
            if r.get('refund_ex_gst') and Decimal(r['refund_ex_gst'])>0:
                original=lines.get(r.get('original_transaction_item_id'))
                if not original or original['item_id']!=r['item_id']:
                    self.issue('transaction_items',None,'original_transaction_item_id','invalid_refund_link','Refund provenance unresolved',record_id=key)
        for t in self.tables.get('transactions',[]):
            if not t.get('posted_at') or t.get('status') not in ['Posted','Draft'] or t.get('transaction_type') not in ['Sale','Refund']:
                self.issue('transactions',None,None,'invalid_document','Document not safely classifiable',record_id=t['transaction_id'])

    def resolve_customers(self):
        customers=self.tables.get('customers',[])
        for candidate in self.tables.get('customer_import_batch',[]):
            mobile=candidate.get('mobile');email=candidate.get('email')
            hits={r['customer_id'] for r in customers if (mobile and r.get('mobile')==mobile) or (email and r.get('email')==email)}
            choice=next((d for d in reversed(self.decisions) if d['table']=='customer_import_batch' and d['field']=='customer_id' and d['raw_value']==candidate['source_customer_id']),None)
            if choice:
                target=choice['value']
                if target=='new_identity':
                    cid='CUS_'+uuid.uuid5(uuid.NAMESPACE_URL,'B001/customer_import_batch/'+candidate['source_customer_id']).hex[:20]
                    row={f:None for f in SCHEMA['customers']};row.update(candidate);row.update(business_id='B001',customer_id=cid);customers.append(row)
                elif target in hits:cid=target
                else:raise ValueError('Owner identity choice must be one of the actual contact matches or new_identity')
                resolution={'source_customer_id':candidate['source_customer_id'],'status':'owner_confirmed','customer_id':cid,'reason':choice['reason']}
                self.identity.append(resolution)
                self.log('customer_import_batch',None,'customer_id',candidate['source_customer_id'],cid,'owner_approved',choice['reason'],choice)
                continue
            if len(hits)>1:
                resolution={'source_customer_id':candidate['source_customer_id'],'status':'clarify_conflict','customer_id':None,'candidates':sorted(hits)}
                self.issue('customer_import_batch',None,None,'identity_conflict','Mobile and email resolve to different identities',record_id=candidate['source_customer_id'])
            elif len(hits)==1:
                cid=next(iter(hits));resolution={'source_customer_id':candidate['source_customer_id'],'status':'matched','customer_id':cid,'reason':'Exact normalised mobile or email; source contact not overwritten'}
            else:
                cid='CUS_'+uuid.uuid5(uuid.NAMESPACE_URL,'B001/customer_import_batch/'+candidate['source_customer_id']).hex[:20]
                resolution={'source_customer_id':candidate['source_customer_id'],'status':'new_identity','customer_id':cid,'reason':'No strong contact match; name-only similarity not merged'}
                row={f:None for f in SCHEMA['customers']};row.update(candidate);row.update(business_id='B001',customer_id=cid);customers.append(row)
            self.identity.append(resolution)
            self.log('customer_import_batch',None,'customer_id',candidate['source_customer_id'],resolution.get('customer_id'),'identity_resolution',resolution.get('reason','Conflicting strong identifiers require clarification'))
        self.tables['customers']=customers

    def table_health(self):
        result={}
        for table in SCHEMA:
            issues=[i for i in self.issues if i['table']==table]
            result[table]={'state':'Missing' if table not in self.tables else ('Invalid' if not self.tables[table] and issues else ('Partially Available' if issues else 'Available')),'rows':len(self.tables.get(table,[])),'issue_count':len(issues)}
        return result

    def save(self,path):
        """Append immutable snapshots and audit events. Identical imports are idempotent."""
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(path) as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS batches(batch_id TEXT PRIMARY KEY, imported_at TEXT, payload TEXT);
              CREATE TABLE IF NOT EXISTS raw_rows(batch_id TEXT, source_table TEXT, source_row INTEGER, payload TEXT, PRIMARY KEY(batch_id,source_table,source_row));
              CREATE TABLE IF NOT EXISTS audit_events(event_id TEXT PRIMARY KEY, batch_id TEXT, payload TEXT);
              CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT);''')
            payload={'tables':self.tables,'health':self.health,'issues':self.issues,'identity':self.identity,'lineage':self.lineage}
            con.execute('INSERT OR IGNORE INTO batches VALUES(?,?,?)',(self.batch_id,datetime.now(ZoneInfo('UTC')).isoformat(),serial(payload)))
            con.executemany('INSERT OR IGNORE INTO raw_rows VALUES(?,?,?,?)',[(self.batch_id,r['table'],r['row'],serial(r['record'])) for r in self.raw])
            con.executemany('INSERT OR IGNORE INTO audit_events VALUES(?,?,?)',[(digest({'batch':self.batch_id,'event':e}),self.batch_id,serial(e)) for e in self.audit])
            con.execute("INSERT OR REPLACE INTO state VALUES('current_batch',?)",(self.batch_id,))
        return self.batch_id

    def report(self):
        field_health={}
        for table,fields in SCHEMA.items():
            field_health[table]={}
            for field in fields:
                rows=self.tables.get(table,[]);present=sum(r.get(field) is not None for r in rows)
                problems=[i for i in self.issues if i['table']==table and i['field']==field]
                state='Missing' if table not in self.tables or field not in self.headers.get(table,[]) else ('Invalid' if problems and not present else ('Partially Available' if problems or present<len(rows) else 'Available'))
                field_health[table][field]={'state':state,'non_null_rows':present,'rows':len(rows),'issue_count':len(problems)}
        return {'batch_id':self.batch_id,'health':self.health,'field_health':field_health,'issues':self.issues,'identity_resolutions':self.identity,'correction_events':len(self.audit),'lineage_rows':len(self.lineage)}
