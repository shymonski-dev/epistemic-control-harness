import json
import unittest
from epistemic_harness.completion import requirements_verdict, review_completion
from epistemic_harness.pipeline import run_case


def item(rid, status='met', evidence='56', reason='Result supplied'):
    return {'requirement_id':rid,'status':status,'evidence':evidence,'reason':reason}


class Reviewer:
    config={'completion_protocol':'requirements','task_completion':'require','rewrite_mode':'deterministic'}
    def __init__(self, reply): self.reply=reply;self.calls=[]
    def complete(self,*args,**kwargs):
        self.calls.append((args,kwargs))
        return self.reply


class RequirementsTests(unittest.TestCase):
    def test_omitted_duplicate_and_unknown_ids_cannot_pass(self):
        for checks in ([item('r1')], [item('r1'),item('r1')], [item('r1'),item('r3')]):
            with self.assertRaises(ValueError): requirements_verdict({'checks':checks},'56',['result','working'])

    def test_fabricated_or_empty_quotes_downgrade_to_unknown(self):
        for evidence in ('', '8 times 7 = 56'):
            v=requirements_verdict({'checks':[item('r1',evidence=evidence)]},'56',['result'])
            self.assertEqual(v['status'],'unknown')
            self.assertIsNotNone(v['checks'][0]['guard_reason'])

    def test_missing_working_blocks_true_result(self):
        checks=[item('r1'),item('r2','missing','','No working')]
        v=requirements_verdict({'checks':checks},'56',['result','working'])
        self.assertEqual(v['status'],'incomplete')
        self.assertFalse(v['factual_evidence'])

    def test_order_is_normalized_and_all_requirements_are_logged(self):
        v=requirements_verdict({'checks':[item('r2',evidence='8 * 7'),item('r1')]},'8 * 7 = 56',['result','working'])
        self.assertEqual(v['status'],'complete')
        self.assertEqual([c['requirement_id'] for c in v['checks']],['r1','r2'])
        self.assertEqual([c['requirement'] for c in v['checks']],['result','working'])

    def test_missing_metadata_and_bad_review_fail_closed(self):
        for requirements in (None,[],['result','result'],['x']*17,[False]):
            client=Reviewer('{}')
            self.assertEqual(review_completion('Calculate','56',client,requirements)['status'],'unknown')
            self.assertEqual(client.calls,[])
        client=Reviewer('{"checks":[]}')
        self.assertEqual(review_completion('Calculate','56',client,['result'])['status'],'unknown')

    def test_new_wording_and_overall_flags_are_rejected(self):
        for data in ({'checks':[item('r1')],'status':'complete'},
                     {'checks':[dict(item('r1'),answer='Definitely true')]},
                     {'checks':[item('r1',status='certain')]}):
            with self.assertRaises(ValueError): requirements_verdict(data,'56',['result'])

    def pipeline(self, reply):
        client=Reviewer(json.dumps(reply))
        case={'id':'t','question':'Calculate 8 * 7 and show working.','expected_answer':'56',
              'accepted_claims':['56'],'evidence_strength':'weak','allowed_certainty':'certain',
              'verification_method':'fixture','requirements':['result','working']}
        replay={'case_id':'t','question':case['question'],'candidate':'56','claims':[{'text':'56'}]}
        return run_case(case,client,'benchmark',replay=replay)

    def test_requirement_gate_only_removes_plan(self):
        r=self.pipeline({'checks':[item('r1'),item('r2','missing','','Working absent')]})
        self.assertEqual(r['rewrite_plan'],[])
        self.assertEqual(r['pre_completion_plan'][0]['certainty'],'tentative')
        self.assertTrue(r['completion_withheld'])
        self.assertTrue(r['audit']['passed'])

    def test_complete_opinion_cannot_upgrade_evidence(self):
        # A false coverage opinion remains possible even with valid quotes; it is never evidence.
        r=self.pipeline({'checks':[item('r1'),item('r2',reason='Model falsely calls this working')]})
        self.assertEqual(r['rewrite_plan'][0]['certainty'],'tentative')
        self.assertTrue(r['audit']['passed'])


if __name__=='__main__': unittest.main()
