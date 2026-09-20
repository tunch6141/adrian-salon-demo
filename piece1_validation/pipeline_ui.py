"""Owner-facing import and immutable approval history."""
import io
import json
from pathlib import PurePosixPath
import zipfile
import streamlit as st
from analytics.persistence import raw_payload, import_raw, store_for


def render_pipeline(intake, setting):
    if not st.session_state.get('pipeline_connected'):
        st.info('Local preview: connect Supabase to save raw data, cleaned versions and approvals across sessions.')
        return
    st.caption(f'Saved in Supabase · Cleaned version {intake.version_id[:8]} · Raw batch {intake.raw_id[:12]}')
    with st.expander('Import a raw data snapshot'):
        st.write('Upload a ZIP containing the salon CSV tables, or select the CSV files together. Each import is a complete snapshot, not an append. Previously approved rules are reused; new ambiguities remain visible for review.')
        uploads = st.file_uploader('Raw CSV files or one ZIP',type=['csv','zip'],accept_multiple_files=True,key='pipeline_upload')
        bundle=io.BytesIO()
        with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,text in intake.source['tables'].items():archive.writestr(name+'.csv',text.encode('utf-8'))
        st.download_button('Download current raw snapshot',bundle.getvalue(),'raw_snapshot.zip','application/zip')
        if uploads and st.button('Import raw data',key='pipeline_import'):
            try:
                tables={}
                def add(name,content):
                    table=PurePosixPath(name).stem
                    if table in tables: raise ValueError('Duplicate CSV table: '+table)
                    tables[table]=content.decode('utf-8')
                if len(uploads)==1 and uploads[0].name.lower().endswith('.zip'):
                    with zipfile.ZipFile(io.BytesIO(uploads[0].getvalue())) as archive:
                        files=[f for f in archive.infolist() if not f.is_dir()]
                        if len(files)>100 or sum(f.file_size for f in files)>15_000_000:
                            raise ValueError('Upload at most 100 files and 15 MB uncompressed.')
                        for f in files:
                            if not f.filename.lower().endswith('.csv'): raise ValueError('The ZIP must contain CSV files only.')
                            add(f.filename,archive.read(f))
                else:
                    if sum(f.size for f in uploads)>15_000_000:raise ValueError('Upload at most 15 MB.')
                    for f in uploads:
                        if not f.name.lower().endswith('.csv'):raise ValueError('Select CSV files or one ZIP.')
                        add(f.name,f.getvalue())
                changed=import_raw(st.session_state,setting,raw_payload({'format':'salon_raw_csv_v1','tables':tables}))
                st.session_state['p1_pending']=None
                st.session_state['p1_notice']='Raw data saved and approved rules applied. Review any new unresolved issues below.' if changed else 'This raw batch is already active; no duplicate version was created.'
                st.rerun()
            except (ValueError,KeyError,UnicodeError,zipfile.BadZipFile) as exc:
                st.error(str(exc))
    with st.expander('Approval and import history'):
        st.caption('Most recent 100 events. Names are self-reported under the shared demo password. Automatic imports link back to the rules originally approved by an owner.')
        try:
            events=store_for(setting).history()
            labels={'seed':'Initial raw import','automatic_import':'New import using approved rules',
                    'correction':'Owner confirmed correction','manual_sale':'Owner confirmed missing sale',
                    'context':'Owner recorded context','checkpoint_restore':'Reviewed checkpoint restored'}
            st.dataframe([{'When':e['approved_at'],'Who':e['actor'],'Action':labels.get(e['kind'],e['kind']),
                'Cleaned version':e['version_id'],'Previous version':e.get('previous_version_id')} for e in events],hide_index=True)
            if events:
                selected=st.selectbox('Inspect an event',range(len(events)),
                    format_func=lambda i:events[i]['approved_at']+' · '+labels.get(events[i]['kind'],events[i]['kind'])+' · '+events[i]['actor'],key='pipeline_history_event')
                event=events[selected];details=event['details'];changes=details.get('changes',{})
                rows=[{'Table':d['table'],'Record':d.get('record_id','Matching future records'),
                       'Field':d['field'],'Original value':d['raw_value'],'Approved value':d['value'],
                       'Confirmed by':d['approved_by'],'Confirmed at':d['approved_at'],'Reason':d['reason']}
                      for d in changes.get('decisions',[])]
                if rows:st.dataframe(rows,hide_index=True)
                for label,key in [('Confirmed missing sales','sales'),('Recorded business context','context')]:
                    if changes.get(key):st.write(label);st.dataframe(changes[key],hide_index=True)
                reused=set(details.get('reused_rule_ids',[]))
                if event['kind']=='automatic_import':
                    st.write('The original data was preserved and existing approved cleaning rules were applied automatically.')
                    rules=[d for d in intake.decisions if d.get('rule_id') in reused]
                    if rules:st.dataframe([{'Original value':d['raw_value'],'Approved value':d['value'],
                        'Originally confirmed by':d['approved_by'],'Originally confirmed at':d['approved_at']} for d in rules],hide_index=True)
                st.caption('Unresolved issues after this event: '+str(details.get('unresolved_issue_count','See saved version')))
                st.download_button('Download selected event',json.dumps(event,indent=2),'approval_event.json','application/json')
            st.download_button('Download approval history',json.dumps(events,indent=2),'approval_history.json','application/json')
        except ValueError as exc: st.error(str(exc))
