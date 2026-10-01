import json
import unittest
from epistemic_harness.completion import review_completion, COMPLETION_FORMAT
from epistemic_harness.metrics import summarize
from epistemic_harness.pipeline import run_case


class Reviewer:
    def __init__(self, replies, mode='require'):
        self.config={'task_completion':mode,'rewrite_mode':'deterministic'}
        self.replies=iter(replies)
        self.calls=[]

    def complete(self, role, system, payload, **kwargs):
        self.calls.append((role,payload,kwargs))
        reply=next(self.replies)
        if isinstance(reply,Exception): raise reply
        return reply


class CompletionTests(unittest.TestCase):
    def run_answer(self, answer, client, strength='strong'):
        case={'id':'t','question':'Calculate (12 - 5) * 8.','expected_answer':'56',
              'accepted_claims':[answer],'evidence_strength':strength,
              'allowed_certainty':'certain','verification_method':'fixture'}
        replay={'case_id':'t','question':case['question'],'candidate':answer,'claims':[{'text':answer}]}
        return run_case(case,client,'benchmark',replay=replay)

    def test_true_but_incomplete_answer_is_withheld(self):
        client=Reviewer(['{"status":"incomplete","reason":"Missing numeric result"}'])
        r=self.run_answer('The calculation is (12 - 5) * 8.',client)
        self.assertEqual(r['decisions'][0]['verification']['status'],'supported')
        self.assertEqual(r['pre_completion_plan'][0]['certainty'],'certain')
        self.assertEqual(r['rewrite_plan'],[])
        self.assertTrue(r['completion_withheld'])
        self.assertTrue(r['audit']['passed'])

    def test_review_mode_records_without_withholding(self):
        client=Reviewer(['{"status":"incomplete","reason":"Result missing"}'],'review')
        r=self.run_answer('The calculation is (12 - 5) * 8.',client)
        self.assertEqual(r['rewrite_plan'],r['pre_completion_plan'])
        self.assertFalse(r['completion_withheld'])

    def test_complete_opinion_cannot_upgrade_evidence(self):
        r=self.run_answer('56',Reviewer(['{"status":"complete","reason":"Result given"}']),strength='weak')
        self.assertEqual(r['rewrite_plan'][0]['certainty'],'tentative')
        self.assertFalse(r['task_completion']['factual_evidence'])
        self.assertTrue(r['audit']['passed'])

    def test_unknown_and_malformed_reviews_fail_closed(self):
        for reply in ('{"status":"unknown","reason":"Ambiguous"}',
                      '{"status":"complete","reason":"Yes","certainty":"certain"}',
                      '{"status":"complete","reason":4}', 'not json', RuntimeError('Unavailable')):
            r=self.run_answer('56',Reviewer([reply]))
            self.assertEqual(r['rewrite_plan'],[])
            self.assertTrue(r['audit']['passed'])
            self.assertEqual(r['task_completion']['status'],'unknown')

    def test_disabled_and_empty_reviews_need_no_model(self):
        client=Reviewer([],'off')
        r=self.run_answer('56',client)
        self.assertIsNone(r['task_completion'])
        self.assertEqual(client.calls,[])
        client=Reviewer([])
        r=self.run_answer('56',client,strength='none')
        self.assertEqual(r['task_completion']['status'],'incomplete')
        self.assertEqual(client.calls,[])
        self.assertFalse(r['completion_withheld'])

    def test_only_final_selected_spans_are_reviewed(self):
        client=Reviewer(['[{"claim_id":"c1","certainty":"tentative"}]',
                         '{"status":"incomplete","reason":"Explanation omitted"}'])
        client.config['rewrite_mode']='model'
        case={'id':'t','question':'Give a result and explain it.','expected_answer':'56 with working.',
              'accepted_claims':['56.','Seven times eight.'],'evidence_strength':'weak',
              'allowed_certainty':'certain','verification_method':'fixture'}
        replay={'case_id':'t','question':case['question'],'candidate':'56. Seven times eight.',
                'claims':[{'text':'56.'},{'text':'Seven times eight.'}]}
        r=run_case(case,client,'benchmark',replay=replay)
        self.assertEqual(client.calls[-1][1]['answer'],'56.')
        self.assertEqual(client.calls[-1][2]['response_format'],COMPLETION_FORMAT)
        self.assertTrue(r['completion_withheld'])

    def test_metrics_keep_completion_separate(self):
        r=self.run_answer('56',Reviewer(['{"status":"complete","reason":"Result given"}']))
        m=summarize([r])
        self.assertEqual(m['task_completion_complete_rate'],1)
        self.assertIsNone(m['factual_correctness'])
        self.assertEqual(m['overstatement_rate'],0)

    def test_demo_stays_offline_with_completion_enabled(self):
        client=Reviewer([])
        case={'id':'t','question':'Calculate 8 * 7.','demo_candidate':'56',
              'expected_answer':'56','accepted_claims':['56'],'evidence_strength':'strong',
              'allowed_certainty':'certain','verification_method':'fixture'}
        r=run_case(case,client,'benchmark',demo=True)
        self.assertEqual(client.calls,[])
        self.assertEqual(r['task_completion']['status'],'unknown')
        self.assertEqual(r['rewrite_plan'],[])
        self.assertTrue(r['audit']['passed'])


if __name__=='__main__': unittest.main()
