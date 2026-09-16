import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from streamlit.testing.v1 import AppTest
from unittest.mock import patch
import app
from analyst_engine import Database
at=AppTest.from_file(str(ROOT/'app.py'));at.secrets.update(OPENAI_API_KEY='test',OPENAI_MODEL='gpt-4.1-mini',DEMO_PASSWORD='testing')
at.run(timeout=30)
assert not at.exception
at.text_input(key='v4_password').set_value('testing').run()
assert not at.exception
result={'status':'answered','plan':{'scope':'Sarah June revenue','intent':'lookup'},'answer':{'claims':[{'text':'Test-only answer','evidence':[],'context_ids':[]}],'chart':{'kind':'bar','result':0,'x':'staff_name','y':'revenue'},'investigation':'','recommendation':'','measurement':'','missing_information':''},'results':[{'table':'completed_visits','row_count':1,'rows':[{'staff_name':'Sarah','revenue':10}],'sql':'SELECT ...'}],'contexts':[]}
with patch('openai.OpenAI'), patch('analyst_ui.investigate',return_value=result) as call:
    for q in ['June revenue?','What about July?']:
        at.run()
        next(x for x in at.text_input if x.label=='Your question or follow-up').set_value(q)
        next(x for x in at.button if x.label=='Send question').click().run(timeout=30)
        assert not at.exception,at.exception
    assert call.call_count==2
    assert len(call.call_args.args[4])==1
# Details still render.
at.radio[0].set_value('Detailed insights').run(timeout=30)
assert not at.exception,at.exception
print('PASS: password, two typed turns, context propagation, dynamic chart rendering, legacy views (AI mocked).')
