import unittest
from epistemic_harness.evidence import evidence_verdict
from epistemic_harness.policy import Claim, decide

CASE={'expected_answer':'A is known. B is unobserved.','evidence_strength':'strong'}

def part(text,status='supported',quote='A is known.'):
    return {'text':text,'status':status,'evidence_quote':quote,'reason':'Reference relation'}

class EvidenceTests(unittest.TestCase):
    def verdict(self,claim,parts,score=1):
        return evidence_verdict({'score':score,'parts':parts},claim,CASE)

    def test_supported_prefix_cannot_hide_unsupported_tail(self):
        with self.assertRaises(ValueError): self.verdict('A is known. B is known.',[part('A is known.')])
        v=self.verdict('A is known. B is known.',[part('A is known.'),part('B is known.','unknown','')])
        self.assertEqual(v.status,'unknown')
        self.assertEqual(v.evidence_strength,'none')

    def test_gaps_reordered_and_paraphrased_spans_are_rejected(self):
        for parts in ([part('B is known.'),part('A is known.')],
                      [part('A'),part('B is known.')], [part('A is established.')]):
            with self.assertRaises(ValueError): self.verdict('A is known. B is known.',parts)

    def test_fabricated_quotes_cannot_support_or_contradict(self):
        for status in ('supported','contradicted'):
            for quote in ('','A is known and B is false.'):
                v=self.verdict('A is known.',[part('A is known.',status,quote)])
                self.assertEqual(v.status,'unknown')
                self.assertIsNotNone(v.evidence_check['parts'][0]['guard_reason'])

    def test_full_mapping_never_promotes_model_evidence(self):
        v=self.verdict('A is known.',[part('A is known.')])
        self.assertEqual(v.status,'supported')
        self.assertEqual(v.evidence_strength,'weak')
        self.assertEqual(decide(Claim('c1','A is known.'),v,'certain').ceiling,'tentative')

    def test_unknown_is_not_contradiction(self):
        v=self.verdict('B is known.',[part('B is known.','unknown','')])
        self.assertEqual(v.status,'unknown')
        self.assertEqual(v.score,0)

    def test_invalid_scores_and_unexpected_fields_fail_closed(self):
        for score in (True,float('nan'),float('inf'),-1,2):
            with self.assertRaises(ValueError): self.verdict('A is known.',[part('A is known.')],score)
        with self.assertRaises(ValueError):
            evidence_verdict({'score':1,'parts':[part('A is known.')],'status':'supported'},'A is known.',CASE)

    def test_valid_quote_is_not_semantic_proof(self):
        # A malicious/mistaken semantic judgment can still pass provenance; retain weak cap.
        v=self.verdict('B is known.',[part('B is known.',quote='A is known.')])
        self.assertEqual(v.evidence_strength,'weak')
        self.assertIn('not semantic proof',v.evidence_check['provenance_note'])

if __name__=='__main__': unittest.main()
