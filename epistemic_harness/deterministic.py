"""Bounded checkers for declared tasks. No eval, model translation, or answer-code execution."""
import ast
from fractions import Fraction
from itertools import product
import re
from .policy import Claim, Verification

NUMBER = r'[+-]?(?:\d+(?:\.\d+)?|\.\d+)'
UNITS = {'mm':('length',Fraction(1,1000)), 'cm':('length',Fraction(1,100)),
         'm':('length',Fraction(1)), 'km':('length',Fraction(1000)),
         'g':('mass',Fraction(1,1000)), 'kg':('mass',Fraction(1)),
         's':('time',Fraction(1)), 'min':('time',Fraction(60)), 'h':('time',Fraction(3600))}


def number(text: str) -> Fraction:
    if not isinstance(text,str) or len(text)>32 or not re.fullmatch(NUMBER,text):
        raise ValueError('Unsupported number syntax')
    return bounded(Fraction(text))


def bounded(value: Fraction) -> Fraction:
    if abs(value.numerator)>10**12 or value.denominator>10**12:
        raise ValueError('Arithmetic limit exceeded')
    return value


def arithmetic(expression: str) -> Fraction:
    if not isinstance(expression,str) or len(expression)>120 or not re.fullmatch(r'[0-9.\s+*/()\-]+',expression):
        raise ValueError('Unsupported arithmetic syntax')
    tree=ast.parse(expression.strip(),mode='eval')
    if len(list(ast.walk(tree)))>64: raise ValueError('Expression too complex')
    def visit(node):
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            return number(ast.get_source_segment(expression.strip(),node))
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            value=visit(node.operand)
            return value if isinstance(node.op,ast.UAdd) else -value
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
            left,right=visit(node.left),visit(node.right)
            if isinstance(node.op,ast.Add): value=left+right
            elif isinstance(node.op,ast.Sub): value=left-right
            elif isinstance(node.op,ast.Mult): value=left*right
            else: value=left/right
            return bounded(value)
        raise ValueError('Arithmetic operator not allowed')
    return visit(tree.body)


def logic_tree(text: str, variables: list[str]):
    if not isinstance(text,str) or len(text)>160: raise ValueError('Invalid logic expression')
    tree=ast.parse(text,mode='eval').body
    if len(list(ast.walk(tree)))>64: raise ValueError('Logic expression too complex')
    def validate(node):
        if isinstance(node,ast.Name) and node.id in variables: return
        if isinstance(node,ast.Constant) and type(node.value) is bool: return
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,ast.Not):
            validate(node.operand); return
        if isinstance(node,ast.BoolOp) and isinstance(node.op,(ast.And,ast.Or)):
            for child in node.values: validate(child)
            return
        raise ValueError('Unsupported logic syntax')
    validate(tree)
    return tree


def truth(node,world):
    if isinstance(node,ast.Name): return world[node.id]
    if isinstance(node,ast.Constant): return node.value
    if isinstance(node,ast.UnaryOp): return not truth(node.operand,world)
    values=[truth(child,world) for child in node.values]
    return all(values) if isinstance(node.op,ast.And) else any(values)


def logic_status(check: dict, claim: str) -> tuple[str,dict]:
    variables=check['variables']; premises=check['premises']
    if (not isinstance(variables,list) or not 1<=len(variables)<=8 or
        any(not isinstance(v,str) or not re.fullmatch(r'[A-Z][A-Za-z0-9_]*',v) for v in variables) or
        len(set(variables))!=len(variables)):
        raise ValueError('Declare 1 to 8 distinct logic variables')
    if not isinstance(premises,list) or len(premises)>16: raise ValueError('Too many premises')
    constraints=[logic_tree(p,variables) for p in premises]
    query=logic_tree(claim,variables)
    outcomes=[]
    for values in product((False,True),repeat=len(variables)):
        world=dict(zip(variables,values))
        if all(truth(p,world) for p in constraints): outcomes.append(truth(query,world))
    detail={'consistent_worlds':len(outcomes),'claim_true_worlds':sum(outcomes)}
    if not outcomes: return 'unknown',dict(detail,guard_reason='Inconsistent premises; no vacuous certainty')
    return ('supported' if all(outcomes) else 'contradicted' if not any(outcomes) else 'unknown'),detail


class DeterministicVerifier:
    def __init__(self, claim_bridge=False):
        self.claim_bridge = claim_bridge

    def verify(self,claim: Claim,case: dict) -> Verification:
        check=case.get('check')
        if not isinstance(check,dict):
            return Verification('unknown',0,'none','deterministic_unknown','No declared check')
        kind=check.get('type')
        bridge = None
        try:
            text = claim.text
            if self.claim_bridge:
                from .bridge import bridge_claim
                text, bridge = bridge_claim(text, check)
                if text is None: raise ValueError('Bridge refused answer')
            if kind=='arithmetic':
                expected=arithmetic(check['expression'])
                match=re.fullmatch(r'\s*('+NUMBER+r')\s*',text)
                if not match: raise ValueError('Claim must contain only a numeric result')
                actual=number(match[1]); status='supported' if actual==expected else 'contradicted'
                detail={'expression':check['expression'],'computed_result':str(expected),'claimed_result':str(actual)}
            elif kind=='units':
                source,target=check['from_unit'],check['to_unit']
                if source not in UNITS or target not in UNITS or UNITS[source][0]!=UNITS[target][0]:
                    raise ValueError('Unknown or incompatible unit dimensions')
                expected=bounded(number(check['value'])*UNITS[source][1]/UNITS[target][1])
                match=re.fullmatch(r'\s*('+NUMBER+r')\s+([A-Za-z]+)\s*',text)
                if not match or match[2] not in UNITS or UNITS[match[2]][0]!=UNITS[target][0]:
                    raise ValueError('Claim must contain only a number and compatible unit')
                actual=bounded(number(match[1])*UNITS[match[2]][1]/UNITS[target][1])
                status='supported' if actual==expected else 'contradicted'
                detail={'value':check['value'],'from_unit':source,'to_unit':target,
                        'computed_result':str(expected),'claimed_result_in_target_unit':str(actual)}
            elif kind=='logic': status,detail=logic_status(check,text)
            else: raise ValueError('Unsupported declared check type')
        except (ValueError,SyntaxError,TypeError,KeyError,ZeroDivisionError,RecursionError):
            return Verification('unknown',0,'none','deterministic_unknown',
                                'Invalid evidence, unsupported syntax, or bounded-check limit',
                                {'bridge':bridge} if bridge is not None else None)
        if bridge is not None: detail['bridge'] = bridge
        strength=case['evidence_strength'] if status=='supported' else 'none'
        if strength=='none' and status=='supported': status='unknown'
        return Verification(status,1.0 if status=='supported' else 0.0,strength,
            'deterministic_'+kind,'Computed from the declared task; logic certainty is conditional on supplied premises',detail)
