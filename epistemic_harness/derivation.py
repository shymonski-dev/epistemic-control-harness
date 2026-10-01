"""Check literal equality chains for a declared arithmetic task, without a model."""
import ast
import re
from .deterministic import arithmetic, number, NUMBER
from .policy import Verification


def normalize_operators(text):
    return text.translate(str.maketrans({'×': '*', '÷': '/', '−': '-'})).strip()


def task_tree(text):
    # arithmetic() validates the whitelist and resource bounds before AST comparison.
    arithmetic(text)
    return ast.dump(ast.parse(text.strip(), mode='eval'), include_attributes=False)


def check_derivation(text, expression):
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise ValueError('Derivation outside text bounds')
    if not isinstance(expression, str): raise ValueError('Missing declared arithmetic task')
    task = normalize_operators(expression)
    expected = arithmetic(task)
    anchor = task_tree(task)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not 1 <= len(lines) <= 8: raise ValueError('Declare 1 to 8 equality chains')
    chains = []
    failed_edges = []
    term_count = 0
    for line_number, original in enumerate(lines, 1):
        line = normalize_operators(original)
        if line.endswith('.'): line = line[:-1].rstrip()
        if not re.fullmatch(r'[0-9.\s+*/()=\-]+', line):
            raise ValueError('Whole answer must contain only arithmetic chains')
        terms = [term.strip() for term in line.split('=')]
        term_count += len(terms)
        if not 2 <= len(terms) <= 16 or term_count > 64:
            raise ValueError('Derivation term limit exceeded')
        if task_tree(terms[0]) != anchor:
            raise ValueError('Chain does not start with the declared task')
        if not re.fullmatch(NUMBER, terms[-1]):
            raise ValueError('Chain must end with a numeric result')
        number(terms[-1])
        values = [arithmetic(term) for term in terms]
        edges = [left == right for left, right in zip(values, values[1:])]
        failed_edges.extend({'line': line_number, 'edge': i+1} for i, ok in enumerate(edges) if not ok)
        chains.append({'original_text': original, 'terms': terms,
                       'exact_values': [str(v) for v in values], 'equalities_valid': edges})
    return ('contradicted' if failed_edges else 'supported'), {
        'declared_expression': expression, 'expected_value': str(expected),
        'chains': chains, 'failed_edges': failed_edges, 'whole_answer_checked': True,
        'proof_scope': 'Exact numeric equalities for the declared expression; no proof of real-world inputs',
    }


class ArithmeticDerivationVerifier:
    def verify(self, claim, case):
        check = case.get('check')
        try:
            if not isinstance(check, dict) or check.get('type') != 'arithmetic_derivation':
                raise ValueError('No manually declared arithmetic derivation task')
            status, proof = check_derivation(claim.text, check['expression'])
        except (ValueError, SyntaxError, TypeError, KeyError, ZeroDivisionError, RecursionError) as exc:
            return Verification('unknown', 0, 'none', 'checked_arithmetic_derivation',
                                'Proof refused: '+str(exc)[:160], {'whole_answer_checked': False})
        strength = case['evidence_strength'] if status == 'supported' else 'none'
        if strength == 'none' and status == 'supported': status = 'unknown'
        return Verification(status, 1.0 if status == 'supported' else 0.0, strength,
                            'checked_arithmetic_derivation',
                            'Every equality checked exactly; certainty remains capped by declared input evidence', proof)
