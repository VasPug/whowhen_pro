"""Sequential, resumable experiment execution with a fixed denominator."""
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import random
import time

from ..prompts import load_taxonomy
from ..score import score
from .config import ARMS
from .data import digest, file_hash, code_hash, atomic_json
from .checks import InvalidOutput
from .client import Client, ProviderError, FatalProviderError, BudgetExceeded, validate_credentials
from .harnesses import run_harness


def verify(run_dir):
    root = Path(run_dir)
    m = json.loads((root/'manifest.json').read_text())
    if digest(m['identity']) != m['run_id']: raise ValueError('Manifest identity changed')
    payload = {k:v for k,v in m.items() if k not in ('identity','run_id')}
    if digest(payload) != m['identity'].get('prepared_hash'): raise ValueError('Manifest cohort/artifact fingerprints changed')
    cfg = m['identity']['config']
    if len(m['evaluation']) != cfg['sample_size'] or len(m['development']) != cfg['dev_size']:
        raise ValueError('Manifest partition counts differ from configuration')
    entries = m['evaluation'] + m['development']
    ids = [e['case_id'] for e in entries]
    groups = [e['group'] for e in entries]
    if len(set(ids)) != len(ids) or len(set(groups)) != len(groups):
        raise ValueError('Manifest cases/groups must be unique and partitions disjoint')
    if set(ids) != set(m['case_hashes']): raise ValueError('Manifest case references differ')
    if m['identity']['code_hash'] != code_hash(): raise ValueError('Code changed; prepare a new run')
    if file_hash(root/'taxonomy.yaml') != m['identity']['files']['taxonomy']:
        raise ValueError('Prepared taxonomy changed')
    if file_hash(root/'labels.json') != m['labels_hash']: raise ValueError('Prepared labels changed')
    for cid, checksum in m['case_hashes'].items():
        if file_hash(root/'cases'/f'{cid}.json') != checksum: raise ValueError(f'Prepared case changed: {cid}')
    if not m['evaluation']: raise ValueError('Empty evaluation cohort')
    return m


@contextmanager
def run_lock(root):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    with (root/'.run.lock').open('a') as f:
        try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e: raise RuntimeError('This experiment is already running') from e
        try: yield
        finally: fcntl.flock(f, fcntl.LOCK_UN)


def result_name(arm, case_id, rep):
    return f'{arm}__{case_id}__r{rep:03d}'


def run(run_dir, offline=False, client_factory=Client):
    root = Path(run_dir)
    with run_lock(root):
        m = verify(root); cfg = m['identity']['config']
        mode = root / ('offline' if offline else 'live')
        taxonomy = load_taxonomy(root)
        labels = json.loads((root/'labels.json').read_text())
        schedule = [(arm, entry, rep) for rep in range(cfg['repetitions'])
                    for entry in m['evaluation'] for arm in ARMS]
        random.Random(cfg['seed']).shuffle(schedule)
        if not offline: validate_credentials(cfg)
        for index, (arm, entry, rep) in enumerate(schedule, 1):
            name = result_name(arm, entry['case_id'], rep)
            dest = mode/'results'/f'{name}.json'
            if dest.exists():
                previous = json.loads(dest.read_text())
                if previous.get('run_id') != m['run_id'] or previous.get('offline') != offline:
                    raise ValueError('Stored result belongs to a different experiment')
                continue
            # Validate credentials before recording a failure; an absent key should not poison resume.
            client = client_factory(cfg, mode/'calls'/f'{name}.jsonl', mode/'budget.json', offline=offline)
            case = json.loads((root/'cases'/f'{entry["case_id"]}.json').read_text())
            record = {'run_id': m['run_id'], 'arm': arm, 'case_id': entry['case_id'], 'repetition': rep,
                      'offline': offline, 'source_hash': entry['source_hash'], 'status': 'failed',
                      'prediction': {}, 'score': {'agent': False, 'step': False, 'mode': False}}
            started = time.monotonic()
            try:
                output = run_harness(arm, case, taxonomy, cfg, client)
                record.update(output)
                record['score'] = score(output['prediction'], labels[entry['case_id']], entry['framework'])
                record['status'] = 'completed'
                record['valid_fields'] = all(output['prediction'].get(k) for k in ('agent_name','step_coord','error_mode'))
            except BudgetExceeded:
                record['error'] = 'budget_exhausted'
            except FatalProviderError:
                # Bad key/account/routing affects the run, not this trace. Leave
                # the outcome missing so corrected setup can resume normally.
                from .report import summarize
                summarize(root, offline=offline)
                raise
            except (ProviderError, InvalidOutput) as e:
                record['error'] = str(e)  # these classes use fixed, credential-free diagnostics
            except Exception as e:
                record['error'] = f'Unexpected {type(e).__name__}; inspect the call audit'
            record['wall_seconds'] = time.monotonic() - started
            atomic_json(dest, record)
            print(f'[{index}/{len(schedule)}] {arm} {entry["case_id"]}: {record["status"]}', flush=True)
        from .report import summarize
        return summarize(root, offline=offline)
