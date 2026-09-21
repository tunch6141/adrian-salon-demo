"""Isolated commercial-reasoning experiment; not the accepted default chat."""
import streamlit as st
from analyst_ui import render

st.set_page_config(page_title='Stage 1 preview',layout='wide')
st.title('Stage 1 preview')
st.warning('Experimental: this version has not passed the commercial reasoning checks. Use the main app for your regular salon chat.')
render(None,lambda key:st.secrets.get(key,''))
