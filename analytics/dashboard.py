"""Inspect live deterministic evidence without an AI call."""
import hmac
from datetime import date,timedelta
import streamlit as st
from .persistence import load_active
from .calculations import staff_summary,pricing_simulation
from .views import build_views

def render(setting):
    password=setting('DEMO_PASSWORD')
    if not password:st.info('Set DEMO_PASSWORD in Streamlit Secrets.');return
    entered=st.text_input('Demo password',type='password',key='evidence_password')
    if not hmac.compare_digest(entered.encode(),password.encode()):return
    try:
        with st.spinner('Loading salon data…'):
            intake=load_active(st.session_state,setting)
    except ValueError as exc:
        st.error(str(exc));return
    st.subheader('Business evidence')
    st.caption(f'Synthetic data · As at {intake.asof:%d %B %Y %H:%M %Z} · Revenue excludes GST. Receivables show their source tax basis.')
    start=st.date_input('From',value=date(2026,9,7),key='evidence_start')
    end=st.date_input('Through',value=date(2026,9,13),key='evidence_end')
    if start>end:st.error('Choose an end date on or after the start.');return
    st.dataframe(staff_summary(intake,str(start),str(end+timedelta(days=1))),hide_index=True)
    st.caption('The dates above filter the staff summary. Each evidence table below retains its own stated period. A note never silently changes revenue or availability.')
    with st.spinner('Preparing business evidence…'):
        frames=build_views(intake)
    choice=st.selectbox('Inspect evidence',list(frames),key='evidence_table')
    st.dataframe(frames[choice],hide_index=True)
    st.download_button('Download this evidence',frames[choice].to_csv(index=False).encode(),'evidence_'+choice+'.csv','text/csv')
    with st.expander('Model a price change'):
        cols=st.columns(3)
        price=cols[0].number_input('Current unit price excluding GST',min_value=0.01,value=70.0)
        proposed=cols[1].number_input('Proposed unit price excluding GST',min_value=0.01,value=66.5)
        volume=cols[2].number_input('Baseline completed volume',min_value=0,value=20)
        has_cost=st.checkbox('I have a reliable direct unit cost')
        cost=st.number_input('Direct unit cost excluding wages',min_value=0.0,value=5.0) if has_cost else None
        st.json(pricing_simulation(price,volume,proposed,cost))
        st.caption('A simulation changes no prices. Additional capacity feasibility needs service duration and available hours.')
