import json
import uuid
from datetime import date
import hmac
import pandas as pd
import streamlit as st
import altair as alt
from analyst_engine import Database, QueryBlocked, validate_chart
from commercial.v2_runtime import investigate, ANSWER_RELEASE
from business_context import ContextStore


def numerical_prose(text):
    """Display simple prose counts as digits, including quoted leave durations."""
    import re
    words='zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
    pattern=r'\b('+ '|'.join(words)+r')(?=\s+(?:days?|weeks?|months?|hours?|appointments?|bookings?|visits?|percent|per cent)\b)'
    return re.sub(pattern,lambda m:str(words.index(m[0].lower())),text,flags=re.I)


def safe_text(text):st.markdown(numerical_prose(text).replace('$',r'\$'))


def display_frame(rows):
    """Format mixed/transposed tables before pandas turns numbers into objects."""
    frame=pd.DataFrame(rows)
    for col in frame.columns:
        frame[col]=frame[col].map(lambda v: f'{v:,.2f}'.rstrip('0').rstrip('.') if isinstance(v,float) else v)
    return frame


def result_chart(item):
    """A valid data chart does not depend on successful prose generation."""
    chart=(item.get('answer') or {}).get('chart')
    if chart and chart['kind']!='none':
        try:validate_chart(item['results'],chart);return chart
        except QueryBlocked:pass
    for i,result in enumerate(item.get('results',[])):
        if not result['rows']:continue
        if result['table']=='approved_revenue_trend':
            chart=dict(kind='line',result=i,x='period_start',y='net_revenue_aud',series='staff_name')
        elif result['table']=='approved_staff_summary' and len(result['rows'])>1:
            chart=dict(kind='bar',result=i,x='staff_name',y='service_revenue_aud',series='')
        else:continue
        try:validate_chart(item['results'],chart);return chart
        except QueryBlocked:continue
    return None


def verified_trend_summary(item):
    scope=item.get('plan',{}).get('trend')
    if not scope:return []
    label={'service':'service','product':'retail','part':'part','all':'total net'}[scope['category']]
    summaries=[]
    for result in item.get('results',[]):
        if result['table']!='approved_trend_totals':continue
        for row in result['rows']:
            text=f"{row['staff_name']}: {label} revenue totalled AUD {row['net_revenue_aud']:,.2f} from {scope['start_date']} to {scope['end_date']}."
            low,high=row.get('minimum_complete_bucket_revenue'),row.get('maximum_complete_bucket_revenue')
            if low is not None and high is not None:text+=f" Complete {scope['grain']} periods ranged from AUD {low:,.2f} to AUD {high:,.2f}."
            delta=row.get('last_minus_first_complete_bucket')
            if delta is not None:text+=f" Change from the first to last complete {scope['grain']}: AUD {delta:+,.2f}."
            pattern=row.get('complete_bucket_pattern')
            if pattern=='fluctuating':text+=' The complete periods fluctuated.'
            elif pattern=='nondecreasing':text+=' Revenue did not decrease between the complete periods.'
            summaries.append(text)
    return summaries


def diagnostic_facts(item):
    """Present approved module values directly; the model explains their meaning."""
    diagnostic=item.get('plan',{}).get('diagnostic')
    if not diagnostic:return []
    results=item.get('results',[])
    current=next((r['rows'] for r in results if r.get('table')=='approved_staff_summary'),[])
    comparisons=next((r['rows'] for r in results if r.get('table')=='approved_comparison_summary'),[])
    compared={r['staff_name']:r for r in comparisons}
    lines=[]
    for row in current:
        start,end=diagnostic['start_date'],diagnostic['end_date']
        period=start if start==end else f'{start} to {end}'
        text=f"{row['staff_name']} · {period}: service revenue AUD {row['service_revenue_aud']:,.2f}."
        if row.get('completed_appointments') is not None:text+=f" {row['completed_appointments']:g} completed appointments; {row['completed_service_hours']:g} completed service hours."
        if row.get('bookable_hours') is not None:text+=f" {row['bookable_hours']:g} bookable hours"
        if row.get('realised_utilisation_pct') is not None:text+=f"; utilisation {row['realised_utilisation_pct']:.2f}%"
        text=text.rstrip('.')+'.'
        if row.get('revenue_per_service_hour') is not None:text+=f" Service revenue per completed service hour: AUD {row['revenue_per_service_hour']:,.2f}."
        prior=compared.get(row['staff_name'])
        if prior and prior.get('service_revenue_aud_baseline_value') is not None:
            text+=f" Baseline {prior['baseline_start']} to {prior['baseline_end']} (total divided by {prior['baseline_divisor']}): AUD {prior['service_revenue_aud_baseline_value']:,.2f}. Revenue change: AUD {prior['service_revenue_aud_difference']:+,.2f} ({prior['service_revenue_aud_percentage_change']:+.2f}%)."
        lines.append(text)
    return lines


