from pathlib import Path
from unittest.mock import patch
import unittest,json
from piece1_validation.adapter import Intake
from piece1_validation.clarification import questions,proposed,decision,context_note,validate_checkpoint
from piece1_validation.metrics import revenue
RAW=Path(__file__).resolve().parents[1]/'piece1_validation/sample_raw'
class ClarificationTests(unittest.TestCase):
    def setUp(self):self.i=Intake(RAW);self.q={q['kind']:q for q in questions(self.i)}
    def make(self,kind,value,text):return decision(proposed(self.q[kind],value,text),'Test owner')
    def test_draft_does_not_modify(self):
        proposed(self.q['staff'],'S01','S Wong is Sarah');self.assertEqual(len(self.i.issues),3)
    def test_staff_confirmation(self):
        d=self.make('staff','S01','S Wong is Sarah');j=Intake(RAW,[d]);self.assertEqual(len(j.issues),2);self.assertEqual(j.tables['bookings'][3]['staff_id'],'S01')
        self.assertTrue(any(a['action']=='owner_approved' for a in j.audit))
    def test_cost_confirmation_scoped(self):
        d=self.make('cost','35','The unit cost is 35 ex GST');j=Intake(RAW,[d]);self.assertEqual(j.tables['inventory_items'][3]['unit_cost'],'35');self.assertEqual(len(j.issues),2)
    def test_unstated_value_rejected(self):
        with self.assertRaises(ValueError):proposed(self.q['cost'],'35','I do not know')
        with self.assertRaises(ValueError):proposed(self.q['staff'],'S02','Sarah')
    def test_partial_name_is_not_evidence(self):
        with self.assertRaises(ValueError):proposed(self.q['staff'],'S03','The same person')
    def test_unknown_staff_rejected(self):
        with self.assertRaises(ValueError):proposed(self.q['staff'],'S99','S99')
    def test_invalid_cost_rejected(self):
        for value,text in [('NaN','NaN'),('-1','-1'),('35.555','35.555'),('35','35 inc GST')]:
            with self.assertRaises(ValueError):proposed(self.q['cost'],value,text)
    def test_customer_choice_does_not_merge_existing(self):
        d=self.make('identity','C0001','This is C0001');j=Intake(RAW,[d]);self.assertEqual(j.identity[-1]['customer_id'],'C0001');self.assertEqual(len(j.issues),2)
        old={c['customer_id']:c for c in self.i.tables['customers']};new={c['customer_id']:c for c in j.tables['customers']}
        self.assertEqual(old['C0001'],new['C0001']);self.assertEqual(old['C0002'],new['C0002'])
    def test_separate_customer_choice(self):
        d=self.make('identity','new_identity','Keep as a separate customer');j=Intake(RAW,[d]);self.assertEqual(len(j.tables['customers']),182)
    def test_export_restore_preserves_effects(self):
        ds=[self.make('staff','S01','Sarah'),self.make('cost','35','35'),self.make('identity','C0001','C0001')]
        notes=[context_note('Sarah was on leave.','Sarah','2026-09-08','2026-09-09','Owner')]
        accepted,restored=validate_checkpoint(json.loads(json.dumps({'format':'piece1_owner_review_v1','decisions':ds,'context':notes})),RAW)
        j=Intake(RAW,accepted);self.assertEqual(len(j.issues),0);self.assertEqual(restored,notes)
        self.assertEqual(revenue(j,'2026-09-07','2026-09-14','S01')['net_revenue'],'1410.00')
    def test_restore_rejects_arbitrary_fields(self):
        d=self.make('staff','S01','Sarah');d['field']='net_amount_ex_gst'
        with self.assertRaises(ValueError):validate_checkpoint({'format':'piece1_owner_review_v1','decisions':[d]},RAW)
    def test_context_verbatim_not_causality(self):
        n=context_note('Sarah took leave, which I think affected sales.','Sarah','2026-09-08','2026-09-09','Owner')
        self.assertFalse(n['causality_verified']);self.assertEqual(n['source_type'],'owner_reported')
        with self.assertRaises(ValueError):context_note('Leave','Sarah','2026-09-09','2026-09-08','Owner')
if __name__=='__main__':unittest.main()
