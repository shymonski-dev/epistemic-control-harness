"""Declared arithmetic is checked locally; remaining text uses reference verification."""
from .derivation import ArithmeticDerivationVerifier
from .verification import ModelVerifier, BenchmarkVerifier


class Stage2Verifier:
    def __init__(self, client, demo=False):
        self.client = client
        self.demo = demo

    def verify(self, claim, case):
        # Any declared check is handled locally, including invalid/unsupported declarations.
        # Failure never falls through to a model that might approve the proof.
        if 'check' in case:
            return ArithmeticDerivationVerifier().verify(claim, case)
        if self.demo:
            return BenchmarkVerifier().verify(claim, case)
        return ModelVerifier(self.client, self.client.config.get('verification_protocol', 'evidence_map')).verify(claim, case)
