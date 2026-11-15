import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_launcher_missing_key_fails_before_setup():
    env = dict(os.environ); env.pop('OPENROUTER_API_KEY', None)
    p = subprocess.run(['bash', str(ROOT/'scripts/run-judge-experiment.sh')],
                       input='', text=True, capture_output=True, env=env, cwd='/tmp')
    assert p.returncode == 1
    assert 'OPENROUTER_API_KEY' in p.stderr
    assert 'pip' not in p.stdout


def test_cli_missing_key_does_not_download(tmp_path):
    env = dict(os.environ); env.pop('OPENROUTER_API_KEY', None)
    p = subprocess.run([sys.executable, '-m', 'whowhen_eval.experiment', 'run',
                        '--data-root', str(tmp_path/'not-created')], capture_output=True, text=True, env=env, cwd=ROOT)
    assert p.returncode == 1 and 'OPENROUTER_API_KEY' in p.stderr
    assert not (tmp_path/'not-created').exists()
