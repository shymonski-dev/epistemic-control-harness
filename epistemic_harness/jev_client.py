"""Bounded OpenRouter System One transport. No chat requests or automatic retries."""
import hashlib
import json
import math
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request
from .client import EndpointError, urlopen

OPTIONS = ('supported', 'contradicted', 'unknown')


def validate_settings(settings):
    if (not isinstance(settings, dict) or set(settings) != {'provider', 'model', 'protocol'} or
            settings['provider'] != 'openrouter' or settings['protocol'] != 'systemone' or
            not isinstance(settings['model'], str) or not settings['model'].strip() or len(settings['model']) > 200):
        raise ValueError('Decision reviewer requires openrouter, systemone and a model')
    return settings


def numeric(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_response(data, ids):
    if (not isinstance(data, dict) or not isinstance(data.get('answers'), dict) or
            set(data['answers']) != set(ids) or not isinstance(data.get('model'), str) or
            not data['model'].strip() or len(data['model']) > 200):
        raise ValueError('Invalid Jev response model or answer IDs')
    answers = {}
    for pid, answer in data['answers'].items():
        if not isinstance(answer, dict) or answer.get('type') != 'choice' or answer.get('choice') not in OPTIONS:
            raise ValueError('Invalid Jev Choice answer')
        probs = answer.get('probabilities'); confidence = answer.get('confidence')
        if (not isinstance(probs, dict) or set(probs) != set(OPTIONS) or
                any(not numeric(p) or not 0 <= p <= 1 for p in probs.values()) or
                abs(sum(probs.values()) - 1) > 1e-6):
            raise ValueError('Invalid Jev probability distribution')
        if probs[answer['choice']] < max(probs.values()) - 1e-9:
            raise ValueError('Jev selected a non-maximal option')
        if not numeric(confidence) or not 0 <= confidence <= 1:
            raise ValueError('Invalid Jev confidence')
        answers[pid] = {k: answer[k] for k in ('type', 'choice', 'probabilities', 'confidence')}
    usage = {}
    if isinstance(data.get('usage'), dict):
        for key in ('input_tokens', 'output_tokens', 'cost'):
            value = data['usage'].get(key)
            if value is not None:
                if not numeric(value) or value < 0 or (key.endswith('tokens') and type(value) is not int):
                    raise ValueError('Invalid Jev usage')
                usage[key] = value
    return {'answers': answers, 'model': data['model'], 'usage': usage}


def decode_response(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate Jev JSON key')
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError('Non-finite Jev JSON constant')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)


class JevClient:
    def __init__(self, config):
        self.settings = validate_settings(config.get('decision_reviewer'))
        self.timeout = config.get('timeout_seconds', 60)
        if type(self.timeout) is not int or self.timeout <= 0:
            raise ValueError('Invalid Jev timeout')

    def decide(self, state, questions):
        if not isinstance(questions, dict) or not 1 <= len(questions) <= 32:
            raise ValueError('Invalid Jev question count')
        for pid, q in questions.items():
            if (not isinstance(pid, str) or not pid or not isinstance(q, dict) or
                    q.get('type') != 'choice' or not isinstance(q.get('criteria'), dict) or
                    set(q['criteria']) != set(OPTIONS)):
                raise ValueError('Invalid Jev question')
        key = os.environ.get('OPENROUTER_API_KEY', '')
        if not key:
            raise ValueError('OPENROUTER_API_KEY is required for Jev')
        base = os.environ.get('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1').rstrip('/')
        parsed = urlsplit(base)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Invalid Jev endpoint URL')
        endpoint = base + '/systemone'
        body = json.dumps({'model': self.settings['model'], 'state': state, 'questions': questions},
                          allow_nan=False, ensure_ascii=False).encode()
        if len(body) > 200_000:
            raise ValueError('Jev request exceeds bounded size')
        request = Request(endpoint, data=body, headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(200_001)
        except HTTPError as exc:
            raise EndpointError(f'Jev endpoint returned HTTP {exc.code}') from None
        except (URLError, TimeoutError, OSError):
            raise EndpointError('Jev transport failed') from None
        if len(raw) > 200_000:
            raise ValueError('Jev response exceeds bounded size')
        result = validate_response(decode_response(raw), questions)
        result.update(requested_model=self.settings['model'], request_sha256=hashlib.sha256(body).hexdigest())
        return result
