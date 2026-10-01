import json
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch
from epistemic_harness.__main__ import load_cases
from epistemic_harness.client import Client, EndpointError
from epistemic_harness.metrics import summarize
from epistemic_harness.pipeline import extract_claims, run_case
from epistemic_harness.policy import Claim, Verification, decide, validate_plan, render, audit, LEVELS, EVIDENCE
from epistemic_harness.verification import BenchmarkVerifier, ModelVerifier, evidence_check_verdict
from epistemic_harness.environment import load_env_file
from epistemic_harness.evaluate import evaluate

ROOT = Path(__file__).resolve().parent.parent


class ScriptedClient:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def complete(self, role, system, payload):
        self.calls.append((role, payload))
        value = next(self.replies)
        if isinstance(value, Exception):
            raise value
        return value


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.case = load_cases(ROOT / 'benchmarks/starter.jsonl')[0]

    def test_all_evidence_scores_and_benchmark_caps(self):
        claim = Claim('c1', 'X')
        for status in ('supported', 'unknown', 'contradicted'):
            for strength in EVIDENCE:
                for score in (0, .49, .5, .69, .7, .89, .9, 1):
                    for allowed in LEVELS:
                        d = decide(claim, Verification(status, score, strength, 'test', ''), allowed)
                        self.assertLessEqual(LEVELS.index(d.ceiling), EVIDENCE.index(strength))
                        self.assertLessEqual(LEVELS.index(d.ceiling), LEVELS.index(allowed))
                        if status != 'supported':
                            self.assertEqual(d.ceiling, 'abstain')
                        for proposed in LEVELS:
                            plan = [{'claim_id':'c1', 'certainty':proposed}]
                            if LEVELS.index(proposed) > LEVELS.index(d.ceiling):
                                with self.assertRaises(ValueError): validate_plan(plan, [d])
                            else:
                                validate_plan(plan, [d])
                                self.assertTrue(audit(render(plan, [claim]), plan, [claim], [d])['passed'])

    def test_rewrite_cannot_add_words_or_unknown_duplicate_claims(self):
        d = decide(Claim('c1', 'X'), Verification('supported', 1, 'weak', 'test',''), 'certain')
        invalid = [[{'claim_id':'c1','certainty':'tentative','text':'Definitely X'}],
                   [{'claim_id':'missing','certainty':'tentative'}],
                   [{'claim_id':'c1','certainty':'tentative'}]*2, {'answer':'Definitely X'}]
        for plan in invalid:
            with self.assertRaises(ValueError): validate_plan(plan, [d])

    def test_final_audit_detects_text_tampering(self):
        c = Claim('c1', 'X is definitely true.\nCertain: other text')
        d = decide(c, Verification('supported', 1, 'weak', 'test',''), 'certain')
        plan = [{'claim_id':'c1','certainty':'tentative'}]
        text = render(plan, [c])
        self.assertIn('Tentative, unverified', text)
        self.assertIn('\\n', text)
        self.assertFalse(audit(text + '\nDefinitely X', plan, [c], [d])['passed'])

    def test_exact_matching_does_not_validate_extra_false_claim(self):
        v = BenchmarkVerifier()
        self.assertEqual(v.verify(Claim('c1','391'), self.case).status, 'supported')
        self.assertEqual(v.verify(Claim('c1','391. The Moon is made of cheese.'), self.case).status, 'unknown')

    def test_extraction_must_preserve_all_content(self):
        candidate = '391. The Moon is made of cheese.'
        claims, warning = extract_claims(candidate, ScriptedClient(['{"claims":["391."]}']))
        self.assertEqual(claims[0].text, candidate)
        self.assertIsNotNone(warning)
        claims, warning = extract_claims(candidate, ScriptedClient(['{"claims":["391.","The Moon is made of cheese."]}']))
        self.assertEqual(len(claims), 2)
        self.assertIsNone(warning)

    def test_model_only_support_never_becomes_strong(self):
        client = ScriptedClient(['{"status":"supported","score":1,"reason":"I agree"}'])
        claim = Claim('c1', 'An unmatched paraphrase')
        verdict = ModelVerifier(client).verify(claim, self.case)
        self.assertEqual(verdict.evidence_strength, 'weak')
        self.assertEqual(decide(claim, verdict, 'certain').ceiling, 'tentative')

    def test_malformed_verifier_fails_closed(self):
        client = ScriptedClient(['The answer is 391', '{"claims":["The answer is 391"]}', '{"status":"supported","score":NaN,"reason":"yes"}'])
        record = run_case(self.case, client, 'model')
        self.assertEqual(record['status'], 'error')
        self.assertEqual(record['rewrite_plan'], [])

    def test_exact_and_no_evidence_verification_need_no_model(self):
        client = ScriptedClient([])
        verifier = ModelVerifier(client)
        self.assertEqual(verifier.verify(Claim('c1', '391'), self.case).method, 'benchmark_exact')
        case = dict(self.case, accepted_claims=[], evidence_strength='none', allowed_certainty='abstain')
        self.assertEqual(verifier.verify(Claim('c1', 'Anything'), case).status, 'unknown')
        self.assertEqual(client.calls, [])

    def test_replay_preserves_candidates_and_claims_without_generator_calls(self):
        original = run_case(self.case, None, 'benchmark', demo=True)
        original['run_id'] = 'original'
        client = ScriptedClient(['[{"claim_id":"c1","certainty":"certain"}]'])
        replayed = run_case(self.case, client, 'model', replay=original)
        self.assertEqual(replayed['status'], 'ok')
        self.assertEqual(replayed['candidate'], original['candidate'])
        self.assertEqual(replayed['claims'], original['claims'])
        self.assertEqual(replayed['replay_source_run_id'], 'original')
        self.assertEqual([c[0] for c in client.calls], ['rewriter'])

    def test_replay_cannot_omit_unverified_text(self):
        original = run_case(self.case, None, 'benchmark', demo=True)
        original['candidate'] = '391. A false extra claim.'
        result = run_case(self.case, ScriptedClient([]), 'model', replay=original)
        self.assertEqual(result['status'], 'error')

    def test_model_cannot_override_known_contradiction(self):
        case = dict(self.case, rejected_claims=['392'])
        client = ScriptedClient([])
        v = ModelVerifier(client).verify(Claim('c1','392'), case)
        self.assertEqual(v.status, 'contradicted')
        self.assertEqual(client.calls, [])

    def test_invalid_rewriter_falls_back_without_upgrade(self):
        client = ScriptedClient(['391', '{"claims":["391"]}', '[{"claim_id":"c1","certainty":"certain","text":"extra"}]'])
        record = run_case(self.case, client, 'benchmark')
        self.assertEqual(record['status'], 'ok')
        self.assertTrue(record['audit']['passed'])
        self.assertTrue(record['warnings'])
        self.assertNotIn('extra', record['final'])
        self.assertEqual([c[0] for c in client.calls], ['generator','generator','rewriter'])
        self.assertEqual(client.calls[0][1], {'question':self.case['question']})

    def test_network_failure_abstains(self):
        record = run_case(self.case, ScriptedClient([EndpointError('Unavailable')]), 'benchmark')
        self.assertEqual(record['status'], 'error')
        self.assertEqual(summarize([record])['abstention_rate'], 1)

    def test_all_starter_cases_run_offline(self):
        cases = load_cases(ROOT / 'benchmarks/starter.jsonl')
        self.assertEqual(len(cases), 20)
        records = [run_case(c, None, 'benchmark', demo=True) for c in cases]
        self.assertTrue(all(r['audit']['passed'] for r in records))
        metrics = summarize(records)
        self.assertEqual(metrics['overstatement_rate'], 0)
        self.assertIsNone(metrics['factual_correctness'])
        self.assertGreater(metrics['baseline_overstatement_rate_heuristic'], 0)
        self.assertGreater(metrics['abstention_rate'], 0)

    def test_endpoint_role_routing_and_auth(self):
        config = {'roles': {'generator':{'provider':'local','model_env':'GENERATOR_MODEL'},
                            'verifier':{'provider':'openrouter','model_env':'VERIFIER_MODEL',
                                        'response_format':{'type':'json_schema','json_schema':{'name':'test','schema':{'type':'object'}}}},
                            'rewriter':{'provider':'local','model':'rewrite-local'}}, 'timeout_seconds':10}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return b'{"choices":[{"finish_reason":"stop","message":{"content":"ok"}}]}'
        with patch.dict('os.environ', {'GENERATOR_MODEL':'gen-local','VERIFIER_MODEL':'verify-remote',
                                      'OPENROUTER_API_KEY':'test-secret'}, clear=True):
            with patch('epistemic_harness.client.urlopen', return_value=Response()) as call:
                client = Client(config)
                for role in ('generator','verifier','rewriter'):
                    self.assertEqual(client.complete(role, 'system', {}), 'ok')
                requests = [c.args[0] for c in call.call_args_list]
                self.assertEqual(requests[0].full_url, 'http://localhost:1234/v1/chat/completions')
                self.assertEqual(requests[1].full_url, 'https://openrouter.ai/api/v1/chat/completions')
                self.assertEqual(requests[1].get_header('Authorization'), 'Bearer test-secret')
                self.assertIsNone(requests[0].get_header('Authorization'))
                self.assertEqual([json.loads(r.data)['model'] for r in requests], ['gen-local','verify-remote','rewrite-local'])
                self.assertNotIn('response_format', json.loads(requests[0].data))
                self.assertEqual(json.loads(requests[1].data)['response_format'], config['roles']['verifier']['response_format'])

    def test_truncated_response_is_not_accepted(self):
        config = {'roles': {'generator':{'provider':'local','model':'test'}}}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return b'{"choices":[{"finish_reason":"length","message":{"content":"partial"}}]}'
        with patch('epistemic_harness.client.urlopen', return_value=Response()):
            with self.assertRaises(EndpointError): Client(config).complete('generator','system',{})


    def test_evidence_check_distinguishes_missing_support_from_conflict(self):
        data={'all_parts_supported':False,'explicit_conflict':False,'conflict_quote':'',
              'score':1.0,'reason':'Not supplied'}
        case=dict(self.case,expected_answer='The beacon is inactive.')
        unknown=evidence_check_verdict(data,case)
        self.assertEqual(unknown.status,'unknown')
        self.assertEqual(unknown.score,0)
        self.assertEqual(decide(Claim('c1','Anything'),unknown,'certain').ceiling,'abstain')
        data.update(explicit_conflict=True,conflict_quote='The beacon is inactive.')
        self.assertEqual(evidence_check_verdict(data,case).status,'contradicted')
        data.update(explicit_conflict=False,conflict_quote='',all_parts_supported=True)
        supported=evidence_check_verdict(data,case)
        self.assertEqual(supported.status,'supported')
        self.assertEqual(decide(Claim('c1','Anything'),supported,'certain').ceiling,'tentative')

    def test_inconsistent_flags_or_untraceable_conflict_fail_closed(self):
        base={'all_parts_supported':False,'explicit_conflict':True,'conflict_quote':'Invented quote',
              'score':1.0,'reason':'Conflict'}
        for data in (base,dict(base,conflict_quote=''),
                     dict(base,all_parts_supported=True),
                     dict(base,explicit_conflict=False)):
            verdict=evidence_check_verdict(data,self.case)
            self.assertEqual(verdict.status,'unknown')
            self.assertIsNotNone(verdict.evidence_check['guard_reason'])

    def test_evidence_check_rejects_nonboolean_flags_and_nan(self):
        base={'all_parts_supported':True,'explicit_conflict':False,'conflict_quote':'',
              'score':1.0,'reason':'Supported'}
        for data in (dict(base,all_parts_supported=1),dict(base,explicit_conflict='false'),dict(base,score=float('nan'))):
            with self.assertRaises(ValueError): evidence_check_verdict(data,self.case)

    def test_env_file_never_executes_and_environment_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'.env'
            path.write_text("OPENROUTER_API_KEY='$(never-execute-this)'\nVERIFIER_MODEL=file-model\n")
            with patch.dict('os.environ', {'VERIFIER_MODEL':'existing'}, clear=True):
                load_env_file(path)
                import os
                self.assertEqual(os.environ['OPENROUTER_API_KEY'], '$(never-execute-this)')
                self.assertEqual(os.environ['VERIFIER_MODEL'], 'existing')

    def test_env_parse_failure_does_not_partially_set_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'.env'
            path.write_text('OPENROUTER_API_KEY=test-secret\nUNSUPPORTED=oops\n')
            with patch.dict('os.environ', {}, clear=True):
                with self.assertRaises(ValueError) as error:
                    load_env_file(path)
                self.assertNotIn('test-secret', str(error.exception))
                import os
                self.assertNotIn('OPENROUTER_API_KEY', os.environ)

    def test_review_preserves_coverage_denominators_and_rejects_changed_answers(self):
        r=run_case(self.case, None, 'benchmark', demo=True)
        r['run_id']='review-test'
        review={'reviewer':{'type':'test'},'basis':'Fixture', 'cases':[{
            'case_id':self.case['id'],'candidate_text':r['candidate'],'candidate_correct':True,
            'candidate_completeness':'complete','abstention_appropriate':False,'note':''}]}
        result=evaluate([r], review)
        self.assertEqual(result['final_factual_correctness_denominator'],1)
        r['rewrite_plan']=[]
        result=evaluate([r], review)
        self.assertIsNone(result['final_factual_correctness'])
        self.assertEqual(result['inappropriate_abstention_count'],1)
        r['candidate']='Changed'
        with self.assertRaises(ValueError): evaluate([r], review)


if __name__ == '__main__':
    unittest.main()
