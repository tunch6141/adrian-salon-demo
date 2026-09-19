import json
import uuid
from datetime import date
import hmac
import pandas as pd
import streamlit as st
import altair as alt
from analyst_engine import Database, QueryBlocked
from analyst_ai import investigate
from business_context import ContextStore


def safe_text(text):st.markdown(text.replace('$',r'\$'))


def build_chart(df,chart):
    x,y=chart['x'],chart['y']
    series=chart.get('series','')
    c=alt.Chart(df)
    tooltip=[alt.Tooltip(col,type='quantitative' if pd.api.types.is_numeric_dtype(df[col]) else 'nominal') for col in df.columns]
    if chart['kind']=='pie':
        return c.mark_arc().encode(theta=alt.Theta(y,type='quantitative'),color=alt.Color(x,type='nominal'),tooltip=tooltip)
    c=(c.mark_line(point=True) if chart['kind']=='line' else c.mark_bar()).encode(x=alt.X(x,type='ordinal',sort=None),y=alt.Y(y,type='quantitative'),tooltip=tooltip)
    if series:
        c=c.encode(color=alt.Color(series,type='nominal',title='Staff' if series=='staff_name' else series))
        if chart['kind']=='bar':c=c.encode(xOffset=alt.XOffset(series,type='nominal'))
    return c

def render_result(item):
    status=item['status']
    if status=='explanation':
        st.info('The app retrieved data but could not verify its written explanation. That does not mean your business question is unanswerable. The tables contain the retrieved figures; the explanation was withheld to avoid presenting an unchecked claim.')
    elif status=='facts_only':
        st.info('The results were retrieved, but the written explanation did not pass its checks. Showing the calculated results instead.')
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
                st.dataframe(pd.DataFrame(result['rows']).head(10),hide_index=True)
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
        for claim in a['claims']:
            safe_text(claim['text'])
        if item['plan'].get('diagnostic') and len(item['plan']['diagnostic']['staff'])>1 and item['results']:
            summary=pd.DataFrame(item['results'][0]['rows'])
            if 'staff_name' in summary:
                comparison=summary.set_index('staff_name').T
                comparison.index=([str(x).replace('_',' ').title() for x in comparison.index])
                st.dataframe(comparison.round(2),use_container_width=True)
        chart=a['chart']
        if chart['kind']!='none':
            df=pd.DataFrame(item['results'][chart['result']]['rows'])
            x,y=chart['x'],chart['y']
            st.altair_chart(build_chart(df,chart),use_container_width=True)
        for label,key in [('What was investigated','investigation'),('Suggested action','recommendation'),('What to measure','measurement')]:
            if a[key]:
                with st.expander(label):safe_text(a[key])
        if a['missing_information']:st.info(a['missing_information'])
    if item.get('timing'):
        timing=item['timing']
        st.caption(f"Completed in {timing['total_seconds']:.1f}s · {len(timing['calls'])} AI calls")
    if item['results']:
        with st.expander('Evidence and calculations'):
            st.caption(item['plan']['scope'])
            for i,result in enumerate(item['results']):
                st.write(f'Result {i} · {result["table"]} · {result["row_count"]} rows')
                st.dataframe(pd.DataFrame(result['rows']),hide_index=True)
                st.code(result['sql'],language='sql')
            if item['contexts']:
                st.write('Relevant owner-reported context — not independently verified:')
                st.dataframe(pd.DataFrame(item['contexts']),hide_index=True)
            if item.get('issues'):st.write(item['issues'])
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
            rows=store.search()
            st.dataframe(pd.DataFrame(rows),hide_index=True)
            st.download_button('Export context log',json.dumps(rows,indent=2),'business_context.json','application/json')
            if rows:
                ids=[r['id'] for r in rows]
                chosen=st.selectbox('Note to retract',ids,format_func=lambda i: next(r['entity']+' · '+r['start_date']+' · '+r['event_type'] for r in rows if r['id']==i))
                confirm=st.checkbox('Confirm retraction of this note')
                if st.button('Retract selected note',disabled=not confirm):
                    store.retract(chosen);st.rerun()
        except Exception:st.error('Context log is unavailable. Check the database connection.')


def render(t,setting):
    st.subheader('Ask your salon')
    st.caption('Version 5 · Handoff 18 September · Shared corrected data')
    key,model,password=setting('OPENAI_API_KEY'),setting('OPENAI_MODEL'),setting('DEMO_PASSWORD')
    if not (key and model and password):
        st.info('Add OPENAI_API_KEY, OPENAI_MODEL and DEMO_PASSWORD in Streamlit Secrets.');return
    entered=st.text_input('Demo password',type='password',key='v4_password')
    if not hmac.compare_digest(entered.encode(),password.encode()):
        st.caption('Enter the demo password to continue.');return
    rows=st.session_state.setdefault('context_rows',[])
    store=ContextStore(setting('SUPABASE_URL'),setting('SUPABASE_SERVICE_ROLE_KEY'),rows)
    if hasattr(t,'tables'):
        from analytics.runtime import CombinedContextStore
        store=CombinedContextStore(t,store)
    if not store.persistent:st.info('Context is session-only until Supabase is connected. It will not survive a reboot or a new browser session.')
    revision=getattr(t,'revision','legacy')
    if st.session_state.get('analyst_data_revision') != revision:
        st.session_state['v4_turns']=[]
        st.session_state['analyst_data_revision']=revision
    turns=st.session_state.setdefault('v4_turns',[])
    if st.button('New conversation'):
        st.session_state.v4_turns=[]
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
                db=Database.from_intake(t) if hasattr(t,'tables') else Database(t)
                history=[{'question':x['question'],'plan':x['result']['plan'],'answer':x['result']['answer'],'status':x['result']['status']} for x in turns[-5:]]
                # History is only interpretation context; each answer retrieves fresh database evidence.
                result=investigate(OpenAI(api_key=key,timeout=60,max_retries=0),model,db,question.strip(),history,store,on_stage=lambda stage: progress.update(label=stage))
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