def build_chart(df,chart):
    x,y=chart['x'],chart['y']
    series=chart.get('series','')
    c=alt.Chart(df)
    tooltip=[alt.Tooltip(col,type='quantitative' if pd.api.types.is_numeric_dtype(df[col]) else 'nominal') for col in df.columns]
    if chart['kind']=='pie':
        pie=c.mark_arc().encode(theta=alt.Theta(y,type='quantitative'),color=alt.Color(x,type='nominal'),tooltip=tooltip)
        return pie.facet(column=alt.Column(series,type='nominal',title='Staff')) if series else pie
    c=(c.mark_line(point=True) if chart['kind']=='line' else c.mark_bar()).encode(x=alt.X(x,type='ordinal',sort=None),y=alt.Y(y,type='quantitative'),tooltip=tooltip)
    if series:
        c=c.encode(color=alt.Color(series,type='nominal',title='Staff' if series=='staff_name' else series))
        if chart['kind']=='bar':c=c.encode(xOffset=alt.XOffset(series,type='nominal'))
    return c

def render_result(item):
    if item.get('engine') in ['commercial_stage1','commercial_native_tools']:
        from commercial.presentation import render_commercial
        return render_commercial(item,build_chart,safe_text)
    status=item['status']
    scope=item.get('plan',{}).get('diagnostic') or item.get('plan',{}).get('revenue') or item.get('plan',{}).get('trend') or item.get('plan',{}).get('financial')
    if scope and item.get('reporting_date') and scope['start_date']<=item['reporting_date']<scope['end_date']:
        st.caption('Actual results are to date through '+item['reporting_date']+'; the requested period has not finished. Future bookings are scheduled, not completed revenue.')
    if status=='explanation':
        st.info('The app retrieved data but could not verify its written explanation. That does not mean your business question is unanswerable. The tables contain the retrieved figures; the explanation was withheld to avoid presenting an unchecked claim.')
    elif status=='facts_only':
        st.info('The investigation could not complete all its checks. Showing the verified results retrieved so far.')
        for line in verified_trend_summary(item):safe_text(line)
        for result in item['results']:
            if result['table']=='approved_period_comparison':
                for row in result['rows']:
                    if row['metric']=='service_revenue_aud':
                        change=row['difference']
                        if change is None:continue
                        direction='higher' if change>0 else 'lower' if change<0 else 'unchanged'
                        divisor=row['baseline_divisor']
                        baseline_label='total' if divisor==1 else f'total divided by {divisor:g}'
                        st.write(f"{row['staff_name']}: AUD {row['current_value']:,.2f} service revenue for {row['current_start']} to {row['current_end']}. Baseline {row['baseline_start']} to {row['baseline_end']} ({baseline_label}): AUD {row['baseline_value']:,.2f}. Difference: AUD {abs(change):,.2f} {direction}.")
        if item['plan'].get('diagnostic') and item['results']:
            st.dataframe(pd.DataFrame(item['results'][0]['rows']),hide_index=True)
        else:
            for result in item['results'][:2]:
                st.caption(result['table'])
                st.dataframe(pd.DataFrame(result['rows']),hide_index=True)
    elif status=='context':
        st.info('I have prepared an owner-context draft. Review the dates and explanation below before saving.')
    elif status in ['unsupported','clarify']:
        st.info('No verified answer is available for this request.')
        st.caption('What information is missing or needs clarifying:')
        safe_text(item['plan']['missing_information'])
    elif status=='blocked':
        st.warning('The evidence check did not approve an answer. I have withheld the explanation; you can inspect the query results below or ask a narrower question.')
    else:
        a=item['answer']
        for fact in diagnostic_facts(item):safe_text(fact)
        if item['plan'].get('booking_id'):
            for result in item['results']:
                for row in result['rows']:
                    if row.get('id_match')=='unique match ignoring leading zero padding':
                        st.caption(f"Matched {row['requested_booking_id']} to booking {row['booking_id']} by its unique number.")
        for claim in a['claims']:
            safe_text(claim['text'])
        if item['plan'].get('trend'):
            st.caption('Calendar periods are clipped to your requested dates. Partial first/last periods should not be compared with full periods.')
        if item['plan'].get('financial') or item['plan'].get('customer') or item['plan'].get('booking_id') or item['plan'].get('trend') or (item['plan'].get('queries') and not item['plan'].get('diagnostic')):
            for result in item['results']:
                if result['table']=='approved_trend_totals':continue
                frame=pd.DataFrame(result['rows'])
                if 'appointment_start' in frame and 'appointment_end' in frame:
                    cols=list(frame.columns);cols.remove('appointment_end');cols.insert(cols.index('appointment_start')+1,'appointment_end');frame=frame[cols]
                st.dataframe(frame,hide_index=True,use_container_width=True)
        if item['plan'].get('diagnostic') and len(item['plan']['diagnostic']['staff'])>1 and item['results']:
            summary=pd.DataFrame(item['results'][0]['rows'])
            if 'staff_name' in summary:
                comparison=display_frame(summary).set_index('staff_name').T
                comparison.index=([str(x).replace('_',' ').title() for x in comparison.index])
                st.dataframe(comparison.round(2),use_container_width=True)
        for label,key in [('What was investigated','investigation'),('Suggested action','recommendation'),('What to measure','measurement')]:
            if a[key]:
                with st.expander(label):safe_text(a[key])
        if a['missing_information']:st.info(a['missing_information'])
        if a.get('context_review'):
            notes={c['id']:c for c in item.get('contexts',[])}
            with st.expander('How business context was considered'):
                for review in a['context_review']:
                    note=notes.get(review.get('context_id'))
                    if note:
                        st.caption(f"Owner-reported · {note['entity']} · {note['start_date']} to {note['end_date']}")
                        safe_text(note['explanation'])
                        safe_text(review.get('interpretation',''))
    chart=result_chart(item)
    if chart:
        st.altair_chart(build_chart(pd.DataFrame(item['results'][chart['result']]['rows']),chart),use_container_width=True)
    if item.get('timing'):
        timing=item['timing']
        st.caption(f"Completed in {timing['total_seconds']:.1f}s · {len(timing['calls'])} AI calls")
    if item['results'] or item.get('issues') or item.get('contexts'):
        with st.expander('Evidence and calculations'):
            st.caption(item['plan']['scope'])
            if item.get('dataset_version'):st.caption('Cleaned data version: '+item['dataset_version'])
            if item.get('answer_release'):st.caption('Answer release: '+item['answer_release'])
            for i,result in enumerate(item['results']):
                st.write(f'Result {i} · {result["table"]} · {result["row_count"]} rows')
                st.dataframe(pd.DataFrame(result['rows']),hide_index=True)
                st.code(result['sql'],language='sql')
            if item['contexts']:
                st.write('Relevant owner-reported context — not independently verified:')
                st.dataframe(pd.DataFrame(item['contexts']),hide_index=True)
            if item.get('issues'):st.write(item['issues'])
            if item.get('execution_notes'):st.write(item['execution_notes'])
            if item.get('timing'):st.write(item['timing']['calls'])


