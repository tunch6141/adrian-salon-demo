"""Durable raw -> reviewed clean snapshots. Credentials stay on the Streamlit server."""
from copy import deepcopy
from pathlib import Path
import csv
import io
import json
import uuid
import requests
from piece1_validation.adapter import Intake, SCHEMA, digest
from analytics.runtime import SOURCE, load_snapshot, enrich_snapshot

BUSINESS = 'B001'
FORMAT = 'piece1_owner_review_v1'


def checkpoint(state):
    return {'format': FORMAT, **{k: deepcopy(state.get('p1_'+k, [])) for k in ('decisions','context','sales')}}


def raw_payload(source=SOURCE):
    if isinstance(source, dict):
        payload = deepcopy(source)
    else:
        payload = {'format':'salon_raw_csv_v1', 'tables': {
            p.stem: p.read_bytes().decode('utf-8') for p in sorted(Path(source).glob('*.csv'))}}
    if payload.get('format') != 'salon_raw_csv_v1' or not isinstance(payload.get('tables'),dict):
        raise ValueError('Expected a raw CSV dataset.')
    if not payload['tables'] or set(payload['tables']) - set(SCHEMA):
        raise ValueError('Upload CSVs matching the supported salon field structure.')
    if not all(isinstance(v,str) for v in payload['tables'].values()):
        raise ValueError('Raw tables must contain original CSV text.')
    if len(json.dumps(payload).encode()) > 15_000_000:
        raise ValueError('This demo accepts at most 15 MB of raw CSV data.')
    for name, text in payload['tables'].items():
        reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError(f'{name}: missing or duplicate column headers.')
        if set(reader.fieldnames) - set(SCHEMA[name]):
            raise ValueError(f'{name}: unrecognised columns need an adapter mapping first.')
    business = list(csv.DictReader(io.StringIO(payload['tables'].get('businesses','').lstrip('\ufeff'))))
    if len(business) != 1 or business[0].get('business_id') != BUSINESS:
        raise ValueError('This pilot accepts the B001 salon dataset only.')
    # Guard the minimum structure used throughout this pilot; optional modules can be absent.
    if not {'businesses','staff','customers','items','bookings','transactions','transaction_items'} <= payload['tables'].keys():
        raise ValueError('Include the core salon CSVs in a complete snapshot. Optional modules may be omitted.')
    return payload


def scoped_decisions(raw, decisions):
    """Aliases persist across records; value/identity fixes only follow the reviewed source row."""
    rows = {}
    from piece1_validation.adapter import KEYS
    for table, text in raw['tables'].items():
        rows[table] = {str(r.get(KEYS[table], '')).strip():r for r in csv.DictReader(io.StringIO(text.lstrip('\ufeff')))}
    return [d for d in decisions if not d.get('source_row_hash') or
            digest(rows.get(d['table'],{}).get(d.get('record_id'),{})) == d['source_row_hash']]


def build_snapshot(raw, cp):
    state = {'p1_'+k:cp[k] for k in ('decisions','sales','context')}
    state['p1_decisions'] = scoped_decisions(raw, cp['decisions'])
    intake = load_snapshot(state, raw)
    intake.decisions = deepcopy(cp['decisions'])
    data = {'format':'salon_canonical_v1', **{k:deepcopy(getattr(intake,k)) for k in
        ('tables','issues','audit','lineage','identity','health','headers','batch_id')}}
    return data


def restore_snapshot(record):
    data = record['snapshot']
    if data.get('format') != 'salon_canonical_v1':
        raise ValueError('Unsupported saved dataset version.')
    obj = Intake.__new__(Intake)
    for key in ('tables','issues','audit','lineage','identity','health','headers','batch_id'):
        setattr(obj, key, deepcopy(data[key]))
    obj.source = deepcopy(record['raw'])
    obj.raw = []
    for table, text in obj.source['tables'].items():
        obj.raw.extend({'table':table,'row':n,'record':row} for n,row in
                       enumerate(csv.DictReader(io.StringIO(text.lstrip('\ufeff'))),2))
    obj.decisions = deepcopy(record['checkpoint']['decisions'])
    enrich_snapshot(obj, record['checkpoint']['context'])
    obj.version_id = record['version_id']
    obj.raw_id = record['raw_id']
    obj.revision = record['version_id']
    return obj


