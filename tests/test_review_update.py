import unittest,json
from pathlib import Path
from piece1_validation.adapter import Intake
from piece1_validation.clarification import questions,stock_reply,proposed,decision,context_note,validate_checkpoint
from piece1_validation.amendments import sale_record,validate_sales,apply_sales,money_request
from piece1_validation.change_view import changes
from piece1_validation.metrics import revenue
RAW=Path(__file__).resolve().parents[1]/'piece1_validation/sample_raw'
class ReviewTests(unittest.TestCase):
    def setUp(self):self.i=Intake(RAW);self.q=next(q for q in questions(self.i) if q['kind']=='cost')
    def sale(self,amount='500',tax='AUD excluding GST',reference='CASH-SARAH-1609'):
        return sale_record('S01','2026-09-16',amount,tax,'service','Unrecorded service',reference,'Adrian','Sarah made AUD500 cash on 16/9/2026, forgot to record it.')
    def test_item_name_shown(self):self.assertIn('Specialist colour kit',self.q['question'])
    def test_aud_attached_and_tentative_reply(self):
        text="i think it's AUD500";r=stock_reply(self.q,text);d=proposed(self.q,r['value'],text);self.assertEqual(d['value'],'500');self.assertEqual(len(self.i.issues),3)
    def test_wrong_product_explained(self):
        for text in ['Colour shampoo, i dont have the ID','colour shampoo, ID 12345','colour shampoo/12345']:
            r=stock_reply(self.q,text);self.assertEqual(r['intent'],'clarify');self.assertIn('P01',r['message']);self.assertIn('P04',r['message'])
    def test_unknown_id_not_cost(self):self.assertEqual(stock_reply(self.q,'ID12345')['intent'],'clarify')
    def test_pack_price_and_negative_not_cost(self):
        for text in ['500 for a box','selling price AUD500','-500','minus AUD500']:
            self.assertEqual(stock_reply(self.q,text)['intent'],'clarify')
    def test_cost_change_visible(self):
        d=decision(proposed(self.q,'500','AUD500'),'Adrian');j=Intake(RAW,[d]);diff=changes(self.i,j)
        row=next(r for r in diff if r['Table']=='inventory_items' and r['Field']=='unit_cost');self.assertIsNone(row['Before']);self.assertEqual(row['After'],'500')
    def test_identity_link_visible(self):
        q=next(q for q in questions(self.i) if q['kind']=='identity');j=Intake(RAW,[decision(proposed(q,'C0001','C0001'),'Adrian')])
        self.assertTrue(any(r['Table']=='customer_identity_links' and r['After']=='C0001' for r in changes(self.i,j)))
    def test_cash_correction_is_not_context(self):
        self.assertTrue(money_request('Sarah actually made AUD 500 revenue on cash on 16/9/2026 which forgot to update in the system, could you please update that?'))
        self.assertFalse(money_request('Sarah was on annual leave visiting family.'))
    def test_correct_period_and_idempotence(self):
        old=revenue(self.i,'2026-09-16','2026-09-17','S01');s=self.sale();j=apply_sales(self.i,[s]);new=revenue(j,'2026-09-16','2026-09-17','S01')
        self.assertEqual(float(new['net_revenue'])-float(old['net_revenue']),500)
        self.assertEqual(revenue(j,'2026-09-07','2026-09-14','S01')['net_revenue'],'1410.00');self.assertIsNone(new['gross_profit'])
        again=apply_sales(j,[s]);self.assertEqual(revenue(again,'2026-09-16','2026-09-17','S01')['net_revenue'],new['net_revenue'])
    def test_same_id_changed_amount_blocked(self):
        s=self.sale();j=apply_sales(self.i,[s]);altered=dict(s,entered_amount='600')
        with self.assertRaises(ValueError):apply_sales(j,[altered])
    def test_duplicate_reference_blocked(self):
        with self.assertRaises(ValueError):validate_sales([self.sale(),self.sale()])
    def test_tax_requires_choice_and_inclusive_amount(self):
        with self.assertRaises(ValueError):self.sale(tax='')
        self.assertEqual(self.sale(amount='550',tax='AUD including 10% GST')['net_amount_ex_gst'],'500.00')
    def test_restore_recomputes_tampered_amount(self):
        s=self.sale();s['net_amount_ex_gst']='999999';restored=validate_sales(json.loads(json.dumps([s])));self.assertEqual(restored[0]['net_amount_ex_gst'],'500.00')
    def test_business_context_does_not_affect_revenue(self):
        n=context_note('Sarah was on leave.','Sarah','2026-09-08','2026-09-09','Owner');self.assertFalse(n['causality_verified']);self.assertEqual(revenue(self.i,'2026-09-07','2026-09-14','S01')['net_revenue'],'1410.00')
if __name__=='__main__':unittest.main()
