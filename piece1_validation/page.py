"""Isolated validation UI; consumes raw fixture data, not expected clean answers."""
from pathlib import Path
import copy,hmac,json,os,tempfile
import streamlit as st
from .adapter import Intake
from .metrics import revenue

def render():
    st.set_page_config(page_title='Piece 1 | Data validation',layout='wide')
    st.title('Piece 1 — Data validation')
    st.caption('Build P1-UI-1 · Synthetic revised dataset · Reporting clock: 17 September 2026, 6 pm Melbourne')
    try:password=str(st.secrets.get('DEMO_PASSWORD',os.environ.get('DEMO_PASSWORD','')))
    except (FileNotFoundError,KeyError):password=os.environ.get('DEMO_PASSWORD','')
    if not password:
        st.info('Set DEMO_PASSWORD in Streamlit Secrets to open this validation page. No AI API key is needed.')
        return
    entered=st.text_input('Demo password',type='password',key='piece1_password')
    if not hmac.compare_digest(entered.encode(),password.encode()):
        st.caption('Enter your existing demo password to continue.');return
    st.write('Check raw-data cleaning and revenue calculations before connecting them to the analyst.')
    try:intake=Intake(Path(__file__).with_name('sample_raw'))
    except Exception as exc:
        st.error(f'Validation data could not load: {type(exc).__name__}: {exc}')
        st.info('Check that the entire piece1_validation folder was uploaded beside app.py.');return
    person=st.selectbox('Revenue scope',['Sarah','Matthew','Sam','Whole business'])
    staff={'Sarah':'S01','Matthew':'S02','Sam':'S03','Whole business':None}[person]
    result=revenue(intake,'2026-09-07','2026-09-14',staff)
    st.subheader('Revenue for 7–13 September 2026')
    if result['status']=='Available':
        columns=st.columns(4)
        for c,label,key in zip(columns,['Service revenue','Retail revenue','Total net revenue','Average transaction value'],['service_revenue','product_revenue','net_revenue','average_transaction_value']):
            c.metric(label,'Unavailable' if result[key] is None else f"AUD {float(result[key]):,.2f}")
        st.caption(f"{result['sale_transaction_count']} sales · GST excluded · Refunds recognised on posting date")
    else:st.warning('An exact total is unavailable. Review the limitations.');st.json(result)
    st.subheader('Cleaning and unresolved issues')
    columns=st.columns(3)
    columns[0].metric('Clean booking records',len(intake.tables['bookings']))
    columns[1].metric('Unresolved issues',len(intake.issues))
    columns[2].metric('Raw booking rows',sum(r['table']=='bookings' for r in intake.raw))
    st.dataframe([{'Table':i['table'],'Record':i.get('record_id'),'Field':i['field'],'Problem':i['code'],'Explanation':i['message']} for i in intake.issues],hide_index=True)
    st.caption('The staff alias, missing stock cost and conflicting customer match remain unresolved. They do not prevent this revenue calculation.')
    with st.expander('See corrections and identity matches'):
        st.dataframe([{'Table':a['table'],'Row':a['source_row'],'Field':a['field'],'Original':str(a['original']),'Cleaned':str(a['clean']),'Action':a['action']} for a in intake.audit],hide_index=True)
        st.json(intake.identity)
    with st.expander('See data health and revenue evidence'):
        st.dataframe([{'Table':t,**h} for t,h in intake.health.items()],hide_index=True)
        st.dataframe(result.get('evidence',[]),hide_index=True)
    st.subheader('Run deployment checks')
    st.write('These checks exercise the deployed adapter. Expected figures are test assertions, never input to the revenue calculator.')
    if st.button('Run validation checks',type='primary'):
        checks=[]
        def check(label,ok):checks.append({'Check':label,'Result':'PASS' if ok else 'FAIL'})
        sarah=revenue(intake,'2026-09-07','2026-09-14','S01')
        check('Sarah service revenue = AUD 1,380',sarah['service_revenue']=='1380.00')
        check('Sarah retail revenue = AUD 30',sarah['product_revenue']=='30.00')
        check('Sarah total = AUD 1,410, average sale = AUD 94',sarah['net_revenue']=='1410.00' and sarah['average_transaction_value']=='94.00')
        check('Duplicate booking removed: 832 raw → 831 clean',len(intake.tables['bookings'])==831 and sum(r['table']=='bookings' for r in intake.raw)==832)
        check('Ambiguous staff and stock cost remain unknown',intake.tables['bookings'][3]['staff_id'] is None and intake.tables['inventory_items'][3]['unit_cost'] is None)
        check('Conflicting customer identifiers require clarification',intake.identity[-1]['status']=='clarify_conflict')
        no_inventory=copy.deepcopy(intake)
        for table in ['inventory_items','inventory_movements']:no_inventory.tables.pop(table,None)
        check('Revenue still works without inventory',revenue(no_inventory,'2026-09-07','2026-09-14','S01')['net_revenue']=='1410.00')
        full=revenue(intake,'2026-06-22','2026-09-14')
        check('Full-history control = AUD 94,295 / 699 sales',full['net_revenue']=='94295.00' and full['sale_transaction_count']==699)
        # SQLite is only a disposable deployment check; no persistent cloud-storage claim.
        with tempfile.TemporaryDirectory(prefix='piece1_check_') as tmp:
            import sqlite3
            db=Path(tmp)/'check.sqlite';intake.save(db);intake.save(db)
            with sqlite3.connect(db) as con:count=con.execute('SELECT COUNT(*) FROM batches').fetchone()[0]
        check('Identical imports do not create duplicate snapshots',count==1)
        st.session_state['piece1_check_results']=checks
    if 'piece1_check_results' in st.session_state:
        checks=st.session_state['piece1_check_results'];st.dataframe(checks,hide_index=True)
        if all(c['Result']=='PASS' for c in checks):st.success(f"All {len(checks)} deployment checks passed.")
        else:st.error('Some checks failed. Download the report before proceeding.')
    st.download_button('Download validation report',json.dumps({'build':'P1-UI-1','intake':intake.report(),'revenue':result,'deployment_checks':st.session_state.get('piece1_check_results',[]),'scope':'Data intake and revenue only. Live AI, booking capacity and permanent cloud storage are not tested.'},indent=2),file_name='piece1_validation_report.json',mime='application/json')
    st.info('This page validates Piece 1 only. The original chatbot still uses its original data. Permanent storage and AI integration come later.')
