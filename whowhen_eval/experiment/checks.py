"""Bounded checks over cited observations; never execute model-written code."""
import json
import math
import operator
import re


class InvalidOutput(ValueError):
    pass


def json_object(text):
    # Accept prose/fences around one complete object. Never repair broken JSON,
    # extract a nested fragment, or choose between multiple candidate objects.
    if not isinstance(text, str): raise InvalidOutput('Expected a JSON object')
    start = text.find('{')
    if start < 0 or '[' in text[:start]: raise InvalidOutput('Expected a JSON object')
    try:
        decoder = json.JSONDecoder(parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        value, end = decoder.raw_decode(text, start)
    except (ValueError, TypeError) as e:
        raise InvalidOutput('Expected a JSON object') from e
    if not isinstance(value, dict) or any(c in text[end:] for c in '{}[]'):
        raise InvalidOutput('Expected a single JSON object')
    return value


def citation(ref, sources):
    if not isinstance(ref, dict): raise InvalidOutput('Citation must be an object')
    source, quote = ref.get('ref'), ref.get('quote')
    if not isinstance(source, str) or source not in sources or not isinstance(quote, str) or not quote or quote not in sources[source]:
        raise InvalidOutput('Citation must reference an exact observed source span')
    return {'ref': source, 'quote': quote}


def source_reference(ref, sources):
    """Resolve a source ID; text always comes from the recorded source, not the model."""
    key = ref if isinstance(ref, str) else ref.get('ref') if isinstance(ref, dict) else None
    if not isinstance(key, str) or key.strip() not in sources:
        raise InvalidOutput('Unknown or malformed source ID')
    key = key.strip()
    return {'ref': key, 'quote': sources[key]}


def numeric_operand(value, sources):
    citation(value, sources)
    n = value.get('value')
    if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n):
        raise InvalidOutput('Numeric operand must be finite')
    # Only simple unambiguous numeric spans; complex formats go to semantic checking.
    numbers = list(re.finditer(r'(?<![\w.])[-+]?\d+(?:\.\d+)?(?![\w.])', value['quote']))
    if len(numbers) != 1 or float(numbers[0].group()) != n:
        raise InvalidOutput('Numeric operand does not match its cited span')
    source = sources[value['ref']]
    # Match broad numeric tokens in the ORIGINAL source. Grouped/scientific numbers
    # must not become different values by trimming the quote around a suffix.
    tokens = {m.span() for m in re.finditer(
        r'(?<![\w.+−-])[+−-]?(?:\d+(?:,\d+)*(?:\.\d+)?|\.\d+)(?:[eE][+−-]?\d+)?(?![\w]|[.,]\d)', source)}
    for occurrence in re.finditer(re.escape(value['quote']), source):
        span = (occurrence.start()+numbers[0].start(), occurrence.start()+numbers[0].end())
        if span not in tokens:
            raise InvalidOutput('Numeric operand quote cuts a larger source number')
    return n


def check_constraint(c, sources):
    if not isinstance(c, dict): raise InvalidOutput('Constraint must be an object')
    source_reference(c.get('source'), sources)
    if not all(isinstance(c.get(k), str) and c[k].strip() for k in ('requirement', 'assertion')):
        raise InvalidOutput('Constraint needs requirement and assertion')
    if type(c.get('applicable')) is not bool: raise InvalidOutput('Applicability must be boolean')
    if not c['applicable']: return {'result': 'not_applicable', 'method': c.get('method')}
    if c.get('method') == 'semantic': return {'result': 'needs_semantic', 'method': 'semantic'}
    if c.get('method') != 'numeric': raise InvalidOutput('Unsupported checker method')
    ops = {'le': operator.le, 'lt': operator.lt, 'ge': operator.ge, 'gt': operator.gt, 'eq': operator.eq, 'ne': operator.ne}
    if not isinstance(c.get('op'), str) or c['op'] not in ops: raise InvalidOutput('Unsupported comparison operator')
    left = numeric_operand(c.get('left'), sources)
    right = numeric_operand(c.get('right'), sources)
    return {'result': 'satisfied' if ops[c['op']](left, right) else 'violated',
            'method': 'numeric', 'evidence': [citation(c['left'], sources), citation(c['right'], sources)],
            'operands': [left, right], 'operator': c['op'],
            'limitation': 'Requirement applicability and operand linking were model-derived; only comparison is deterministic.'}


def semantic_result(obj, sources, reviewer=False):
    key, allowed = ('verdict', {'support', 'challenge', 'inconclusive'}) if reviewer else (
        'result', {'satisfied', 'violated', 'inconclusive'})
    if not isinstance(obj.get(key), str) or obj[key] not in allowed or not isinstance(obj.get('reason'), str) or not obj['reason'].strip():
        raise InvalidOutput('Invalid semantic verdict/reason')
    if not isinstance(obj.get('evidence'), list): raise InvalidOutput('Evidence must be a list')
    evidence = [source_reference(x, sources) for x in obj['evidence']]
    if obj[key] != 'inconclusive' and not evidence:
        raise InvalidOutput('Conclusive checks and reviews require source evidence')
    return {key: obj[key], 'reason': obj['reason'], 'evidence': evidence}