def context_form(store):
    pending=st.session_state.get('context_draft') or {}
    with st.expander('Review and record business context',expanded=bool(pending)):
        st.caption('Nothing is saved automatically. A reported explanation does not change capacity, remove an anomaly or establish causality.')
        if not pending:
            st.write('You can also add a note here directly.')
        known=['Sarah','Matthew','Sam','Salon']
        def parsed(key):
            try:return date.fromisoformat(pending.get(key,''))
            except ValueError:return None
        with st.form('context_review_'+st.session_state.get('draft_id','manual')):
            entity=st.selectbox('Applies to',known,index=known.index(pending.get('entity','Salon')) if pending.get('entity','Salon') in known else 3)
            start=st.date_input('Event start date',value=parsed('start_date'))
            end=st.date_input('Event end date',value=parsed('end_date'))
            kind=st.text_input('Event type',value=pending.get('event_type',''))
            explanation=st.text_area('Owner-reported explanation',value=pending.get('explanation',''),max_chars=2000)
            source=st.text_input('Reported by',placeholder='Your name (self-reported for this pilot)')
            confirmed=st.checkbox('I confirm these dates and this explanation should be recorded as owner-provided context.')
            save=st.form_submit_button('Save context to database' if store.persistent else 'Keep context for this session')
        if save:
            try:
                if not confirmed or start is None or end is None:raise ValueError('Confirm the note and enter both event dates.')
                store.save(dict(entity=entity,start_date=start.isoformat(),end_date=end.isoformat(),event_type=kind,explanation=explanation),source,st.session_state.get('draft_id'))
                st.session_state.pop('context_draft',None)
                st.session_state.pop('draft_id',None)
                st.success('Saved to the context database.' if store.persistent else 'Kept for this session only. Export below if you want a copy.')
            except Exception:
                st.error('The note was not confirmed saved. Check the dates, source and database connection.')
    with st.expander('Context log'):
        try:
            rows=store.all_rows()
            st.dataframe(display_frame(rows),hide_index=True)
            st.download_button('Export context log',json.dumps(rows,indent=2),'business_context.json','application/json')
            if rows:
                ids=[r['id'] for r in rows]
                chosen=st.selectbox('Note to review or correct',ids,format_func=lambda i: next(r['entity']+' · '+r['start_date']+' · '+r['event_type']+' · '+r['status'] for r in rows if r['id']==i))
                original=next(r for r in rows if r['id']==chosen)
                st.caption('Corrections apply to future answers. Previous conversation replies remain historical. Original raw data is preserved.')
                with st.form('correct_context_'+chosen+'_'+original.get('recorded_at','')):
                    known=['Sarah','Matthew','Sam','Salon']
                    if original['entity'] not in known:known.append(original['entity'])
                    entity=st.selectbox('Corrected applies to',known,index=known.index(original['entity']))
                    start=st.date_input('Corrected start date',date.fromisoformat(original['start_date']))
                    end=st.date_input('Corrected end date',date.fromisoformat(original['end_date']))
                    kind=st.text_input('Corrected event type',original['event_type'])
                    explanation=st.text_area('Corrected explanation',original['explanation'],max_chars=2000)
                    actor=st.text_input('Changed by',key='context_actor_'+chosen)
                    reason=st.text_input('Reason for change',key='context_reason_'+chosen)
                    action=st.selectbox('Change', ['Save correction','Retract note'])
                    confirmed=st.checkbox('I approve this change and its entry in the change history.')
                    submitted=st.form_submit_button('Confirm context change')
                if submitted:
                    try:
                        if not confirmed:raise ValueError('Please approve the change before saving.')
                        store.correct(original,dict(entity=entity,start_date=start.isoformat(),end_date=end.isoformat(),event_type=kind,explanation=explanation),actor,reason,retract=action=='Retract note')
                        st.session_state['context_change_saved']=True
                        st.rerun()
                    except ValueError as exc:st.error(str(exc))
                if st.session_state.pop('context_change_saved',False):st.success('Context updated. The change history preserves the previous version.')
                if not original.get('source_record'):
                    events=store.history(chosen)
                    st.write('Change history')
                    for event in events:
                        before=event.get('before_record') or {};after=event.get('after_record') or {}
                        st.caption(str(event['recorded_at'])+' · '+str(event['actor'])+' · '+str(event['operation']))
                        st.write('Reason: '+str(after.get('change_reason') or 'Original note'))
                        fields=['entity','start_date','end_date','explanation','status']
                        st.dataframe(pd.DataFrame([{'Field':k,'Before':before.get(k,''),'After':after.get(k,'')} for k in fields]),hide_index=True)
                    st.download_button('Export selected change history',json.dumps(events,indent=2),'context_change_history.json','application/json')
        except Exception:st.error('Context log is unavailable. Check the database connection.')


