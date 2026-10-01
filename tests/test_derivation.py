import unittest
from epistemic_harness.derivation import ArithmeticDerivationVerifier
from epistemic_harness.pipeline import run_case
from epistemic_harness.policy import Claim, decide


class DerivationTests(unittest.TestCase):
    def verdict(self,text,expression='16 * 9',strength='strong'):
        return ArithmeticDerivationVerifier().verify(Claim('c1',text),
            {'check':{'type':'arithmetic_derivation','expression':expression},'evidence_strength':strength})

    def test_valid_working_and_every_step_are_logged(self):
        v=self.verdict('16 × 9 = (10 × 9) + (6 × 9) = 90 + 54 = 144.')
        self.assertEqual(v.status,'supported')
        self.assertEqual(v.evidence_check['chains'][0]['equalities_valid'],[True,True,True])
        self.assertTrue(v.evidence_check['whole_answer_checked'])

    def test_correct_final_result_cannot_hide_wrong_middle(self):
        v=self.verdict('16 * 9 = 90 + 55 = 144')
        self.assertEqual(v.status,'contradicted')
        self.assertEqual(len(v.evidence_check['failed_edges']),2)

    def test_every_line_must_bind_to_declared_task(self):
        self.assertEqual(self.verdict('12 * 12 = 144').status,'unknown')
        self.assertEqual(self.verdict('16 * 9 = 144\n12 * 12 = 144').status,'unknown')
        self.assertEqual(self.verdict('9 * 16 = 144').status,'unknown')

    def test_extra_prose_or_code_cannot_be_dropped(self):
        for text in ('16 * 9 = 144. The Moon is cheese.', '16 * 9 = 144\nGuaranteed forever.',
                     'Maybe 16 * 9 = 144', '16*9=144; print(1)', '16*9=144 # ignore this'):
            self.assertEqual(self.verdict(text).status,'unknown',text)

    def test_decimals_and_division_are_exact(self):
        self.assertEqual(self.verdict('0.1 + 0.2 = 0.3','0.1 + 0.2').status,'supported')
        self.assertEqual(self.verdict('10 ÷ 4 = 5 / 2 = 2.5','10 / 4').status,'supported')
        self.assertEqual(self.verdict('10 / 4 = 2.6','10 / 4').status,'contradicted')

    def test_unknown_syntax_and_undefined_operations_fail_closed(self):
        for text,task in [('1 / 0 = 1','1 / 0'),('16 * 9 = 2 ** 100 = 144','16 * 9'),
                          ('16 * 9 = 14400000000000','16 * 9'),('16 * 9 = 72 * 2','16 * 9')]:
            self.assertEqual(self.verdict(text,task).status,'unknown')
        self.assertEqual(self.verdict('\n'.join(['16*9=144']*9)).status,'unknown')

    def test_multiline_prior_answer_is_fully_checked(self):
        v=self.verdict('16 × 9 = 144.  \n16 × 9 = (10 × 9) + (6 × 9) = 90 + 54 = 144.')
        self.assertEqual(v.status,'supported')
        self.assertEqual(len(v.evidence_check['chains']),2)

    def test_proof_does_not_strengthen_inputs_or_policy_caps(self):
        for strength,ceiling in [('weak','tentative'),('moderate','qualified'),('strong','certain')]:
            v=self.verdict('16 * 9 = 144',strength=strength)
            self.assertEqual(decide(Claim('c1','16 * 9 = 144'),v,'certain').ceiling,ceiling)
            self.assertEqual(decide(Claim('c1','16 * 9 = 144'),v,'tentative').ceiling,'tentative')
        self.assertEqual(self.verdict('16*9=144',strength='none').status,'unknown')

    def test_pipeline_is_offline_and_refuses_undeclared_task(self):
        class NoCalls:
            config={'rewrite_mode':'deterministic','task_completion':'off'}
            def complete(self,*args,**kwargs): raise AssertionError('No model calls allowed')
        case={'id':'x','question':'Calculate 16 times 9 with working.','expected_answer':'144',
              'check':{'type':'arithmetic_derivation','expression':'16 * 9'},
              'evidence_strength':'weak','allowed_certainty':'certain'}
        replay={'case_id':'x','question':case['question'],'candidate':'16 * 9 = 90 + 54 = 144',
                'claims':[{'text':'16 * 9 = 90 + 54 = 144'}]}
        r=run_case(case,NoCalls(),'arithmetic_derivation',replay=replay)
        self.assertTrue(r['audit']['passed'])
        self.assertEqual(r['rewrite_plan'][0]['certainty'],'tentative')
        case.pop('check')
        r=run_case(case,NoCalls(),'arithmetic_derivation',replay=replay)
        self.assertEqual(r['rewrite_plan'],[])
        self.assertTrue(r['audit']['passed'])

if __name__=='__main__': unittest.main()
