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
        def __call__(self, *args): raise ValueError('synthetic failure')
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
