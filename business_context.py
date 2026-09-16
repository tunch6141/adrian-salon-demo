"""Owner-reviewed persistent context. Separate from analytical facts and model writes."""
import uuid
from datetime import date, datetime, timezone
import requests

FIELDS=['id','entity','start_date','end_date','event_type','explanation','source_name','recorded_at','status']

class ContextStore:
    def __init__(self,url='',key='',session_rows=None):
        self.url=url.rstrip('/')
        self.key=key
        self.rows=session_rows if session_rows is not None else []
        self.persistent=bool(url and key)
    def _request(self,method,**kwargs):
        if not self.url.startswith('https://') or not self.url.endswith('.supabase.co'):
            raise ValueError('Use your HTTPS Supabase project URL.')
        response=requests.request(method,self.url+'/rest/v1/business_context',headers={'apikey':self.key,'Authorization':'Bearer '+self.key,'Prefer':'return=representation'},timeout=20,**kwargs)
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
    def retract(self,record_id):
        if self.persistent:return self._request('PATCH',params={'id':'eq.'+record_id},json={'status':'retracted'})
        for r in self.rows:
            if r['id']==record_id:r['status']='retracted'
