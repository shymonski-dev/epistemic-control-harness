import copy
import io
import json
import math
import os
import unittest
from dataclasses import replace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request
from epistemic_harness.client import Client, EndpointError, NoRedirect, urlopen
from epistemic_harness.evidence import evidence_verdict
from epistemic_harness.jev_client import JevClient, validate_response, decode_response
from epistemic_harness.jev_verification import review_jev, CRITERIA
from epistemic_harness.pipeline import run_case

CONFIG={'verification_mode':'stage2','verification_protocol':'evidence_jev','rewrite_mode':'deterministic',
 'task_completion':'off','timeout_seconds':5,'roles':{k:{'provider':'local','model':'test'} for k in ['generator','verifier','rewriter']},
 'decision_reviewer':{'provider':'openrouter','model':'typesafe/jev-1.13','protocol':'systemone'}}
CASE={'id':'t','question':'State the reading.','expected_answer':'The reading is unavailable.',
 'evidence_strength':'strong','allowed_certainty':'certain','verification_method':'reference','accepted_claims':[],'rejected_claims':[]}
TEXT=CASE['expected_answer']

def response(choice='supported'):
 return {'model':'typesafe/jev-1.13-20260917','answers':{'p1':{'type':'choice','choice':choice,
   'probabilities':{k:1 if k==choice else 0 for k in CRITERIA},'confidence':1}},
   'usage':{'input_tokens':400,'output_tokens':40,'cost':.00002},'provider':'ignored metadata'}

def mapping(status='supported',quote=TEXT):
 return {'score':1,'parts':[{'text':TEXT,'status':status,'evidence_quote':quote,'reason':'Reference'}]}

def verdict(status='supported',quote=TEXT):
 return evidence_verdict(mapping(status,quote),TEXT,CASE)

class FakeClient(Client):
 def __init__(self,reply=None,mapreply=None):
  super().__init__(copy.deepcopy(CONFIG));self.reply=reply or response();self.mapreply=mapreply or mapping();self.calls=[]
 def complete(self,*args,**kwargs):return json.dumps(self.mapreply)
 def decide(self,state,questions):self.calls.append((state,questions));return self.reply

