import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
from unittest.mock import MagicMock,patch
import app
from analyst_engine import Database,bind_claim_values,period_diagnostic,QueryBlocked
from analyst_ai import investigate,structured,Plan
from business_context import ContextStore
class BoundValueTests(unittest.TestCase):
    def test_insert_values_and_rounding(self):
        r=[{'rows':[{'revenue':13075,'change':8.913,'nil':None}]}]
        c={'text':'Revenue was [[0]]; change was [[1]].','evidence':[{'result':0,'row':0,'column':'revenue','format':'money'},{'result':0,'row':0,'column':'change','format':'percent'}]}
        self.assertEqual(bind_claim_values(r,c,['','']),'Revenue was AUD 13,075.00; change was 8.91%.')
        c['text']='Revenue was 13,575.'
        with self.assertRaises(QueryBlocked):bind_claim_values(r,c,['',''])
    def test_months_not_combined(self):
        db=Database(app.load_data(Path(__file__).resolve().parents[1]))
        r=period_diagnostic(db,['Sam'],'2026-08-01','2026-08-31','2026-07-01','2026-07-31')
        self.assertEqual(r[0]['rows'][0]['service_revenue_aud'],13075)
        comparison=next(x for x in r[-1]['rows'] if x['metric']=='service_revenue_aud')
        self.assertEqual(comparison['baseline_value'],12005)
        self.assertEqual(comparison['difference'],1070)
        self.assertAlmostEqual(comparison['percentage_change'],8.912952936276551)
        db.close()
    def test_weekly_baseline(self):
        db=Database(app.load_data(Path(__file__).resolve().parents[1]))
        r=period_diagnostic(db,['Sarah'],'2026-09-07','2026-09-13','2026-08-10','2026-09-06',4)
        row=next(x for x in r[-1]['rows'] if x['metric']=='service_revenue_aud')
        self.assertEqual(row['current_value'],3800)
        self.assertEqual(row['baseline_value'],3800)
        self.assertEqual(row['difference'],0)
        db.close()
    def test_explain_failure_without_api(self):
        history=[{'status':'facts_only','plan':{'scope':'Sam'}}]
        with patch('analyst_ai.structured') as call:r=investigate(None,'test',None,'what do you mean?',history,ContextStore())
        call.assert_not_called()
        self.assertEqual(r['status'],'explanation')
    def test_terra_low_reasoning(self):
        client=MagicMock();client.responses.parse.return_value.output_parsed='parsed'
        structured(client,'gpt-5.6-terra',Plan,'test',{})
        self.assertEqual(client.responses.parse.call_args.kwargs['reasoning'],{'effort':'low'})
        structured(client,'gpt-4.1-mini',Plan,'test',{})
        self.assertNotIn('reasoning',client.responses.parse.call_args.kwargs)
