"""Optional whole-answer grammar. No substring harvesting or model translation."""
import re

NUM = r'[+-]?(?:\d+(?:\.\d+)?|\.\d+)'
ALIASES = {
    'mm': ('millimetre', 'millimeter'), 'cm': ('centimetre', 'centimeter'),
    'm': ('metre', 'meter'), 'km': ('kilometre', 'kilometer'),
    'g': ('gram',), 'kg': ('kilogram',), 's': ('second',),
    'min': ('minute',), 'h': ('hour',),
}
UNIT_NAMES = {name: unit for unit, names in ALIASES.items()
              for name in (unit, *(n for root in names for n in (root, root+'s')))}


def bridge_claim(text, check):
    """Return canonical text and a trace, or refuse the entire answer."""
    trace = {'original_text': text, 'rule': 'refused', 'canonical_claim': None,
             'whole_answer': True}
    if not isinstance(text, str) or len(text) > 240:
        return None, dict(trace, guard_reason='Answer outside bridge bounds')
    # Only a single optional terminal period; no dropped clauses or qualifiers.
    value = text.strip()
    if value.endswith('.'): value = value[:-1].rstrip()
    kind = check.get('type')
    canonical = None
    rule = None
    if kind in ('arithmetic', 'units'):
        prefix = re.fullmatch(r'(?:The answer is|The result is) (.+)', value, re.I)
        body = prefix[1] if prefix else value
        if kind == 'arithmetic' and re.fullmatch(NUM, body):
            canonical, rule = body, 'numeric_answer' if prefix else 'numeric_literal'
        elif kind == 'units':
            match = re.fullmatch('('+NUM+r')\s+([A-Za-z]+)', body)
            if match and match[2].lower() in UNIT_NAMES:
                canonical = match[1]+' '+UNIT_NAMES[match[2].lower()]
                rule = 'unit_answer' if prefix else 'unit_literal'
            if canonical is None:
                conversion = re.fullmatch('('+NUM+r')\s+([A-Za-z]+) (?:equals|is equal to) ('+NUM+r')\s+([A-Za-z]+)', value, re.I)
                if conversion:
                    # A restated source must exactly match the declared source quantity/unit.
                    from .deterministic import number
                    source_unit = UNIT_NAMES.get(conversion[2].lower())
                    target_unit = UNIT_NAMES.get(conversion[4].lower())
                    if (source_unit == check.get('from_unit') and target_unit and
                            number(conversion[1]) == number(check['value'])):
                        canonical, rule = conversion[3]+' '+target_unit, 'declared_conversion'
    elif kind == 'logic':
        match = re.fullmatch(r'([A-Z][A-Za-z0-9_]*) is (true|false)', value)
        if match and match[1] in check.get('variables', []):
            canonical = match[1] if match[2] == 'true' else 'not '+match[1]
            rule = 'symbol_truth'
        # Original strict Boolean grammar remains supported by the checker.
        elif not value.endswith('.'):
            canonical, rule = value, 'boolean_expression'
    if canonical is None:
        return None, dict(trace, guard_reason='Whole answer does not match an approved grammar')
    return canonical, dict(trace, rule=rule, canonical_claim=canonical)
