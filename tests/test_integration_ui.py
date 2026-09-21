"""Streamlit integration without external model calls or real credentials."""
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]

def test_app_uses_corrected_data_in_analytical_chat():
    app=AppTest.from_file(str(ROOT/'pages/3_Stage_1_Preview.py'),default_timeout=60)
    app.secrets.update(DEMO_PASSWORD='test',OPENAI_API_KEY='fake-key',OPENAI_MODEL='mock-model')
    app.run();app.text_input(key='v4_password').set_value('test').run()
    from test_commercial_v2 import NativeClient, scope, query, final
    from commercial.v2_models import FrameQuestion
    client=NativeClient([
        ('frame_question',FrameQuestion(intent='lookup',relation='new',scope=scope(entities=['Sarah'],start_date='2026-09-07',end_date='2026-09-13',category='all'),hypotheses=[])),
        ('query_data',query()),
        ('finish_answer',final(answer='Sarah recorded AUD 1,410.00 net revenue.'))])
    with patch('openai.OpenAI',return_value=client):
        app.text_input[1].set_value('What was Sarah revenue for 7 to 13 September?')
        next(b for b in app.button if b.label=='Send question').click().run()
    assert not app.exception
    result=app.session_state['v4_turns'][-1]['result']
    assert result['status']=='answered'
    assert '1,410.00' in result['display']['direct_answer']
    assert any(r['id']=='CTX1' for r in result['contexts'])
    assert app.session_state['active_analytical_state']['scope']['entities']==['Sarah']


def test_validation_page_and_checkpoint_flow():
    app=AppTest.from_file(str(ROOT/'pages/1_Data_Validation.py'),default_timeout=60)
    app.secrets['DEMO_PASSWORD']='test';app.run()
    app.text_input(key='piece1_password').set_value('test').run()
    assert not app.exception
    assert app.metric[2].value=='AUD 1,410.00'
    app.text_input(key='p1_owner').set_value('Adrian').run()
    app.selectbox(key='p1_issue').set_value('staff:B00004').run()
    app.selectbox(key='p1_choice:staff:B00004').set_value('S01').run()
    app.button(key='p1_review').click().run()
    assert len(app.session_state['p1_decisions'])==0
    app.button(key='p1_confirm').click().run()
    assert not app.exception and len(app.session_state['p1_decisions'])==1
    assert app.metric[5].value=='2'
    next(b for b in app.button if b.label=='Run validation checks').click().run()
    assert any('All 9' in r.value for r in app.success)

def test_evidence_and_legacy_routes():
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60);app.secrets['DEMO_PASSWORD']='test';app.run()
    app.radio[0].set_value('Business evidence').run();app.text_input(key='evidence_password').set_value('test').run()
    assert not app.exception and len(app.dataframe)>=2
    app.selectbox(key='evidence_table').set_value('receivables').run()
    assert not app.exception
    app.radio[0].set_value('Legacy demo').run()
    assert not app.exception
