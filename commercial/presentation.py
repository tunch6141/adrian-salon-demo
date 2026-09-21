"""Concise diagnosis; full execution evidence stays in an optional expander."""
import json
import pandas as pd
import streamlit as st


def render_commercial(item,build_chart,safe_text):
    status=item['status']
    if status=='context':
        st.info('Review the business-context draft below before saving it.')
    elif status=='clarify':safe_text(item['plan']['missing_information'])
    elif status!='answered':
        st.info('I could not yet verify a commercial conclusion. The evidence and remaining checks are available below.')
        for issue in item.get('issues',[])[:2]:safe_text(issue)
    else:
        a=item['answer'];d=item['display']
        safe_text(d['direct_answer'])
        for text in d['key_evidence']:safe_text(text)
        if d['primary_driver'] and d['primary_driver']!=d['direct_answer']:safe_text(d['primary_driver'])
        for text in d['secondary_drivers']:safe_text(text)
        if d['alternatives']:
            with st.expander('Other explanations and uncertainty'):
                for text in d['alternatives']:safe_text(text)
        if d['next_step']:
            st.caption('Next investigation' if a['next_step_kind']=='investigation' else 'Suggested next step')
            safe_text(d['next_step'])
        if a['limitations']:safe_text(a['limitations'])
        for index in a['table_results']:
            st.dataframe(pd.DataFrame(item['results'][index]['rows']),hide_index=True,use_container_width=True)
        if a['visual']['kind']!='none':
            chart=a['visual']
            st.altair_chart(build_chart(pd.DataFrame(item['results'][chart['result']]['rows']),chart),use_container_width=True)
        relevant=[c for c in a['context_review'] if c['relevance']!='not_relevant']
        if relevant:
            with st.expander('How business context was considered'):
                notes={c['id']:c for c in item['contexts']}
                for review in relevant:
                    note=notes[review['context_id']]
                    st.caption('Owner-reported · '+note['entity']+' · '+note['start_date']+' to '+note['end_date'])
                    safe_text(note['explanation']);safe_text(review['interpretation'])
    if item.get('timing'):
        st.caption(f"Completed in {item['timing']['total_seconds']:.1f}s · {len(item['timing']['calls'])} AI calls")
    with st.expander('Evidence and calculations'):
        st.write('Analysis scope',item['analytical_state']['scope'])
        st.write('Hypotheses tested',item['hypothesis_tests'])
        for r in item['results']:
            st.caption(r['table']);st.dataframe(pd.DataFrame(r['rows']),hide_index=True)
        if item.get('issues'):st.write('Remaining checks',item['issues'])
        st.download_button('Download investigation record',json.dumps(item,indent=2,default=str),
            file_name='commercial_investigation.json',mime='application/json',key='audit_'+str(id(item)))