def render(t,setting):
    st.subheader('Ask your salon')
    st.caption('Cleaned-data answers and commercial diagnostics · '+ANSWER_RELEASE)
    key,model,password=setting('OPENAI_API_KEY'),setting('OPENAI_MODEL'),setting('DEMO_PASSWORD')
    if not (key and model and password):
        st.info('Add OPENAI_API_KEY, OPENAI_MODEL and DEMO_PASSWORD in Streamlit Secrets.');return
    entered=st.text_input('Demo password',type='password',key='v4_password')
    if not hmac.compare_digest(entered.encode(),password.encode()):
        st.caption('Enter the demo password to continue.');return
    if t is None:
        from analytics.persistence import load_active
        try:
            with st.spinner('Loading saved salon data…'):
                t=load_active(st.session_state,setting)
        except ValueError as exc:
            st.error(str(exc));return
    if getattr(t,'version_id',None):
        st.caption(f"Using saved cleaned version {t.version_id[:8]} · {len(t.issues)} unresolved data issues")
    else:
        st.info('Local preview: Supabase data storage is not connected.')
    rows=st.session_state.setdefault('context_rows',[])
    store=ContextStore(setting('SUPABASE_URL'),setting('SUPABASE_SERVICE_ROLE_KEY'),rows,st.session_state.setdefault('context_events',[]))
    if hasattr(t,'tables'):
        from analytics.runtime import CombinedContextStore
        store=CombinedContextStore(t,store)
    if not store.persistent:st.info('Context is session-only until Supabase is connected. It will not survive a reboot or a new browser session.')
    revision=ANSWER_RELEASE+':'+getattr(t,'revision','legacy')
    if st.session_state.get('analyst_data_revision') != revision:
        st.session_state['v4_turns']=[]
        st.session_state.pop('active_analytical_state',None)
        st.session_state['analyst_data_revision']=revision
    turns=st.session_state.setdefault('v4_turns',[])
    if st.button('New conversation'):
        st.session_state.v4_turns=[]
        st.session_state.pop('active_analytical_state',None)
        st.session_state.pop('context_draft',None)
        st.session_state.pop('draft_id',None)
        st.rerun()
    for turn in turns:
        with st.chat_message('user'):safe_text(turn['question'])
        with st.chat_message('assistant'):render_result(turn['result'])
    with st.form('question_v4',clear_on_submit=True):
        question=st.text_input('Your question or follow-up',max_chars=1500,placeholder='Show Sarah’s weekly service revenue from April to August as a line chart.')
        submitted=st.form_submit_button('Send question')
    if submitted and question.strip():
        from openai import OpenAI
        db=None
        try:
            with st.status('Investigating your question…',expanded=True) as progress:
                db=Database.from_intake(t,rules_override='Stage 1 uses commercial.contract data definitions.') if hasattr(t,'tables') else Database(t)
                history=[{'question':x['question'],'plan':x['result']['plan'],'answer':x['result']['answer'],'status':x['result']['status'],
                    'resolved_records':[{k:row[k] for k in ['booking_id','customer_id','customer_name','appointment_date','first_completed_visit_date'] if k in row} for r in x['result']['results'] if r['table'] in ['booking_records','approved_customer_profile'] for row in r['rows'][:1]],
                    'issues':x['result'].get('issues',[]),'execution_notes':x['result'].get('execution_notes',[]),
                    'retrieved_scopes':[{'table':r['table'],'sql':r['sql']} for r in x['result']['results']]}
                    for x in turns[-5:]]
                # History is only interpretation context; each answer retrieves fresh database evidence.
                result=investigate(OpenAI(api_key=key,timeout=60,max_retries=0),model,db,question.strip(),[],store,
                    active_state=st.session_state.get('active_analytical_state'),on_stage=lambda stage: progress.update(label=stage))
                if result['status']!='context':st.session_state.active_analytical_state=result['analytical_state']
                result['dataset_version']=getattr(t,'version_id',t.revision)
                st.session_state.v4_turns=(turns+[{'question':question.strip(),'result':result}])[-10:]
                if result['status']=='context' and result['plan']['draft']:
                    st.session_state.context_draft=result['plan']['draft']
                    st.session_state.draft_id=str(uuid.uuid4())
            st.rerun()
        except QueryBlocked as e:st.warning(str(e))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error('Analyst request failed: %s', type(exc).__name__)
            st.error('The investigation could not complete. No answer or context was saved for this request. Check model access, API limits and context connection, then retry with a narrower question.')
        finally:
            if db:db.close()
    context_form(store)
    st.caption(f'Answers use the reporting clock {t.asof.isoformat() if hasattr(t, "asof") else "legacy"}. Queries are read-only. Source context is owner-reported, not established cause.')
