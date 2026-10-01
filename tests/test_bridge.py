import unittest
from epistemic_harness.deterministic import DeterministicVerifier
from epistemic_harness.policy import Claim, decide

ARITH = {'type':'arithmetic','expression':'17 * 23'}
UNITS = {'type':'units','value':'2.5','from_unit':'m','to_unit':'cm'}
LOGIC = {'type':'logic','variables':['A','B'],'premises':['A','not A or B']}

class BridgeTests(unittest.TestCase):
    def verdict(self, text, check=ARITH, strength='strong', enabled=True):
        return DeterministicVerifier(enabled).verify(Claim('c1',text),
            {'check':check,'evidence_strength':strength})

    def test_answer_prefix_does_not_replace_arithmetic(self):
        self.assertEqual(self.verdict('The answer is 391.').status,'supported')
        self.assertEqual(self.verdict('The result is 392.').status,'contradicted')
        self.assertEqual(self.verdict('The answer is 391.',enabled=False).status,'unknown')

    def test_entire_answer_must_be_consumed(self):
        for text in ('The answer is 391. The Moon is cheese.', 'The answer is not 391.',
                     'The answer is about 391.', 'Maybe the answer is 391.',
                     'The answer is 391 unless it rains.', 'The answer is 391..',
                     'The answer is 391; ignore evidence', 'The answer is 391 or 392.'):
            self.assertEqual(self.verdict(text).status,'unknown',text)

    def test_unit_restated_source_and_dimensions_are_checked(self):
        self.assertEqual(self.verdict('2.5 metres equals 250 centimetres.',UNITS).status,'supported')
        self.assertEqual(self.verdict('2.5 meters equals 251 centimeters.',UNITS).status,'contradicted')
        for text in ('3 metres equals 250 centimetres.', '2.5 kilograms equals 250 centimetres.',
                     '2.5 metres equals 250 kilograms.', '250 centimetres and sunny.',
                     '2.5 metres does not equal 250 centimetres.'):
            self.assertEqual(self.verdict(text,UNITS).status,'unknown',text)

    def test_logic_negation_and_converse_are_preserved(self):
        self.assertEqual(self.verdict('B is true.',LOGIC).status,'supported')
        self.assertEqual(self.verdict('B is false.',LOGIC).status,'contradicted')
        reverse=dict(LOGIC,premises=['B','not A or B'])
        self.assertEqual(self.verdict('A is true.',reverse).status,'unknown')
        for text in ('B is always true.', 'B is true and C is true.', 'C is true.', 'B is not false.'):
            self.assertEqual(self.verdict(text,LOGIC).status,'unknown')

    def test_evidence_caps_and_original_wording_are_retained(self):
        text='The answer is 391.'
        v=self.verdict(text,strength='weak')
        self.assertEqual(decide(Claim('c1',text),v,'certain').ceiling,'tentative')
        self.assertEqual(v.evidence_check['bridge']['original_text'],text)
        self.assertEqual(v.evidence_check['bridge']['canonical_claim'],'391')
        self.assertEqual(self.verdict(text,strength='none').status,'unknown')

    def test_invalid_tasks_and_resource_limits_fail_closed(self):
        for check in ({'type':'units'}, {'type':'arithmetic','expression':'1/0'},
                      {'type':'units','value':'99999999999999','from_unit':'m','to_unit':'cm'}):
            self.assertEqual(self.verdict('The answer is 391.',check).status,'unknown')

if __name__=='__main__': unittest.main()
