"""One corrected snapshot shared by the validation page and analytical chat."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json
from piece1_validation.adapter import Intake
from piece1_validation.amendments import apply_sales

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'data/handoff_2026_09_18/raw'

def load_snapshot(state=None, source=SOURCE):
    state=state if state is not None else {}
    intake=apply_sales(Intake(source,state.get('p1_decisions',[])),state.get('p1_sales',[]))
    names={r['staff_id']:r['staff_name'] for r in intake.tables.get('staff',[])}
    rows=[]
    for raw in intake.tables.get('business_context',[])+state.get('p1_context',[]):
        if raw.get('confirmed') is False:continue
        rows.append({'id':raw['context_id'],'entity':raw.get('entity') or names.get(raw.get('staff_id')) or ('Customer '+raw['customer_id'] if raw.get('customer_id') else 'Salon'),
                     'start_date':raw['period_start'],'end_date':raw['period_end'],'event_type':raw.get('event_type') or 'owner_report',
                     'explanation':raw['explanation'],'source_name':raw['source_name'],'recorded_at':raw['recorded_at'],
                     'status':'active','source_type':raw.get('source_type','owner_reported'),'causality_verified':False,
                     'customer_id':raw.get('customer_id')})
    # Deduplicate stable IDs. Original notes are never overwritten by a new chat turn.
    intake.contexts=list({r['id']:r for r in rows}.values())
    intake.revision=hashlib.sha256((intake.batch_id+json.dumps(intake.contexts,sort_keys=True)).encode()).hexdigest()
    intake.zone=ZoneInfo(intake.tables['businesses'][0]['timezone'])
    intake.asof=datetime.fromisoformat(intake.tables['businesses'][0]['as_of']).astimezone(intake.zone)
    return intake

class CombinedContextStore:
    """Read source + Piece 1 + analyst notes; preserve the existing reviewed write path."""
    def __init__(self,intake,store):
        self.intake,self.store=intake,store
        self.persistent=store.persistent
    def search(self,entity='',start='',end=''):
        source=[r for r in self.intake.contexts if (not entity or entity=='Salon' or r['entity'] in [entity,'Salon']) and (not start or r['end_date']>=start) and (not end or r['start_date']<=end)]
        rows=self.store.search(entity,start,end)
        return list({r['id']:r for r in source+rows}.values())
    def save(self,*args,**kwargs):return self.store.save(*args,**kwargs)
    def retract(self,record_id):
        if any(r['id']==record_id for r in self.intake.contexts):
            raise ValueError('Source and Piece 1 notes cannot be retracted in the analyst log. Correct their originating record.')
        return self.store.retract(record_id)
