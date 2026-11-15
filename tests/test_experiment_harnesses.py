import json

import pytest

from tests.test_experiment_data import release, taxonomy
from whowhen_eval.experiment.config import load_config
from whowhen_eval.experiment.data import bundle
from whowhen_eval.experiment.harnesses import run_harness, valid_prediction
from whowhen_eval.experiment.checks import check_constraint, InvalidOutput

ANSWER = 'Agent Name: agent\nStep Number: 2\nError Mode: R.2\nReason: The selected flight exceeds the budget.'


class Scripted:
    def __init__(self, responses): self.responses = responses; self.calls = []
    def __call__(self, role, parts):
        self.calls.append((role, parts))
        result = self.responses[role] if role in self.responses else self.responses['default']
        if isinstance(result, Exception): raise result
        if isinstance(result, list): result = result.pop(0)
        return result if isinstance(result, str) else json.dumps(result)


def test_baseline_one_unchanged_call(release, taxonomy):
    c = bundle(release, taxonomy); call = Scripted({'baseline': ANSWER})
    r = run_harness('baseline', c, taxonomy, load_config(), call)
    assert call.calls == [('baseline', c['baseline_parts'])]
    assert r['prediction']['error_mode'] == 'R.2'


def test_agentrx_prefixes_empty_checks_and_final(release, taxonomy):
    c = bundle(release, taxonomy)
    call = Scripted({'requirements': {'requirements': []}, 'constraints': {'constraints': []}, 'final': ANSWER})
    r = run_harness('agentrx', c, taxonomy, load_config(), call)
    assert len(call.calls) == 4  # requirements, two prefixes, final
    first_prefix = json.dumps(call.calls[1][1])
    assert 'Flight A costs 620' in first_prefix
    assert 'Selected A' not in first_prefix
    assert r['audit']['checks'] == []


def numeric_constraint():
    return {'requirement': 'Price <= budget', 'source': {'ref': 'task', 'quote': '500 pounds'},
            'applicable': True, 'method': 'numeric', 'assertion': 'Selected price within budget', 'op': 'le',
            'left': {'ref': 'event:0', 'quote': '620 pounds', 'value': 620},
            'right': {'ref': 'task', 'quote': '500 pounds', 'value': 500}}


def test_numeric_evidence_is_anchored_and_never_executes():
    sources = {'task': 'Budget 500 pounds', 'event:0': 'Price 620 pounds'}
    c = numeric_constraint()
    assert check_constraint(c, sources)['result'] == 'violated'
    c['left']['value'] = 20
    with pytest.raises(InvalidOutput, match='operand'): check_constraint(c, sources)
    c['left']['value'] = 620; c['op'] = '__import__("os")'
    with pytest.raises(InvalidOutput): check_constraint(c, sources)
    c['op'] = 'le'; c['left']['ref'] = 'event:99'
    with pytest.raises(InvalidOutput): check_constraint(c, sources)


def test_agentrx_semantic_inconclusive_is_valid(release, taxonomy):
    c = bundle(release, taxonomy)
    constraint = numeric_constraint(); constraint['method'] = 'semantic'
    call = Scripted({'requirements': {'requirements': []},
                     'constraints': [{'constraints': [constraint]}, {'constraints': []}],
                     'semantic': {'result': 'inconclusive', 'reason': 'No purchase outcome', 'evidence': []},
                     'final': ANSWER})
    r = run_harness('agentrx', c, taxonomy, load_config(), call)
    assert r['audit']['checks'][0]['result'] == 'inconclusive'
    assert r['audit']['checks'][0]['coord'] == '1'


def test_malformed_intermediate_is_not_empty_success(release, taxonomy):
    with pytest.raises(InvalidOutput):
        run_harness('agentrx', bundle(release, taxonomy), taxonomy, load_config(), Scripted({'requirements': 'garbage'}))


def test_raffles_stops_at_support_and_checks_all_four_roles(release, taxonomy):
    call = Scripted({'initial': ANSWER, 'default': {'verdict': 'support', 'reason': 'Supported', 'evidence': []}})
    r = run_harness('raffles', bundle(release, taxonomy), taxonomy, load_config(), call)
    assert len(call.calls) == 5
    assert r['audit']['stop'] == 'consensus'
    assert {x[0] for x in call.calls[1:]} == {'review_fault', 'review_decisiveness', 'review_primacy', 'review_taxonomy'}


def test_raffles_cap_and_malformed_revision_fallback(release, taxonomy):
    call = Scripted({'initial': ANSWER, 'revision': 'malformed',
                     'default': {'verdict': 'challenge', 'reason': 'Earlier mistake', 'evidence': []}})
    r = run_harness('raffles', bundle(release, taxonomy), taxonomy, load_config(), call)
    assert len(call.calls) == 10
    assert r['raw_output'] == ANSWER
    assert r['audit']['stop'] == 'round_limit'
    assert r['audit']['fallback'] is True


def test_structural_validation_is_not_correctness(release, taxonomy):
    c = bundle(release, taxonomy)
    assert valid_prediction({'agent_name': 'agent', 'step_coord': 'Step 1', 'error_mode': 'A.1'}, c, taxonomy)
    assert not valid_prediction({'agent_name': 'nonexistent', 'step_coord': '1', 'error_mode': 'A.1'}, c, taxonomy)
