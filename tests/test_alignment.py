import json
import unittest
from epistemic_harness.alignment import apply_alignment, DIMENSIONS
from epistemic_harness.evidence import evidence_verdict
from epistemic_harness.pipeline import run_case

CASE = {'id':'t','question':'State the instrument reading.','expected_answer':'The instrument reading is unavailable.',
        'evidence_strength':'strong','allowed_certainty':'certain','verification_method':'reference',
        'requirements':['unavailable reading'],'accepted_claims':[],'rejected_claims':[]}
TEXT = CASE['expected_answer']

def mapping(status='supported'):
    return {'score':1,'parts':[{'text':TEXT,'status':status,'evidence_quote':TEXT,'reason':'Reference'}]}

def alignment(status='entailed'):
    return {'checks':[{'part_id':'p1','status':status,**{k:'preserved' for k in DIMENSIONS},
                      'evidence_quote':TEXT,'counterexample':'','reason':'Same assertion'}]}

class Client:
    def __init__(self,replies):
        self.replies=iter(replies);self.calls=[]
        self.config={'verification_protocol':'evidence_alignment','rewrite_mode':'deterministic','task_completion':'off'}
    def complete(self,*args,**kwargs):
        self.calls.append((args,kwargs));return json.dumps(next(self.replies))

class AlignmentTests(unittest.TestCase):
    def verdict(self,status='supported'):
        return evidence_verdict(mapping(status),TEXT,CASE)
    def test_agreement_keeps_weak_cap(self):
        v=apply_alignment(self.verdict(),alignment(),TEXT)
        self.assertEqual((v.status,v.evidence_strength,v.score),('supported','weak',1))
    def test_each_unresolved_or_changed_dimension_withholds(self):
        for dimension in DIMENSIONS:
            for value in ['changed','unresolved']:
                data=alignment();data['checks'][0][dimension]=value
                v=apply_alignment(self.verdict(),data,TEXT)
                self.assertEqual((v.status,v.evidence_strength,v.score),('unknown','none',0))
    def test_counterexample_blocks_support(self):
        d=alignment();d['checks'][0]['counterexample']='Extra observation may be absent.'
        self.assertEqual(apply_alignment(self.verdict(),d,TEXT).status,'unknown')
    def test_empty_or_fabricated_reference_quote_blocks_support(self):
        for quote in ['', 'A fabricated reference.']:
            d=alignment();d['checks'][0]['evidence_quote']=quote
            self.assertEqual(apply_alignment(self.verdict(),d,TEXT).status,'unknown')
    def test_second_pass_cannot_upgrade_unknown_or_conflict(self):
        for status in ['unknown','contradicted']:
            self.assertEqual(apply_alignment(self.verdict(status),alignment(),TEXT).status,'unknown')
    def test_conflict_needs_both_reviewers_and_provenance(self):
        self.assertEqual(apply_alignment(self.verdict('contradicted'),alignment('conflict'),TEXT).status,'contradicted')
        self.assertEqual(apply_alignment(self.verdict(),alignment('conflict'),TEXT).status,'unknown')
        d=alignment('conflict');d['checks'][0]['evidence_quote']='fabricated'
        self.assertEqual(apply_alignment(self.verdict('contradicted'),d,TEXT).status,'unknown')
    def test_duplicate_missing_unknown_ids_fail_closed(self):
        for checks in [[],alignment()['checks']*2,[dict(alignment()['checks'][0],part_id='p2')]]:
            with self.assertRaises(ValueError):apply_alignment(self.verdict(),{'checks':checks},TEXT)
    def test_malformed_fields_rejected(self):
        for key,value in [('subject','maybe'),('status','supported'),('reason',''),('evidence_quote',None)]:
            d=alignment();d['checks'][0][key]=value
            with self.assertRaises(ValueError):apply_alignment(self.verdict(),d,TEXT)
    def test_payload_is_blind_to_first_verdict_and_gold(self):
        c=Client([mapping(),alignment()]);case=dict(CASE,gold_support='supported')
        r=self.run_answer(case,TEXT,c)
        payload=c.calls[1][0][2]
        self.assertEqual(set(payload),{'question','reference','parts'})
        self.assertEqual(payload['parts'],[{'part_id':'p1','text':TEXT}])
        self.assertTrue(r['audit']['passed']);self.assertEqual(r['rewrite_plan'][0]['certainty'],'tentative')
    def run_answer(self,case,text,c):
        return run_case(case,c,'stage2',replay={'case_id':'t','question':case['question'],'candidate':text,'claims':[{'text':text}]})
    def test_bad_second_response_withholds_entire_pipeline(self):
        r=self.run_answer(CASE,TEXT,Client([mapping(),{'checks':[]}]))
        self.assertEqual(r['status'],'error');self.assertEqual(r['rewrite_plan'],[])
    def test_declared_arithmetic_does_not_call_alignment(self):
        c=Client([]);case=dict(CASE,check={'type':'arithmetic_derivation','expression':'18 * 7'})
        r=self.run_answer(case,'18 * 7 = 70 + 56 = 126',c)
        self.assertEqual(c.calls,[]);self.assertEqual(r['verification_route'],'checked_arithmetic')
        self.assertEqual(r['rewrite_plan'][0]['certainty'],'certain')
    def test_reviewed_alias_cannot_bypass_model_alignment(self):
        case=dict(CASE,accepted_claims=[TEXT]);c=Client([mapping(),alignment('unresolved')])
        r=self.run_answer(case,TEXT,c)
        self.assertEqual(len(c.calls),2);self.assertEqual(r['rewrite_plan'],[])

if __name__=='__main__':unittest.main()
