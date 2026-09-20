import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
from unittest.mock import patch
import app
from analyst_engine import Database
from analyst_ai import Plan,Answer,Review,investigate
from business_context import ContextStore

class DynamicTests(unittest.TestCase):
    def setUp(self):
        self.db=Database(app.load_data(Path(__file__).resolve().parents[1]))
        self.p=Plan(intent='analysis',scope='Sarah June and July channel revenue',missing_information='',queries=["SELECT SUM(service_revenue_aud) AS revenue FROM completed_visits WHERE staff_name='Sarah' AND visit_date BETWEEN '2026-06-01' AND '2026-07-31'"],context_entity='Sarah',context_start='2026-06-01',context_end='2026-07-31',draft=None)
    def tearDown(self):self.db.close()
    def answer(self,**kwargs):
        return Answer(**dict(dict(claims=[],investigation='',recommendation='',measurement='',missing_information='',chart=dict(kind='none',result=0,x='',y='')),**kwargs))
    def test_new_question_drilldown_and_chart(self):
        drill=self.answer(additional_queries=["SELECT booking_channel,SUM(service_revenue_aud) AS revenue FROM completed_visits WHERE staff_name='Sarah' AND visit_date BETWEEN '2026-06-01' AND '2026-07-31' GROUP BY booking_channel ORDER BY revenue DESC"])
        a=self.answer(claims=[dict(text='Phone bookings contributed [[0]] of Sarah’s service revenue.',evidence=[dict(result=1,row=0,column='revenue',format='money')],context_ids=[])],chart=dict(kind='bar',result=1,x='booking_channel',y='revenue'))
        with patch('analyst_ai.structured',side_effect=[self.p,drill,a,Review(approved=True,issues=[])]):
            r=investigate(None,'test',self.db,'Which booking channel contributed most to Sarah sales?',[],ContextStore())
        self.assertEqual(r['status'],'answered')
        self.assertIn('11,095.00',r['answer']['claims'][0]['text'])
        self.assertEqual(len(r['results']),2)
        self.assertEqual(r['answer']['chart']['kind'],'bar')
    def test_reviewer_corrects_instead_of_suppressing_everything(self):
        draft=self.answer(claims=[dict(text='Sarah is lazy.',evidence=[dict(result=0,row=0,column='revenue')],context_ids=[])])
        corrected=self.answer(claims=[dict(text='Sarah recorded [[0]] service revenue. These records do not establish employee effort.',evidence=[dict(result=0,row=0,column='revenue',format='money')],context_ids=[])])
        with patch('analyst_ai.structured',side_effect=[self.p,draft,Review(approved=True,issues=['Removed unsupported judgement'],revised_answer=corrected)]) as calls:r=investigate(None,'test',self.db,'How did Sarah do?',[],ContextStore())
        self.assertEqual(calls.call_args.args[-1]['answer'],draft.model_dump())
        self.assertEqual(r['status'],'answered')
        self.assertNotIn('lazy',str(r['answer']))
        self.assertIn('25,300.00',r['answer']['claims'][0]['text'])
    def test_revised_answer_cannot_invent_numbers(self):
        a=self.answer(claims=[dict(text='Revenue [[0]].',evidence=[dict(result=0,row=0,column='revenue')],context_ids=[])])
        bad=a.model_copy(deep=True);bad.claims[0].text='Revenue was 999999.'
        with patch('analyst_ai.structured',side_effect=[self.p,a,Review(approved=True,issues=[],revised_answer=bad)]) as calls:r=investigate(None,'test',self.db,'Revenue?',[],ContextStore())
        self.assertIn('[[0]]',calls.call_args.args[-1]['answer']['claims'][0]['text'])
        self.assertNotIn('[[0]]',calls.call_args.args[-1]['rendered_answer']['claims'][0]['text'])
        self.assertEqual(r['status'],'facts_only')
    def test_query_loop_bounded(self):
        a=self.answer(additional_queries=self.p.queries)
        with patch('analyst_ai.structured',side_effect=[self.p,a,a,a]) as call:r=investigate(None,'test',self.db,'Investigate',[],ContextStore())
        self.assertEqual(call.call_count,4)
        self.assertEqual(r['status'],'facts_only')
        self.assertEqual(len(r['results']),3)
