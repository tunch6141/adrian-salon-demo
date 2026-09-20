from datetime import datetime
import re
import streamlit as st
from .amendments import sale_record,validate_sales

def render_sale(pending,owner):
    st.write('**Missing sale to review:** '+pending['text'])
    st.info('This is a financial amendment, not a business-context note. Confirm that it is a new completed sale—not a payment for an already recorded invoice. Nothing is added until you confirm.')
    token=pending['token'];text=pending['text']
    names={'Sarah':'S01','Matthew':'S02','Sam':'S03'}
    match=next((n for n in names if re.search(r'\b'+n+r'\b',text,re.I)),None)
    staff=st.selectbox('Staff for this sale',['']+list(names),index=(list(names).index(match)+1 if match else 0),key='sale_staff:'+token)
    dm=re.search(r'\b(\d{1,2}/\d{1,2}/\d{4})\b',text);seed=None
    if dm:
        try:seed=datetime.strptime(dm[1],'%d/%m/%Y').date()
        except ValueError:pass
    day=st.date_input('Sale date',value=seed,key='sale_date:'+token)
    am=re.search(r'(?:AUD\s*|\$\s*)(\d[\d,]*(?:\.\d+)?)',text,re.I)
    amount=st.text_input('Amount received in AUD',value=am[1].replace(',','') if am else '',key='sale_amount:'+token)
    tax=st.selectbox('Does that amount include GST?',['','AUD excluding GST','AUD including 10% GST'],key='sale_tax:'+token)
    category=st.selectbox('Revenue category',['','service','product','part'],key='sale_category:'+token)
    description=st.text_input('What was sold?',key='sale_description:'+token)
    reference=st.text_input('Unique receipt or sale reference',key='sale_reference:'+token)
    distinct=st.checkbox('I checked that this is a completed sale missing from the records, not payment for an existing sale.',key='sale_distinct:'+token)
    values=[staff,str(day),amount,tax,category,description,reference,owner,distinct]
    if st.button('Review missing sale',key='sale_review'):
        try:
            if not distinct:raise ValueError('Check the existing records before adding a sale.')
            row=sale_record(names.get(staff),day,amount,tax,category,description,reference,owner,text)
            validate_sales(st.session_state.get('p1_sales',[])+[row])
            pending['review']={'row':row,'values':values}
        except (ValueError,TypeError) as exc:st.error(str(exc))
    reviewed=pending.get('review')
    if reviewed:
        r=reviewed['row'];st.write(f'**Proposed addition:** {staff}, {r["sale_date"]}, {r["description"]}: AUD {r["net_amount_ex_gst"]} net revenue excluding GST. Reference: {r["source_reference"]}.')
        st.caption('No direct cost, customer or booked hours have been supplied. Profit is unavailable for an affected period, and no service hours or stock movements will be invented.')
        changed=reviewed['values']!=values
        if changed:st.warning('The details changed. Review the sale again before confirming.')
        if st.button('Confirm missing sale',type='primary',disabled=changed,key='sale_confirm'):
            try:
                from analytics.persistence import save_review
                from .chat_ui import setting
                import uuid
                updated=validate_sales(st.session_state.get('p1_sales',[])+[r])
                save_review(st.session_state,setting,{'sales':updated},owner,'manual_sale',pending.setdefault('event_id',str(uuid.uuid4())))
                st.session_state['p1_pending']=None;st.session_state['p1_notice']=f'Sale recorded for {r["sale_date"]}. Select a revenue period containing that date to see the effect. Raw CSVs were not changed.';st.rerun()
            except ValueError as exc:st.error(str(exc))
