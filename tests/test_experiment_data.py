import copy
import hashlib
import json
from pathlib import Path

import pytest

from whowhen_eval.experiment.config import load_config
from whowhen_eval.experiment.data import bundle, prepare, download_verified, digest
from whowhen_eval.prompts import Taxonomy
from whowhen_eval.run import build_prompt


@pytest.fixture
def release():
    return {
        'id': 'secret_R.2_trace', 'framework': 'alfagent', 'benchmark': 'alfworld',
        'task': {'query': 'Choose a flight costing at most 500 pounds.', 'answer': 'SECRET_ANSWER'},
        'trajectory': [
            {'kind': 'user', 'content': 'HIDDEN_INITIAL_INSTRUCTION'},
            {'kind': 'action', 'step_number': 1, 'reasoning': 'Look up flight A',
             'action': 'search A', 'observation': 'Flight A costs 620 pounds.',
             'is_final_answer': False, 'is_injected': True},
            {'kind': 'action', 'step_number': 2, 'reasoning': 'Choose A',
             'action': 'select A', 'observation': 'Selected A', 'is_final_answer': False}],
        'ground_truth': {'agent': 'agent', 'step': 2, 'mode': 'R.2'},
        'gt_agent': 'SECRET_AGENT', 'eval_error_preview': 'SECRET_EVAL',
    }


@pytest.fixture
def taxonomy():
    return Taxonomy(('R.2', 'A.1'), '- R.2: Reasoning error\n- A.1: Tool argument error')


def test_bundle_preserves_baseline_and_excludes_hidden_metadata(release, taxonomy):
    case = bundle(release, taxonomy)
    assert case['baseline_parts'] == build_prompt(release, 'alfagent', taxonomy)
    dumped = json.dumps(case)
    for secret in ['SECRET_ANSWER', 'SECRET_AGENT', 'SECRET_EVAL', 'secret_R.2_trace', 'is_injected', 'HIDDEN_INITIAL_INSTRUCTION']:
        assert secret not in dumped
    assert [e['coord'] for e in case['events']] == ['1', '2']
    assert case['events'][1]['agent'] == 'agent'
    changed = copy.deepcopy(release)
    changed['ground_truth']['mode'] = 'A.1'
    assert bundle(changed, taxonomy) == case


def test_config_rejects_unsupported_modality_and_bad_limits(tmp_path):
    p = tmp_path / 'config.yaml'
    p.write_text('modality: video\n')
    with pytest.raises(ValueError, match='text'): load_config(p)
    p.write_text('max_cost_usd: -1\n')
    with pytest.raises(ValueError): load_config(p)


def make_data(tmp_path, release, n=12):
    data = tmp_path / 'data-root'
    (data / 'data').mkdir(parents=True)
    (data / 'taxonomy.yaml').write_text('R.2:\n  name: Reasoning error\n  description: Wrong inference\n')
    rows = []
    for i in range(n):
        r = copy.deepcopy(release)
        r['id'] = f'row-{i}'
        r['task']['query'] += f' Task group {i // 2}'
        rows.append({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k,v in r.items()})
    (data / 'data/text.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    return data


def test_prepare_freezes_disjoint_groups_and_identity(tmp_path, release):
    data = make_data(tmp_path, release)
    cfg = load_config()
    cfg.update(sample_size=3, dev_size=2, text_sha256=None, taxonomy_sha256=None)
    p = prepare(cfg, data, tmp_path / 'runs')
    m = json.loads((p / 'manifest.json').read_text())
    ev, dev = m['evaluation'], m['development']
    assert len(ev) == 3 and len(dev) == 2
    assert not ({e['group'] for e in ev} & {e['group'] for e in dev})
    assert p == prepare(cfg, data, tmp_path / 'runs')
    cfg['temperature'] = 0.2
    assert p != prepare(cfg, data, tmp_path / 'runs')
    cfg['temperature'] = 0.0
    with (data / 'data/text.jsonl').open('a') as f: f.write('\n')
    assert p != prepare(cfg, data, tmp_path / 'runs')


def test_download_never_installs_corrupt_file(tmp_path):
    src = tmp_path / 'source'; src.write_bytes(b'bad')
    dest = tmp_path / 'dest'
    with pytest.raises(ValueError, match='checksum'):
        download_verified(src.as_uri(), dest, hashlib.sha256(b'good').hexdigest())
    assert not dest.exists()


def test_prepare_rejects_missing_gold_modes(tmp_path, release):
    data = make_data(tmp_path, release)
    (data / 'taxonomy.yaml').write_text('A.1:\n  name: Other\n')
    cfg = load_config(); cfg.update(text_sha256=None, taxonomy_sha256=None)
    with pytest.raises(ValueError, match='taxonomy'): prepare(cfg, data, tmp_path / 'runs')
