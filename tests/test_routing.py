import json
import unittest
from epistemic_harness.pipeline import run_case


class Client:
    def __init__(self,replies=(),completion='off'):
        self.replies=iter(replies);self.calls=[]
        self.config={'verification_protocol':'evidence_map','rewrite_mode':'deterministic',
                     'task_completion':completion,'completion_protocol':'requirements'}
    def complete(self,*args,**kwargs):
        self.calls.append((args,kwargs))
        return next(self.replies)


class RoutingTests(unittest.TestCase):
    def case(self,check=True):
        c={'id':'t','question':'Compute 18 * 7 with working.','expected_answer':'18 * 7 = 126.',
           'requirements':['result','working'],'evidence_strength':'weak','allowed_certainty':'certain',
           'accepted_claims':[],'rejected_claims':[],'verification_method':'fixture'}
        if check: c['check']={'type':'arithmetic_derivation','expression':'18 * 7'}
        return c

    def run_answer(self,case,text,client,spans=None):
        replay={'case_id':case['id'],'question':case['question'],'candidate':text,
                'claims':[{'text':s} for s in (spans or [text])]}
        return run_case(case,client,'stage2',replay=replay)

    def test_arithmetic_proof_uses_no_factual_model_call(self):
        client=Client();r=self.run_answer(self.case(),'18 * 7 = 70 + 56 = 126',client)
        self.assertEqual(client.calls,[])
        self.assertEqual(r['verification_route'],'checked_arithmetic')
        self.assertEqual(r['rewrite_plan'][0]['certainty'],'tentative')
        self.assertTrue(r['audit']['passed'])

    def test_invalid_arithmetic_never_falls_back_to_remote(self):
        for check in (None,{'type':'other'}, {'type':'arithmetic_derivation','expression':'18 * 7'}):
            case=self.case();case['check']=check;client=Client()
            r=self.run_answer(case,'18 * 7 = 127',client)
            self.assertEqual(client.calls,[])
            self.assertEqual(r['rewrite_plan'],[])
            self.assertTrue(r['audit']['passed'])

    def test_fragmentation_cannot_hide_extra_claims(self):
        text='18 * 7 = 126. Guaranteed safe.';client=Client()
        r=self.run_answer(self.case(),text,client,['18 * 7 = 126.','Guaranteed safe.'])
        self.assertEqual(len(r['extracted_claims']),2)
        self.assertEqual(len(r['claims']),1)
        self.assertEqual(r['rewrite_plan'],[])
        self.assertEqual(client.calls,[])

    def test_non_arithmetic_uses_model_evidence_and_keeps_weak_cap(self):
        text='It is unverified.';case=self.case(False);case['expected_answer']=text
        reply={'score':1,'parts':[{'text':text,'status':'supported','evidence_quote':text,'reason':'Reference agrees'}]}
        client=Client([json.dumps(reply)]);r=self.run_answer(case,text,client)
        self.assertEqual(r['verification_route'],'reference_model')
        self.assertEqual(len(client.calls),1)
        self.assertEqual(r['rewrite_plan'][0]['certainty'],'tentative')

    def test_checked_proof_still_needs_completion_gate(self):
        checks={'checks':[{'requirement_id':'r1','status':'met','evidence':'126','reason':'Result'},
                         {'requirement_id':'r2','status':'missing','evidence':'','reason':'Working omitted'}]}
        client=Client([json.dumps(checks)],'require')
        r=self.run_answer(self.case(),'18 * 7 = 126',client)
        self.assertEqual(len(client.calls),1)
        self.assertEqual(r['decisions'][0]['verification']['status'],'supported')
        self.assertEqual(r['rewrite_plan'],[])
        self.assertTrue(r['completion_withheld'])
        self.assertTrue(r['audit']['passed'])

    def test_stage2_demo_remains_offline(self):
        c=self.case(False);c['demo_candidate']='126';c['accepted_claims']=['126'];client=Client()
        r=run_case(c,client,'stage2',demo=True)
        self.assertEqual(client.calls,[])
        self.assertTrue(r['audit']['passed'])

if __name__=='__main__': unittest.main()