class PipelineStore:
    def __init__(self, url, key):
        self.url, self.key = url.rstrip('/'), key
        if not (self.url.startswith('https://') and self.url.endswith('.supabase.co') and key):
            raise ValueError('Configure SUPABASE_URL and the server-side SUPABASE_SERVICE_ROLE_KEY.')

    def rpc(self, name, payload):
        try:
            response = requests.post(self.url+'/rest/v1/rpc/'+name,
                headers={'apikey':self.key,'Authorization':'Bearer '+self.key}, json=payload, timeout=90)
        except requests.RequestException:
            raise ValueError('Supabase could not be reached. No save is confirmed; retry to verify.') from None
        if not response.ok:
            if response.status_code == 409:
                raise ValueError('The saved data changed since review. Refresh and review the latest version before confirming.')
            raise ValueError('Supabase did not confirm this operation. Check the connection and database setup; the previous version remains active.')
        return response.json()

    def current(self):
        return self.rpc('analyst_pipeline_current', {'p_business_id':BUSINESS})

    def ingest(self, raw):
        raw = raw_payload(raw)
        raw_id = digest(raw)
        self.rpc('analyst_pipeline_ingest', {'p_business_id':BUSINESS,'p_raw_id':raw_id,'p_raw':raw})
        return raw_id

    def publish(self, raw, cp, expected, actor, kind, event_id):
        if not actor.strip():
            raise ValueError('Enter the name of the person confirming.')
        raw_id = self.ingest(raw)  # Always preserve the raw input before any cleaning.
        snapshot = build_snapshot(raw, cp)
        version = self.rpc('analyst_pipeline_publish', dict(p_business_id=BUSINESS,
            p_expected_version=expected,p_raw_id=raw_id,p_snapshot=snapshot,p_checkpoint=cp,
            p_event_id=event_id,p_actor=actor,p_kind=kind))
        # Read back the exact committed version, not a potentially newer concurrent head.
        record = self.rpc('analyst_dataset_read', {'p_business_id':BUSINESS,'p_version_id':version})
        if not record or record['snapshot'] != snapshot:
            raise ValueError('The save could not be verified. Reload before making another change.')
        return record

    def history(self):
        return self.rpc('analyst_pipeline_history', {'p_business_id':BUSINESS})


def store_for(setting):
    url, key = setting('SUPABASE_URL'), setting('SUPABASE_SERVICE_ROLE_KEY')
    if not url and not key:
        return None
    return PipelineStore(url,key)


def sync_state(state, record):
    changed = state.get('pipeline_version') != record['version_id']
    for key in ('decisions','context','sales'):
        state['p1_'+key] = deepcopy(record['checkpoint'][key])
    state['pipeline_record'] = record
    state['pipeline_version'] = record['version_id']
    if changed:
        state.pop('piece1_check_results',None)
    return restore_snapshot(record)


def load_active(state, setting):
    if state.get('p1_pending'):
        state['p1_pending'].setdefault('expected_version',state.get('pipeline_version'))
    store = store_for(setting)
    if store is None:
        state['pipeline_connected'] = False
        return load_snapshot(state)
    state['pipeline_connected'] = True
    record = store.current()
    if record is None:
        raw = raw_payload()
        cp = checkpoint({})
        event = str(uuid.uuid5(uuid.NAMESPACE_URL,'salon-pipeline-seed:'+digest(raw)))
        record = store.publish(raw,cp,None,'system:initial_fixture_import','seed',event)
    return sync_state(state,record)


def save_review(state, setting, updates, actor, kind, event_id):
    cp = checkpoint(state)
    for key, value in updates.items():
        cp[key] = deepcopy(value)
    store = store_for(setting)
    if store is None:
        load_snapshot({'p1_'+k:cp[k] for k in ('decisions','context','sales')})
        for k in updates: state['p1_'+k] = cp[k]
        return
    record = state['pipeline_record']
    if 'decisions' in updates:
        from piece1_validation.adapter import KEYS
        for d in cp['decisions']:
            if d in record['checkpoint']['decisions']:continue
            d.setdefault('rule_id',str(uuid.uuid4()))
            if d.get('record_id') and not d.get('source_row_hash'):
                text=record['raw']['tables'].get(d['table'],'')
                row=next((r for r in csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
                          if r.get(KEYS[d['table']])==d['record_id']),{})
                d['source_row_hash']=digest(row)
    # Hold expected version at proposal creation. Another browser may have approved meanwhile.
    expected = state.get('p1_pending',{}).get('expected_version',record['version_id']) if state.get('p1_pending') else record['version_id']
    pending = state.get('p1_pending')
    if pending:
        attempt = pending.setdefault('save_attempt',{'checkpoint':cp,'actor':actor,'kind':kind,'event_id':event_id,
                                                     'raw':record['raw'],'expected':expected})
        if attempt['actor'] != actor or attempt['kind'] != kind:
            raise ValueError('This confirmation has an unverified save. Reload to verify it before changing the approver or action.')
        cp, event_id = attempt['checkpoint'], attempt['event_id']
        result = store.publish(attempt['raw'],cp,attempt['expected'],actor,kind,event_id)
    else:
        result = store.publish(record['raw'],cp,expected,actor,kind,event_id)
    sync_state(state,result)


def import_raw(state, setting, raw):
    store = store_for(setting)
    if store is None: raise ValueError('Connect Supabase before importing a new raw batch.')
    record = state['pipeline_record']
    raw = raw_payload(raw)
    if digest(raw) == record['raw_id']: return False
    event = str(uuid.uuid5(uuid.NAMESPACE_URL,record['version_id']+':import:'+digest(raw)))
    result = store.publish(raw,record['checkpoint'],record['version_id'],
                           'system:approved_rules','automatic_import',event)
    sync_state(state,result)
    return True
