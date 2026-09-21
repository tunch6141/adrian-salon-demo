"""Owner-triggered acceptance run; evaluation material stays outside normal chat."""
import hmac,json
import streamlit as st

st.set_page_config(page_title='Stage 1 checks',layout='wide')
st.title('Stage 1 checks')
st.caption('Development acceptance checks. These use model calls and read-only copies of the cleaned data. They do not change your records.')
password=str(st.secrets.get('DEMO_PASSWORD',''))
entered=st.text_input('Demo password',type='password')
if not password or not hmac.compare_digest(password,entered):st.stop()

from evals.stage1 import cases,run
from analytics.persistence import load_active
from openai import OpenAI

selected=st.multiselect('Cases to run',[c['id'] for c in cases()],default=[c['id'] for c in cases()])
with st.expander('Reuse a previous check'):
    prior_state_text=st.text_area('Previous staff analysis (optional)',help='Paste the analytical_state from a completed staff check to test its follow-up without rerunning the staff check.')
if st.button('Run selected checks',disabled=not selected):
    intake=load_active(st.session_state,lambda key:st.secrets.get(key,''))
    progress=st.empty()
    interim=st.empty()
    previous_staff=next((r['result']['analytical_state'] for r in st.session_state.get('stage1_reports',[]) if r['id']=='staff' and r.get('result')),None)
    if prior_state_text.strip():
        try:previous_staff=json.loads(prior_state_text)
        except ValueError:
            st.error('The previous analysis must be valid JSON.');st.stop()
    def record_progress(current):
        st.session_state.stage1_reports=list(current)
        interim.markdown('| Completed case | Status | Automated review |\n|---|---|---|\n'+
            '\n'.join(f"| {r['id']} | {r['status']} | {'Pass' if r['passed'] else 'Review needed'} |" for r in current))
    reports=run(OpenAI(api_key=st.secrets['OPENAI_API_KEY'],timeout=60,max_retries=0),'gpt-4.1-mini',intake,selected,
        lambda name,n:progress.info(f'Checking {name} ({n+1} of {len(selected)})'),record_progress,previous_staff)
    st.session_state.stage1_reports=reports
    interim.empty()
    progress.success('Selected checks finished.')
if st.session_state.get('stage1_reports'):
    reports=st.session_state.stage1_reports
    st.write(f"{sum(r['passed'] for r in reports)} of {len(reports)} passed automated review. Review the evidence before accepting Stage 1.")
    st.dataframe([dict(case=r['id'],group=r['group'],status=r['status'],passed=r['passed'],issues='; '.join((r.get('grade') or {}).get('issues',[])) or r.get('error','')) for r in reports],hide_index=True)
    st.download_button('Download acceptance results',json.dumps(reports,indent=2,default=str),'stage1_acceptance.json','application/json')
    with st.expander('Detailed results'):
        st.code(json.dumps(reports,indent=2,default=str),language='json')
