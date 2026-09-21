"""Isolated commercial-reasoning experiment; not the accepted default chat."""
import streamlit as st
from analyst_ui import render

st.set_page_config(page_title='Stage 1 preview',layout='wide')
st.title('Stage 1 preview')
st.warning('Experimental: this version has not passed the commercial reasoning checks. Use the main app for your regular salon chat.')
model=st.selectbox('Preview model',['gpt-4.1-mini','gpt-5.4-mini'])
render(None,lambda key:model if key=='OPENAI_MODEL' else st.secrets.get(key,''))
