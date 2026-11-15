"""Bounded checks over cited observations; never execute model-written code."""
import json
import math
import operator
import re


class InvalidOutput(ValueError):
    pass


def json_object(text):
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    try:
        value = json.loads(text, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (ValueError, TypeError) as e:
        raise InvalidOutput('Expected a JSON object') from e
    if not isinstance(value, dict): raise InvalidOutput('Expected a JSON object')
    return value


def citation(ref, sources):
    if not isinstance(ref, dict): raise InvalidOutput('Citation must be an object')
    source, quote = ref.get('ref'), ref.get('quote')
    if source not in sources or not isinstance(quote, str) or not quote or quote not in sources[source]:
        raise InvalidOutput('Citation must reference an exact observed source span')
    return {'ref': source, 'quote': quote}


def numeric_operand(value, sources):
    citation(value, sources)
    n = value.get('value')
    if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n):
        raise InvalidOutput('Numeric operand must be finite')
    # Only simple unambiguous numeric spans; complex formats go to semantic checking.
    numbers = re.findall(r'(?<![\w.])[-+]?\d+(?:\.\d+)?(?![\w.])', value['quote'])
    if len(numbers) != 1 or float(numbers[0]) != n:
        raise InvalidOutput('Numeric operand does not match its cited span')
    return n


def check_constraint(c, sources):
    if not isinstance(c, dict): raise InvalidOutput('Constraint must be an object')
    citation(c.get('source'), sources)
    if not all(isinstance(c.get(k), str) and c[k].strip() for k in ('requirement', 'assertion')):
        raise InvalidOutput('Constraint needs requirement and assertion')
    if type(c.get('applicable')) is not bool: raise InvalidOutput('Applicability must be boolean')
    if not c['applicable']: return {'result': 'not_applicable', 'method': c.get('method')}
    if c.get('method') == 'semantic': return {'result': 'needs_semantic', 'method': 'semantic'}
    if c.get('method') != 'numeric': raise InvalidOutput('Unsupported checker method')
    ops = {'le': operator.le, 'lt': operator.lt, 'ge': operator.ge, 'gt': operator.gt, 'eq': operator.eq, 'ne': operator.ne}
    if c.get('op') not in ops: raise InvalidOutput('Unsupported comparison operator')
    left = numeric_operand(c.get('left'), sources)
    right = numeric_operand(c.get('right'), sources)
    return {'result': 'satisfied' if ops[c['op']](left, right) else 'violated',
            'method': 'numeric', 'evidence': [citation(c['left'], sources), citation(c['right'], sources)],
            'operands': [left, right], 'operator': c['op'],
            'limitation': 'Requirement applicability and operand linking were model-derived; only comparison is deterministic.'}


def semantic_result(obj, sources, reviewer=False):
    key, allowed = ('verdict', {'support', 'challenge', 'inconclusive'}) if reviewer else (
        'result', {'satisfied', 'violated', 'inconclusive'})
    if obj.get(key) not in allowed or not isinstance(obj.get('reason'), str) or not obj['reason'].strip():
        raise InvalidOutput('Invalid semantic verdict/reason')
    if not isinstance(obj.get('evidence'), list): raise InvalidOutput('Evidence must be a list')
    evidence = [citation(x, sources) for x in obj['evidence']]
    if not reviewer and obj[key] != 'inconclusive' and not evidence:
        raise InvalidOutput('Conclusive semantic checks require cited evidence')
    return {key: obj[key], 'reason': obj['reason'], 'evidence': evidence}
