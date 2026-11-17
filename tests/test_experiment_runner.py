import json
from pathlib import Path

import pytest

from tests.test_experiment_data import release, make_data
from whowhen_eval.experiment.config import load_config
from whowhen_eval.experiment.data import prepare
from whowhen_eval.experiment.runner import run, verify, run_lock
from whowhen_eval.experiment.report import summarize, metrics, paired_interval


@pytest.fixture
def prepared(tmp_path, release):
    cfg = load_config()
    cfg.update(sample_size=3, dev_size=2, text_sha256=None, taxonomy_sha256=None, bootstrap_samples=30)
    return prepare(cfg, make_data(tmp_path, release), tmp_path/'runs')


def test_offline_run_three_arms_and_resume(prepared, monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    run(prepared, offline=True)
    report = summarize(prepared, offline=True)
    assert report['offline'] and report['complete']
    assert report['scheduled'] == 9
    assert all(a['completed'] == 3 for a in report['arms'].values())
    logs = list((prepared/'offline'/'calls').glob('*.jsonl'))
    before = {p: p.read_bytes() for p in logs}
    run(prepared, offline=True)
    assert {p: p.read_bytes() for p in logs} == before
    assert not (prepared/'live').exists()
    assert (prepared/'offline'/'report.md').exists()


def test_modified_source_cannot_resume(prepared):
    case = next((prepared/'cases').glob('*.json'))
    case.write_text(case.read_text()+' ')
    with pytest.raises(ValueError, match='case'): verify(prepared)


def test_exclusive_lock(prepared):
    with run_lock(prepared):
        with pytest.raises(RuntimeError, match='running'):
            with run_lock(prepared): pass


def test_partial_report_keeps_denominator(prepared):
    report = summarize(prepared, offline=True)
    assert not report['complete'] and report['missing'] == 9
    assert report['arms']['baseline']['metrics']['What'] == 0
    assert report['arms']['baseline']['metrics']['Who'] is None
    assert report['comparisons']['agentrx']['interval_95'] is None


def test_failures_remain_wrong_and_recorded(prepared):
    class Broken:
        def __init__(self, *args, **kwargs): pass
        def __call__(self, *args, **kwargs): raise ValueError('synthetic failure')
    run(prepared, offline=True, client_factory=Broken)
    r = summarize(prepared, offline=True)
    assert r['complete'] and r['missing'] == 0
    assert r['arms']['agentrx']['failed'] == 3
    assert r['arms']['agentrx']['metrics']['What'] == 0


def test_metrics_use_framework_averaging_and_canonical_modes():
    rows = [{'fw':'macnet', 'modality':'text', 'a_correct':True, 's_correct':True, 'm_correct':True,
             'gt_mode':'R.2','pr_mode':'R.2'} for _ in range(9)]
    rows += [{'fw':'debate', 'modality':'text', 'a_correct':False, 's_correct':False, 'm_correct':True,
              'gt_mode':'A.1','pr_mode':'R.2'}]
    result = metrics(rows)
    assert result['Who'] == 0.5 and result['When'] == 0.5
    assert result['What'] < 0.5  # canonical modes, not m_correct


def test_paired_interval_preserves_pairing():
    rows = [{'fw':'macnet', 'modality':'text', 'group':str(i), 'a_correct':True,
             's_correct':True, 'm_correct':True, 'gt_mode':'R.2', 'pr_mode':'R.2'} for i in range(5)]
    assert paired_interval(rows, rows, samples=30, seed=4) == [0.0, 0.0]


def test_empty_report_does_not_claim_success(tmp_path):
    with pytest.raises((ValueError, FileNotFoundError)): summarize(tmp_path)


def test_cohort_mutation_rejected_even_with_unchanged_identity(prepared):
    path = prepared/'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['evaluation'] = manifest['evaluation'][:1]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Manifest'): verify(prepared)


def test_fatal_provider_error_leaves_cases_resumable(prepared, monkeypatch):
    from whowhen_eval.experiment.client import FatalProviderError
    monkeypatch.setattr('whowhen_eval.experiment.runner.validate_credentials', lambda cfg: None)
    class BadKey:
        def __init__(self, *args, **kwargs): pass
        def __call__(self, *args, **kwargs): raise FatalProviderError('Provider HTTP 401')
    with pytest.raises(FatalProviderError): run(prepared, client_factory=BadKey)
    assert not list((prepared/'live'/'results').glob('*.json'))


def test_auth_preflight_happens_before_any_case(prepared, monkeypatch):
    from whowhen_eval.experiment.client import FatalProviderError
    def reject(cfg): raise FatalProviderError('Invalid OpenRouter key')
    monkeypatch.setattr('whowhen_eval.experiment.runner.validate_credentials', reject)
    class Never:
        def __init__(self, *args, **kwargs): pytest.fail('No per-case client before authentication')
    with pytest.raises(FatalProviderError): run(prepared, client_factory=Never)
    assert not list((prepared/'live'/'results').glob('*.json'))


@pytest.mark.parametrize('field,value', [('framework','debate'),('group','different-task-group')])
def test_cohort_metadata_bound_to_identity(prepared, field, value):
    path = prepared/'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['evaluation'][0][field] = value
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Manifest'): verify(prepared)


def test_report_counts_unfinished_attempt_as_unknown(prepared):
    path = prepared/'offline'/'calls'/'baseline__case-0000__r000.jsonl'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'phase':'started','attempt_id':'a','role':'baseline','offline':True})+'\n')
    r = summarize(prepared, offline=True)['arms']['baseline']['resources']
    assert r['attempts'] == 1 and r['unknown_outcome_attempts'] == 1
    assert r['cost_usd'] is None
