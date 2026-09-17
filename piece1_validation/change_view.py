"""Diff actual canonical records, not a predicted change summary."""
from .adapter import KEYS

def changes(before,after):
    results=[]
    for table in ['bookings','inventory_items','customers','transactions','transaction_items','items']:
        key=KEYS[table];old={r[key]:r for r in before.tables.get(table,[])};new={r[key]:r for r in after.tables.get(table,[])}
        for ident in sorted(set(old)|set(new)):
            a=old.get(ident,{});b=new.get(ident,{})
            for field in sorted(set(a)|set(b)):
                if a.get(field)!=b.get(field):results.append({'Table':table,'Record':ident,'Field':field,'Before':a.get(field),'After':b.get(field),'Change':'Added record' if ident not in old else 'Updated field'})
    old={r['source_customer_id']:r for r in before.identity}
    for r in after.identity:
        a=old.get(r['source_customer_id'],{})
        for field in ['status','customer_id']:
            if a.get(field)!=r.get(field):results.append({'Table':'customer_identity_links','Record':r['source_customer_id'],'Field':field,'Before':a.get(field),'After':r.get(field),'Change':'Approved link'})
    return results

def render_changes(before,after,notes):
    import streamlit as st
    rows=changes(before,after)
    st.subheader('Verify changes in the tables')
    st.caption('Before = cleaned data before owner decisions. After = current session records. Original CSVs remain unchanged. Customer matching changes a link; it does not merge two existing customer records.')
    if rows:st.dataframe([{k:str(v) if v is not None else 'Unavailable' for k,v in r.items()} for r in rows],hide_index=True)
    else:st.info('No confirmed record changes yet.')
    with st.expander('Inspect the current table records'):
        table=st.selectbox('Table',['inventory_items','bookings','customer_identity_links','customers','transactions','transaction_items','business_context'],key='p1_inspect_table')
        data=after.identity if table=='customer_identity_links' else (after.tables.get('business_context',[])+notes if table=='business_context' else after.tables.get(table,[]))
        search=st.text_input('Filter by record ID, name or reference',key='p1_inspect_filter')
        import json
        filtered=[r for r in data if not search or search.casefold() in json.dumps(r).casefold()]
        st.caption(f'{len(filtered)} matching records. Displaying up to 200.')
        st.dataframe([{k:json.dumps(v) if isinstance(v,(dict,list)) else ('' if v is None else str(v)) for k,v in r.items()} for r in filtered[:200]],hide_index=True)
    with st.expander('Who approved the changes?'):
        st.json([a for a in after.audit if a.get('approval')])
