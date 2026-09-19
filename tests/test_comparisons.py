import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
from unittest.mock import patch
import pandas as pd
import app
from analyst_engine import Database,service_diagnostic,validate_claim_numbers,validate_chart,QueryBlocked
from analyst_ai import Plan,Answer,Review,investigate
from analyst_ui import build_chart
from business_context import ContextStore

ROOT=Path(__file__).resolve().parents[1]
class ComparisonTests(unittest.TestCase):
    def setUp(self):self.db=Database(app.load_data(ROOT))
    def tearDown(self):self.db.close()
    def test_august_totals_and_breakdown(self):
        r=service_diagnostic(self.db,['Matthew','Sam'],'2026-08-01','2026-08-31')
        rows={x['staff_name']:x for x in r[0]['rows']}
        self.assertEqual(rows['Matthew']['service_revenue_aud'],13165)
        self.assertEqual(rows['Sam']['service_revenue_aud'],13075)
        self.assertEqual(rows['Matthew']['completed_service_hours'],112.5)
        self.assertEqual(rows['Sam']['completed_service_hours'],111.5)
        self.assertEqual(r[2]['rows'][0]['revenue_difference_aud'],90)
        self.assertEqual(sum(x['left_minus_right_revenue_aud'] for x in r[3]['rows']),90)
        self.assertGreater(rows['Sam']['revenue_per_service_hour'],rows['Matthew']['revenue_per_service_hour'])
    def test_hallucinated_total_rejected(self):
        r=service_diagnostic(self.db,['Sam'],'2026-08-01','2026-08-31')
        claim={'text':'Sam earned AUD 13,575.','evidence':[{'result':0,'row':0,'column':'service_revenue_aud'}]}
        with self.assertRaises(QueryBlocked):validate_claim_numbers(r,claim,[],['2026-08-01','2026-08-31'])
        claim['text']='Sam earned AUD 13,075.'
        validate_claim_numbers(r,claim,[],['2026-08-01','2026-08-31'])
    def test_repeated_dates_require_series(self):
        r=[{'rows':[{'date':'2026-08-01','staff':'Sam','revenue':10},{'date':'2026-08-01','staff':'Matthew','revenue':20}]}]
        chart={'kind':'line','result':0,'x':'date','y':'revenue','series':''}
        with self.assertRaises(QueryBlocked):validate_chart(r,chart)
        chart['series']='staff';validate_chart(r,chart)
        spec=build_chart(pd.DataFrame(r[0]['rows']),chart).to_dict()
        self.assertEqual(spec['encoding']['color']['field'],'staff')
        chart['kind']='bar';spec=build_chart(pd.DataFrame(r[0]['rows']),chart).to_dict()
        self.assertEqual(spec['encoding']['xOffset']['field'],'staff')
    def test_false_refusal_replans(self):
        unsupported=Plan(intent='unsupported',scope='August staff comparison',missing_information='No causes',queries=[],context_entity='',context_start='2026-08-01',context_end='2026-08-31',draft=None)
        plan=unsupported.model_copy(update={'intent':'followup','diagnostic':None,'queries':["SELECT staff_name,SUM(service_revenue_aud) AS revenue FROM completed_visits WHERE staff_name='Sam' AND visit_date BETWEEN '2026-08-01' AND '2026-08-31' GROUP BY staff_name"]})
        a=Answer(claims=[{'text':'Sam earned AUD [[0]].','evidence':[{'result':0,'row':0,'column':'revenue'}],'context_ids':[]}],investigation='',recommendation='',measurement='',missing_information='',chart={'kind':'none','result':0,'x':'','y':'','series':''})
        with patch('analyst_ai.structured',side_effect=[unsupported,plan,a,Review(approved=True,issues=[])]):r=investigate(None,'test',self.db,'Why is that?',[],ContextStore())
        self.assertEqual(r['status'],'answered')
    def test_unknown_illness_stays_unsupported(self):
        p=Plan(intent='unsupported',scope='Illness',missing_information='No illness records',queries=[],context_entity='',context_start='',context_end='',draft=None)
        with patch('analyst_ai.structured',side_effect=[p,p]):r=investigate(None,'test',self.db,'Was he sick?',[],ContextStore())
        self.assertEqual(r['status'],'unsupported')
