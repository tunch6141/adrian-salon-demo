import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
from unittest.mock import patch
import pandas as pd
import app
from analyst_engine import Database,QueryBlocked,reference_value,validate_chart
from analyst_ai import Plan,Answer,Review,investigate
from business_context import ContextStore

ROOT=Path(__file__).resolve().parents[1]
class AnalystTests(unittest.TestCase):
    def setUp(self):
        self.t=app.load_data(ROOT);self.db=Database(self.t)
    def tearDown(self):self.db.close()
    def test_unprogrammed_channel_ranking(self):
        # Arbitrary date/staff/channel analysis absent from the original scenario functions.
        sql="SELECT booking_channel, SUM(service_revenue_aud) AS revenue FROM completed_visits WHERE staff_name='Sarah' AND visit_date BETWEEN '2026-06-01' AND '2026-07-31' GROUP BY booking_channel ORDER BY revenue DESC"
        result=self.db.query(sql)
        a=self.t['appointments'];mask=a.staff_name.eq('Sarah')&a.status.eq('completed')&a.appointment_start.ge('2026-06-01')&a.appointment_start.lt('2026-08-01')
        expected=a[mask].groupby('booking_channel').service_revenue_aud.sum().sort_values(ascending=False)
        self.assertEqual(result['rows'],[{'booking_channel':k,'revenue':v} for k,v in expected.items()])
    def test_scenario_reconciliation(self):
        rows=self.db.query("SELECT staff_name,SUM(service_revenue_aud) AS revenue,SUM(shampoo_revenue) AS retail,SUM(hours) AS hours FROM completed_visits WHERE visit_date BETWEEN '2026-09-07' AND '2026-09-13' GROUP BY staff_name")['rows']
        sarah=next(r for r in rows if r['staff_name']=='Sarah')
        self.assertEqual(sarah,dict(staff_name='Sarah',revenue=3800,retail=35,hours=38))
        self.assertEqual(sum(r['revenue'] for r in rows),9125)
    def test_capacity_denominator(self):
        r=self.db.query("SELECT SUM(bookable_hours) AS capacity,SUM(completed_hours) AS completed FROM staff_daily WHERE visit_date BETWEEN '2026-09-07' AND '2026-09-13'")['rows'][0]
        self.assertEqual(r,dict(capacity=114,completed=91.25))
    def test_read_only_and_invalid_queries(self):
        attacks=["DELETE FROM completed_visits","SELECT 999 AS revenue","SELECT * FROM sqlite_master","SELECT * FROM completed_visits; DROP TABLE completed_visits", "SELECT a.staff_name FROM completed_visits a JOIN completed_visits b ON 1=1", "SELECT load_extension(staff_name) FROM completed_visits", "ATTACH DATABASE '/tmp/leak.db' AS leak", "SELECT staff_name FROM completed_visits UNION SELECT 'invented'", "SELECT staff_name FROM completed_visits"]
        for sql in attacks:
            with self.subTest(sql=sql),self.assertRaises(Exception):self.db.query(sql)
    def test_missing_staff(self):
        self.assertEqual(self.db.query("SELECT staff_name FROM completed_visits WHERE staff_name='Jacintha'")['rows'],[])
    def test_context_period_and_retraction(self):
        store=ContextStore(session_rows=[])
        row=store.save(dict(entity='Sarah',start_date='2026-06-01',end_date='2026-06-03',event_type='Leave',explanation='Owner reports annual leave'),'Adrian')
        self.assertEqual(len(store.search('Sarah','2026-06-01','2026-08-31')),1)
        self.assertEqual(store.search('Matthew','2026-06-01','2026-08-31'),[])
        self.assertEqual(store.search('Sarah','2026-07-01','2026-08-31'),[])
        store.retract(row['id']);self.assertEqual(store.search(),[])
    def test_persistence_error_not_success(self):
        store=ContextStore('https://example.supabase.co','test')
        with patch('business_context.requests.request',side_effect=TimeoutError),self.assertRaises(TimeoutError):store.search()
    def test_chart_uses_result(self):
        r=[self.db.query('SELECT staff_name,SUM(service_revenue_aud) AS revenue FROM completed_visits GROUP BY staff_name')]
        validate_chart(r,dict(kind='bar',result=0,x='staff_name',y='revenue'))
        with self.assertRaises(QueryBlocked):validate_chart(r,dict(kind='bar',result=0,x='staff_name',y='invented'))
    def test_evidence_reference(self):
        with self.assertRaises(QueryBlocked):reference_value([],dict(result=0,row=0,column='revenue'))
    def test_reviewer_withholds_wrong_claim(self):
        p=Plan(intent='lookup',scope='Sarah',missing_information='',queries=["SELECT SUM(service_revenue_aud) AS revenue FROM completed_visits WHERE staff_name='Sarah'"],context_entity='Sarah',context_start='',context_end='',draft=None)
        a=Answer(claims=[dict(text='Invented claim',evidence=[dict(result=0,row=0,column='revenue')],context_ids=[])],investigation='',recommendation='',measurement='',missing_information='',chart=dict(kind='none',result=0,x='',y=''))
        with patch('analyst_ai.structured',side_effect=[p,a,Review(approved=False,issues=['Not supported']),p,a,Review(approved=False,issues=['Not supported'])]):
            result=investigate(None,'test',self.db,'Sarah revenue?',[],ContextStore())
        self.assertEqual(result['status'],'facts_only');self.assertIsNone(result['answer'])
    def test_context_draft_does_not_save(self):
        p=Plan(intent='context',scope='Sarah leave',missing_information='',queries=[],context_entity='Sarah',context_start='',context_end='',draft=dict(entity='Sarah',start_date='',end_date='',event_type='leave',explanation='Owner reports leave'))
        store=ContextStore()
        with patch('analyst_ai.structured',return_value=p):result=investigate(None,'test',self.db,'She was on leave',[],store)
        self.assertEqual(result['status'],'context');self.assertEqual(store.rows,[])
if __name__=='__main__':unittest.main()
