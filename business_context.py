"""Owner-reviewed persistent context. Separate from analytical facts and model writes."""
import uuid
from datetime import date, datetime, timezone
import requests

FIELDS=['id','entity','start_date','end_date','event_type','explanation','source_name','recorded_at','status','origin_id','change_reason']

class ContextStore:
    def __init__(self,url='',key='',session_rows=None,events=None):
        self.url=url.rstrip('/')
        self.key=key
        self.rows=session_rows if session_rows is not None else []
        self.persistent=bool(url and key)
        self.events=events if events is not None else []
    def _request(self,method,table='business_context',**kwargs):
        if not self.url.startswith('https://') or not self.url.endswith('.supabase.co'):
            raise ValueError('Use your HTTPS Supabase project URL.')
        response=requests.request(method,self.url+'/rest/v1/'+table,headers={'apikey':self.key,'Authorization':'Bearer '+self.key,'Prefer':'return=representation'},timeout=20,**kwargs)
        if not response.ok:raise ValueError('Context database unavailable. Check Supabase table and server key. No success is assumed.')
        return response.json()
    def search(self,entity='',start='',end=''):
        if start:date.fromisoformat(start)
        if end:date.fromisoformat(end)
        # Fetch relevant records on server; cap with explicit error, never silently omit evidence.
        if self.persistent:
            params={'select':','.join(FIELDS),'status':'eq.active','limit':'501','order':'start_date.desc'}
            if entity and entity!='Salon':params['entity']='in.('+entity+',Salon)'
            if start:params['end_date']='gte.'+start
            if end:params['start_date']='lte.'+end
            rows=self._request('GET',params=params)
        else:
            rows=[r for r in self.rows if r['status']=='active' and (not entity or entity=='Salon' or r['entity'] in [entity,'Salon']) and (not start or r['end_date']>=start) and (not end or r['start_date']<=end)]
        if len(rows)>500:raise ValueError('Too much matching context. Narrow the period.')
        return rows
    def save(self,draft,source_name,record_id=None):
        if draft['entity'] not in ['Sarah','Matthew','Sam','Salon']:raise ValueError('Choose a known staff member or Salon.')
        start,end=date.fromisoformat(str(draft['start_date'])),date.fromisoformat(str(draft['end_date']))
        if start>end:raise ValueError('End date precedes start date.')
        if not draft['explanation'].strip() or not source_name.strip():raise ValueError('Explanation and source name are required.')
        row={k:str(draft[k]) for k in ['entity','start_date','end_date','event_type','explanation']}
        row.update(id=record_id or str(uuid.uuid4()),source_name=source_name.strip(),recorded_at=datetime.now(timezone.utc).isoformat(),status='active')
        if len(row['explanation'])>2000:raise ValueError('Keep context under 2,000 characters.')
        if self.persistent:
            return self._request('POST',json=row)[0]
        if any(r['id']==row['id'] for r in self.rows):return next(r for r in self.rows if r['id']==row['id'])
        self.rows.append(row)
        return row
    def all_rows(self):
        rows=self._request('GET',params={'select':','.join(FIELDS),'limit':'501','order':'recorded_at.desc'}) if self.persistent else self.rows
        if len(rows)>500:raise ValueError('Too many notes to edit safely; narrow the log first.')
        return rows

    def history(self,record_id):
        if self.persistent:return self._request('GET',table='business_context_audit',params={'context_id':'eq.'+record_id,'order':'recorded_at.desc','limit':'500'})
        return [e for e in self.events if e['context_id']==record_id]

    def correct(self,original,draft,actor,reason,retract=False):
        from copy import deepcopy
        if not actor.strip() or not reason.strip():raise ValueError('Enter your name and the reason for this change.')
        # Reuse all normal validation without writing anything.
        updated=ContextStore().save(draft,actor,original['id'])
        updated.update(status='retracted' if retract else 'active',change_reason=reason.strip(),retracted_by=actor.strip() if retract else None)
        current=deepcopy(original)
        if original.get('source_record'):
            current={k:v for k,v in original.items() if k in FIELDS}
            current['origin_id']=original['id']
            current['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'salon-context:'+original['id']))
            updated['id']=current['id']
            updated['origin_id']=original['id']
            existing=next((r for r in self.all_rows() if r['id']==current['id']),None)
            if existing:raise ValueError('This source note has changed. Reload the context log before editing.')
            if self.persistent:self._request('POST',json=current)
            else:self.rows.append(deepcopy(current))
        if self.persistent:
            rows=self._request('PATCH',params={'id':'eq.'+current['id'],'recorded_at':'eq.'+current['recorded_at'],'status':'eq.'+current['status']},json=updated)
            if not rows:raise ValueError('Someone changed this note. Reload the context log before editing.')
            return rows[0]
        target=next((r for r in self.rows if r['id']==current['id']),None)
        if not target or target.get('recorded_at')!=current.get('recorded_at') or target['status']!=current['status']:
            raise ValueError('This note changed. Reload before editing.')
        self.events.append(dict(context_id=current['id'],operation='UPDATE',actor=actor,recorded_at=updated['recorded_at'],before_record=deepcopy(target),after_record=deepcopy(updated)))
        target.update(updated)
        return target

    def retract(self,record_id,actor=''):
        if self.persistent:
            if not actor.strip():raise ValueError('Retraction requires your name.')
            return self._request('PATCH',params={'id':'eq.'+record_id},json={'status':'retracted','retracted_by':actor})
        for r in self.rows:
            if r['id']==record_id:r['status']='retracted'