class JevTests(unittest.TestCase):
 def test_agreement_preserves_first_score_and_weak_cap(self):
  v=replace(verdict(),score=.6);c=FakeClient()
  r=review_jev(c,v,TEXT,CASE)
  self.assertEqual((r.status,r.score,r.evidence_strength),('supported',.6,'weak'))
  self.assertEqual(r.evidence_check['parts'][0]['initial_status'],'supported')
 def test_agreement_cannot_raise_none_strength(self):
  r=review_jev(FakeClient(),replace(verdict(),evidence_strength='none'),TEXT,CASE)
  self.assertEqual(r.evidence_strength,'none')
 def test_disagreement_becomes_unknown(self):
  for first in ['supported','contradicted','unknown']:
   for second in ['supported','contradicted','unknown']:
    r=review_jev(FakeClient(response(second)),verdict(first),TEXT,CASE)
    expected=first if first==second and first!='unknown' else 'unknown'
    self.assertEqual(r.status,expected)
    if expected!='supported':self.assertEqual((r.score,r.evidence_strength),(0,'none'))
 def test_missing_quote_cannot_be_repaired(self):
  r=review_jev(FakeClient(),verdict(quote=''),TEXT,CASE)
  self.assertEqual(r.status,'unknown')
 def test_stored_map_omission_is_rejected_before_call(self):
  c=FakeClient()
  with self.assertRaises(ValueError):review_jev(c,verdict(),TEXT+' Extra assertion.',CASE)
  self.assertEqual(c.calls,[])
 def test_payload_contains_context_but_no_verdict_gold_or_quotes(self):
  c=FakeClient();review_jev(c,verdict(),TEXT,dict(CASE,gold_support='supported'))
  state,questions=c.calls[0]
  self.assertEqual(set(state),{'reference','candidate','parts'})
  self.assertEqual(state['parts'],[{'part_id':'p1','text':TEXT}]);self.assertEqual(set(questions),{'p1'})
 def test_unknown_no_evidence_needs_no_call(self):
  c=FakeClient();v=replace(verdict(),status='unknown',score=0,evidence_strength='none',evidence_check=None)
  self.assertIs(review_jev(c,v,TEXT,CASE),v);self.assertEqual(c.calls,[])
 def test_ids_probabilities_and_confidence_validated(self):
  cases=[]
  d=response();d['answers']['other']=d['answers'].pop('p1');cases.append(d)
  for val in [math.nan,math.inf,True,-.1,1.1]:
   d=response();d['answers']['p1']['probabilities']['supported']=val;cases.append(d)
   d=response();d['answers']['p1']['confidence']=val;cases.append(d)
  d=response();d['answers']['p1']['probabilities']['unknown']=.2;cases.append(d)
  d=response();d['answers']['p1']['choice']='unknown';cases.append(d)
  d=response();d['answers']['p1']['probabilities']['extra']=0;cases.append(d)
  for d in cases:
   with self.assertRaises(ValueError):validate_response(d,['p1'])
 def test_rounding_ties_and_extra_provider_metadata(self):
  d=response();d['answers']['p1'].update(probabilities={'supported':.5,'unknown':.5000001,'contradicted':0},choice='unknown')
  self.assertEqual(validate_response(d,['p1'])['answers']['p1']['choice'],'unknown')
  d['answers']['p1'].update(probabilities={'supported':.5,'unknown':.5,'contradicted':0},choice='supported')
  self.assertEqual(validate_response(d,['p1'])['answers']['p1']['choice'],'supported')
 def test_duplicate_json_and_nonfinite_constants_rejected(self):
  for text in ['{"answers":{},"answers":{}}','{"value":NaN}']:
   with self.assertRaises(ValueError):decode_response(text)
 def test_huge_numbers_fail_closed_instead_of_crashing(self):
  for field in ['probability','confidence','input_tokens','cost']:
   d=response()
   if field=='probability':d['answers']['p1']['probabilities']['supported']=10**400
   elif field=='confidence':d['answers']['p1']['confidence']=10**400
   else:d['usage'][field]=10**400
   # Include decoding: the large integer is valid JSON within the response bound.
   d=decode_response(json.dumps(d))
   with self.assertRaises(ValueError):validate_response(d,['p1'])
   c=FakeClient(d)
   r=run_case(CASE,c,'stage2',replay={'case_id':'t','question':CASE['question'],'candidate':TEXT,'claims':[{'text':TEXT}]})
   self.assertEqual(r['status'],'error');self.assertEqual(r['rewrite_plan'],[])
 def test_shared_transport_rejects_redirects_before_forwarding_auth(self):
  request=Request('https://openrouter.ai/api/v1/systemone',data=b'{}',headers={'Authorization':'Bearer test-secret'})
  for code in [301,302,303,307,308]:
   for target in ['http://other.example/systemone','https://other.example/systemone','https://openrouter.ai/other']:
    handler=NoRedirect()
    with self.assertRaises(HTTPError) as caught:handler.redirect_request(request,None,code,'redirect',{},target)
    caught.exception.close()
  # Both transports use this opener; a redirect cannot yield a second request.
  with patch('epistemic_harness.client.build_opener') as build:
   build.return_value.open.side_effect=HTTPError(request.full_url,302,'redirect',{},None)
   with self.assertRaises(HTTPError) as caught:urlopen(request,timeout=5)
   caught.exception.close()
   self.assertIsInstance(build.call_args.args[0],NoRedirect)
   self.assertEqual(build.return_value.open.call_count,1)
  with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-secret'},clear=True):
   cfg=copy.deepcopy(CONFIG);cfg['roles']['verifier']['provider']='openrouter'
   for call in [lambda:JevClient(cfg).decide({}, {'p1':{'type':'choice','criteria':CRITERIA}}),
                lambda:Client(cfg).complete('verifier','system',{})]:
    error=HTTPError(request.full_url,302,'redirect',{},io.BytesIO())
    with patch('epistemic_harness.client.build_opener') as build:
     build.return_value.open.side_effect=error
     with self.assertRaisesRegex(EndpointError,'HTTP 302'):call()
     self.assertIsInstance(build.call_args.args[0],NoRedirect)
     self.assertEqual(build.return_value.open.call_count,1)
    error.close()
 def test_native_endpoint_and_credentials_are_not_logged(self):
  with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-secret','OPENROUTER_BASE_URL':'https://openrouter.ai/api/v1'},clear=True):
   def send(req,timeout):
    self.assertEqual(req.full_url,'https://openrouter.ai/api/v1/systemone')
    body=json.loads(req.data);self.assertEqual(set(body),{'model','state','questions'})
    self.assertEqual(req.get_header('Authorization'),'Bearer test-secret')
    return io.BytesIO(json.dumps(response()).encode())
   with patch('epistemic_harness.jev_client.urlopen',side_effect=send):
    r=JevClient(CONFIG).decide({'reference':TEXT},{'p1':{'type':'choice','criteria':CRITERIA}})
   self.assertNotIn('test-secret',json.dumps(r))
 def test_http_errors_are_sanitized_and_not_retried(self):
  with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-secret'},clear=True):
   error=HTTPError('https://example.com',401,'sensitive body',{},None)
   with patch('epistemic_harness.jev_client.urlopen',side_effect=error) as send:
    with self.assertRaisesRegex(EndpointError,'HTTP 401'):JevClient(CONFIG).decide({}, {'p1':{'type':'choice','criteria':CRITERIA}})
    self.assertEqual(send.call_count,1)
 def test_oversized_response_and_unsafe_endpoint_rejected(self):
  with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-secret'},clear=True):
   with patch('epistemic_harness.jev_client.urlopen',return_value=io.BytesIO(b'x'*200001)):
    with self.assertRaises(ValueError):JevClient(CONFIG).decide({}, {'p1':{'type':'choice','criteria':CRITERIA}})
   os.environ['OPENROUTER_BASE_URL']='http://example.com'
   with self.assertRaises(ValueError):JevClient(CONFIG).decide({}, {'p1':{'type':'choice','criteria':CRITERIA}})
 def test_public_settings_do_not_expose_extra_reviewer_secrets(self):
  cfg=copy.deepcopy(CONFIG);cfg['decision_reviewer']['api_key']='test-secret'
  self.assertNotIn('test-secret',json.dumps(Client(cfg).public_settings()))
 def test_live_pipeline_dispatch_keeps_tentative_renderer(self):
  c=FakeClient();r=run_case(CASE,c,'stage2',replay={'case_id':'t','question':CASE['question'],'candidate':TEXT,'claims':[{'text':TEXT}]})
  self.assertEqual(len(c.calls),1);self.assertEqual(r['rewrite_plan'][0]['certainty'],'tentative');self.assertTrue(r['audit']['passed'])
 def test_alias_does_not_bypass_jev(self):
  c=FakeClient(response('unknown'));case=dict(CASE,accepted_claims=[TEXT])
  r=run_case(case,c,'stage2',replay={'case_id':'t','question':CASE['question'],'candidate':TEXT,'claims':[{'text':TEXT}]})
  self.assertEqual(len(c.calls),1);self.assertEqual(r['rewrite_plan'],[])
 def test_invalid_jev_reply_withholds_entire_answer(self):
  c=FakeClient({'model':'test','answers':{}})
  r=run_case(CASE,c,'stage2',replay={'case_id':'t','question':CASE['question'],'candidate':TEXT,'claims':[{'text':TEXT}]})
  self.assertEqual(r['status'],'error');self.assertEqual(r['rewrite_plan'],[])
 def test_arithmetic_and_demo_make_no_jev_call(self):
  c=FakeClient();case=dict(CASE,check={'type':'arithmetic_derivation','expression':'2 * 3'})
  r=run_case(case,c,'stage2',replay={'case_id':'t','question':CASE['question'],'candidate':'2 * 3 = 6','claims':[{'text':'2 * 3 = 6'}]})
  self.assertEqual(c.calls,[]);self.assertTrue(r['audit']['passed'])
  c=FakeClient();case=dict(CASE,demo_candidate=TEXT,accepted_claims=[TEXT])
  r=run_case(case,c,'stage2',demo=True);self.assertEqual(c.calls,[]);self.assertTrue(r['audit']['passed'])

if __name__=='__main__':unittest.main()
