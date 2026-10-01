import unittest
from epistemic_harness.deterministic import DeterministicVerifier, arithmetic, logic_status
from epistemic_harness.policy import Claim, decide
from epistemic_harness.pipeline import run_case


class DeterministicTests(unittest.TestCase):
    def verdict(self,text,check,strength='strong'):
        case={'check':check,'evidence_strength':strength}
        return DeterministicVerifier().verify(Claim('c1',text),case)

    def test_decimal_arithmetic_is_exact(self):
        self.assertEqual(arithmetic('0.1 + 0.2'),arithmetic('0.3'))
        self.assertEqual(self.verdict('2.5',{'type':'arithmetic','expression':'10 / 4'}).status,'supported')
        self.assertEqual(self.verdict('2.6',{'type':'arithmetic','expression':'10 / 4'}).status,'contradicted')

    def test_source_code_and_resource_heavy_syntax_are_rejected(self):
        for expression in ("__import__('os').system('anything')",'2 ** 999999','1 / 0','1e99','9999999999999 * 2'):
            v=self.verdict('1',{'type':'arithmetic','expression':expression})
            self.assertEqual(v.status,'unknown')

    def test_correct_substring_cannot_validate_extra_claims(self):
        v=self.verdict('391; an unrelated fact',{'type':'arithmetic','expression':'17 * 23'})
        self.assertEqual(v.status,'unknown')
        v=self.verdict('300 cm; always sunny',{'type':'units','value':'3','from_unit':'m','to_unit':'cm'})
        self.assertEqual(v.status,'unknown')

    def test_units_require_compatible_dimensions(self):
        check={'type':'units','value':'500','from_unit':'g','to_unit':'kg'}
        self.assertEqual(self.verdict('0.5 kg',check).status,'supported')
        self.assertEqual(self.verdict('0.5 m',check).status,'unknown')
        self.assertEqual(self.verdict('0.6 kg',check).status,'contradicted')
        self.assertEqual(self.verdict('100 cm',dict(check,to_unit='cm')).status,'unknown')

    def test_logic_distinguishes_implication_from_its_converse(self):
        forward={'type':'logic','variables':['A','B'],'premises':['A','not A or B']}
        self.assertEqual(self.verdict('B',forward).status,'supported')
        converse=dict(forward,premises=['B','not A or B'])
        self.assertEqual(self.verdict('A',converse).status,'unknown')
        self.assertEqual(self.verdict('A and B',dict(forward,premises=['A'])).status,'unknown')

    def test_inconsistent_premises_do_not_create_vacuous_certainty(self):
        check={'type':'logic','variables':['A','B'],'premises':['A','not A']}
        v=self.verdict('B',check)
        self.assertEqual(v.status,'unknown')
        self.assertEqual(v.evidence_check['consistent_worlds'],0)

    def test_logic_is_bounded_and_rejects_calls(self):
        for text in ('A()', '__import__("os")', 'A == B', 'C'):
            v=self.verdict(text,{'type':'logic','variables':['A','B'],'premises':['A']})
            self.assertEqual(v.status,'unknown')
        v=self.verdict('A',{'type':'logic','variables':list('ABCDEFGHI'),'premises':[]})
        self.assertEqual(v.status,'unknown')

    def test_computation_respects_fixture_evidence_and_policy_caps(self):
        v=self.verdict('391',{'type':'arithmetic','expression':'17 * 23'},'weak')
        self.assertEqual(decide(Claim('c1','391'),v,'certain').ceiling,'tentative')
        v=self.verdict('391',{'type':'arithmetic','expression':'17 * 23'})
        self.assertEqual(decide(Claim('c1','391'),v,'qualified').ceiling,'qualified')

    def test_fixed_pipeline_runs_with_no_model_calls(self):
        class NoCalls:
            config={'rewrite_mode':'deterministic'}
            def complete(self,*args): raise AssertionError('Model should not be called')
        case={'id':'x','question':'Compute 17 * 23','evidence_strength':'strong','allowed_certainty':'certain',
              'check':{'type':'arithmetic','expression':'17 * 23'}}
        replay={'case_id':'x','question':case['question'],'candidate':'391','claims':[{'text':'391'}]}
        r=run_case(case,NoCalls(),'deterministic',replay=replay)
        self.assertEqual(r['status'],'ok')
        self.assertTrue(r['audit']['passed'])
        self.assertEqual(r['rewrite_plan'][0]['certainty'],'certain')


if __name__=='__main__': unittest.main()
