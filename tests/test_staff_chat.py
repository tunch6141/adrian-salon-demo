from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
import pytest
from analytics.persistence import PipelineStore, raw_payload, checkpoint
from piece1_validation.adapter import Intake
from piece1_validation.clarification import questions, proposed, staff_reply
from piece1_validation.review_ui import show_rows, explain_question
from test_persistence import record

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'piece1_validation/sample_raw'


@pytest.mark.parametrize('text',['Sarah','S Wong is Sarah','s wong means sarah','S01'])
def test_explicit_staff_reply_uses_offered_id(text):
    q=next(q for q in questions(Intake(RAW)) if q['kind']=='staff')
    assert staff_reply(q,text)=={'intent':'answer','value':'S01'}
    assert proposed(q,' Sarah ',text)['value']=='S01'


@pytest.mark.parametrize('text',['Maybe Sarah','Not Sarah','Sarah or Sam','Is it Sarah?'])
def test_staff_reply_does_not_guess(text):
    q=next(q for q in questions(Intake(RAW)) if q['kind']=='staff')
    assert staff_reply(q,text)['intent']=='clarify'


def test_details_question_and_chronological_columns():
    q=next(q for q in questions(Intake(RAW)) if q['kind']=='staff')
    assert 'booking details' in explain_question(q,'is there any other details with S Wong?')
    with patch('piece1_validation.review_ui.st.dataframe') as display:
        show_rows([dict(appointment_end='end',status='Completed',appointment_start='start')],ZoneInfo('Australia/Melbourne'))
    keys=list(display.call_args.args[0][0])
    assert keys.index('Appointment End')==keys.index('Appointment Start')+1


@pytest.mark.parametrize('reply',['Sarah','S Wong is Sarah'])
def test_chat_reply_review_save_and_fresh_session(reply):
    from streamlit.testing.v1 import AppTest
    store=PipelineStore('https://example.supabase.co','test')
    saved=[record(raw_payload(RAW),checkpoint({}))]
    original=deepcopy(saved[0]['raw'])
    events=[]
    def publish(raw,cp,expected,actor,kind,event):
        assert expected==saved[0]['version_id']
        saved[0]=record(raw,cp)
        events.append(dict(actor=actor,kind=kind,checkpoint=deepcopy(cp)))
        return deepcopy(saved[0])
    with patch('analytics.persistence.store_for',return_value=store),patch('piece1_validation.pipeline_ui.store_for',return_value=store),patch.object(store,'current',side_effect=lambda:deepcopy(saved[0])),patch.object(store,'publish',side_effect=publish),patch.object(store,'history',return_value=[]),patch('piece1_validation.chat_ui.ai_extract',side_effect=AssertionError('An explicit known name must not require AI')):
        app=AppTest.from_file(str(ROOT/'pages/1_Data_Validation.py'),default_timeout=60)
        app.secrets.update(DEMO_PASSWORD='test',OPENAI_API_KEY='test',OPENAI_MODEL='gpt-4.1-mini')
        app.run();app.text_input(key='piece1_password').set_value('test').run()
        app.text_input(key='p1_owner').set_value('Chat acceptance tester').run()
        app.chat_input(key='p1_chat_input').set_value('is there any other details with S Wong?').run()
        assert not app.exception and not app.session_state['p1_pending']
        app.chat_input(key='p1_chat_input').set_value(reply).run()
        assert not app.exception and app.session_state['p1_pending']['draft']['value']=='S01'
        assert events==[]
        app.button(key='p1_confirm').click().run()
        assert not app.exception and len(events)==1
        assert events[0]['actor']=='Chat acceptance tester'
        assert events[0]['checkpoint']['decisions'][0]['value']=='S01'
        assert saved[0]['raw']==original
        assert next(r for r in saved[0]['snapshot']['tables']['bookings'] if r['booking_id']=='B00004')['staff_id']=='S01'
        other=AppTest.from_file(str(ROOT/'pages/1_Data_Validation.py'),default_timeout=60)
        other.secrets['DEMO_PASSWORD']='test';other.run()
        other.text_input(key='piece1_password').set_value('test').run()
        assert not other.exception
        assert 'Who is S Wong?' not in other.selectbox(key='p1_issue').options
