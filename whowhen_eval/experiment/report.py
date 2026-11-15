"""Fixed-denominator, framework-weighted metrics and paired uncertainty."""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import random
from statistics import mean

from ..leaderboard import cell_metrics, AXES
from .config import ARMS
from .data import atomic_json
from .runner import verify, result_name


def mode_counts(rows, labels=None):
    labels = sorted(labels if labels is not None else {r['gt_mode'] for r in rows})
    out = {}
    for lab in labels:
        tp = sum(r['gt_mode'] == lab and r['pr_mode'] == lab for r in rows)
        fp = sum(r['gt_mode'] != lab and r['pr_mode'] == lab for r in rows)
        fn = sum(r['gt_mode'] == lab and r['pr_mode'] != lab for r in rows)
        p, r = tp/(tp+fp) if tp+fp else 0, tp/(tp+fn) if tp+fn else 0
        out[lab] = {'support': tp+fn, 'precision': p, 'recall': r, 'f1': 2*p*r/(p+r) if p+r else 0}
    return out


def metrics(rows, labels=None):
    if not rows: return {a: None for a in AXES}
    cells = []
    for modality in sorted({r['modality'] for r in rows}):
        subset = [r for r in rows if r['modality'] == modality]
        cell = cell_metrics(subset)
        if labels is not None:
            cell['What'] = mean(v['f1'] for v in mode_counts(subset, labels).values())
        cells.append(cell)
    return {a: mean(c[a] for c in cells if c[a] is not None)
            if any(c[a] is not None for c in cells) else None for a in AXES}


def repeated_metrics(rows, labels=None):
    reps = sorted({r.get('repetition', 0) for r in rows})
    scores = {str(rep): metrics([r for r in rows if r.get('repetition', 0) == rep], labels) for rep in reps}
    avg = {a: mean(s[a] for s in scores.values() if s[a] is not None)
           if any(s[a] is not None for s in scores.values()) else None for a in AXES}
    return avg, scores


def paired_interval(base, treatment, samples=1000, seed=0):
    if len(base) != len(treatment) or not base: raise ValueError('Paired data must be nonempty and aligned')
    strata = defaultdict(lambda: defaultdict(list))
    for i, (b, t) in enumerate(zip(base, treatment)):
        if any(b.get(k) != t.get(k) for k in ('group', 'fw', 'modality', 'repetition')):
            raise ValueError('Paired rows are misaligned')
        strata[(b['modality'], b['fw'])][b['group']].append(i)
    labels = {r['gt_mode'] for r in base}
    rng = random.Random(seed); deltas = []
    for _ in range(samples):
        indices = []
        for groups in strata.values():
            keys = sorted(groups)
            for _ in keys: indices.extend(groups[rng.choice(keys)])
        b = repeated_metrics([base[i] for i in indices], labels)[0]['What']
        t = repeated_metrics([treatment[i] for i in indices], labels)[0]['What']
        deltas.append(t-b)
    deltas.sort()
    return [deltas[int((samples-1)*0.025)], deltas[int((samples-1)*0.975)]]


def _usage(logs):
    costs = []; tokens = []; missing = 0
    for c in logs:
        u = c.get('usage') or {}
        cost = u.get('cost'); token = u.get('total_tokens')
        if isinstance(cost, (int,float)): costs.append(cost)
        else: missing += 1
        if isinstance(token, int): tokens.append(token)
    return {'attempts': len(logs), 'cost_usd': sum(costs) if logs and not missing else None,
            'known_cost_usd': sum(costs), 'attempts_without_cost': missing,
            'total_tokens': sum(tokens) if logs and len(tokens) == len(logs) else None,
            'known_tokens': sum(tokens),
            'input_tokens_known': sum((c.get('usage') or {}).get('prompt_tokens') or 0 for c in logs),
            'output_tokens_known': sum((c.get('usage') or {}).get('completion_tokens') or 0 for c in logs),
            'reasoning_tokens_known': sum(((c.get('usage') or {}).get('completion_tokens_details') or {}).get('reasoning_tokens') or 0 for c in logs),
            'call_seconds': sum(c.get('latency_seconds',0) for c in logs),
            'transport_errors': sum(bool(c.get('error')) for c in logs)}


def summarize(run_dir, offline=False):
    root = Path(run_dir); m = verify(root); cfg = m['identity']['config']
    labels = json.loads((root/'labels.json').read_text())
    mode = root / ('offline' if offline else 'live'); mode.mkdir(parents=True, exist_ok=True)
    report = {'run_id': m['run_id'], 'offline': offline,
              'interpretation': 'SYNTHETIC OFFLINE TEST; not model results' if offline else 'Exploratory text-only pilot',
              'scheduled': len(m['evaluation'])*len(ARMS)*cfg['repetitions'],
              'missing': 0, 'arms': {}, 'comparisons': {},
              'taxonomy_codes': m['taxonomy_codes'], 'exclusion_counts': dict(Counter(e['reason'] for e in m['excluded'])),
              'dataset_revision': cfg['dataset_revision'], 'code_hash': m['identity']['code_hash'],
              'uncertainty': 'Paired framework-stratified task-group bootstrap, fixed gold-supported modes; exploratory unadjusted 95% intervals for two comparisons, not confirmatory significance tests.'}
    paired, csv_rows = {}, []
    for arm in ARMS:
        rows, successful, logs = [], [], []
        counts = Counter(); wall = []
        for rep in range(cfg['repetitions']):
            for entry in m['evaluation']:
                name = result_name(arm, entry['case_id'], rep)
                path = mode/'results'/f'{name}.json'
                record = json.loads(path.read_text()) if path.exists() else {}
                if record and (record.get('run_id') != m['run_id'] or record.get('offline') != offline):
                    raise ValueError('Report encountered a mismatched result')
                status = record.get('status', 'missing'); counts[status] += 1
                sc = record.get('score') or {}; pred = record.get('prediction') or {}
                row = {'fw': entry['framework'], 'modality': entry['modality'], 'group': entry['group'],
                       'case_id': entry['case_id'], 'repetition': rep,
                       'a_correct': bool(sc.get('agent')), 's_correct': bool(sc.get('step')),
                       'm_correct': bool(sc.get('mode')), 'gt_mode': labels[entry['case_id']]['mode'],
                       'pr_mode': pred.get('error_mode') or '__INVALID__'}
                rows.append(row)
                if status == 'completed': successful.append(row)
                if record.get('valid_fields'): counts['valid_fields'] += 1
                if record: wall.append(record.get('wall_seconds', 0))
                audit = mode/'calls'/f'{name}.jsonl'
                if audit.exists():
                    for line in audit.read_text().splitlines():
                        try: logs.append(json.loads(line))
                        except json.JSONDecodeError: counts['incomplete_audit_lines'] += 1
        paired[arm] = rows; report['missing'] += counts['missing']
        avg, by_rep = repeated_metrics(rows)
        per_mode = mode_counts(rows)
        confusion = defaultdict(Counter)
        for r in rows: confusion[r['gt_mode']][r['pr_mode']] += 1
        report['arms'][arm] = {'metrics': avg, 'per_repetition': by_rep,
            'completed': counts['completed'], 'failed': counts['failed'], 'missing': counts['missing'],
            'completion_rate': counts['completed']/len(rows), 'valid_output_rate': counts['valid_fields']/len(rows),
            'upstream_compatible_successful_records': repeated_metrics(successful)[0],
            'per_mode': per_mode, 'confusion': dict(confusion), 'resources': _usage(logs),
            'wall_seconds': sum(wall), 'incomplete_audit_lines': counts['incomplete_audit_lines']}
        for rep in range(cfg['repetitions']):
            for label, values in mode_counts([r for r in rows if r['repetition']==rep]).items():
                csv_rows.append({'arm': arm, 'repetition': rep, 'mode': label, **values})
    report['complete'] = report['missing'] == 0
    for arm in ARMS[1:]:
        delta = report['arms'][arm]['metrics']['What'] - report['arms']['baseline']['metrics']['What']
        report['comparisons'][arm] = {'delta_f1': delta, 'interval_95': paired_interval(
            paired['baseline'], paired[arm], cfg['bootstrap_samples'], cfg['seed']) if report['complete'] else None}
    budget = mode/'budget.json'
    report['budget'] = json.loads(budget.read_text()) if budget.exists() else None
    atomic_json(mode/'report.json', report)
    with (mode/'per-mode.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['arm','repetition','mode','support','precision','recall','f1'])
        writer.writeheader(); writer.writerows(csv_rows)
    def fmt(v): return 'N/A' if v is None else f'{100*v:.2f}%'
    md = ['# Judge harness experiment', '', '**'+report['interpretation']+'**', '',
          'Complete scheduled cohort.' if report['complete'] else '**INCOMPLETE RUN: missing outcomes count wrong provisionally; no comparative conclusion.**', '',
          '| Harness | Who | When | What macro-F1 | All | Completed | Attempts |',
          '|---|---:|---:|---:|---:|---:|---:|']
    for arm, a in report['arms'].items():
        md.append(f'| {arm} | '+ ' | '.join(fmt(a['metrics'][x]) for x in AXES)
                  +f' | {a["completed"]}/{len(paired[arm])} | {a["resources"]["attempts"]} |')
    md += ['', '## Paired changes from baseline', '', '| Harness | F1 change (percentage points) | Exploratory 95% interval |', '|---|---:|---|']
    for arm, comparison in report['comparisons'].items():
        ci = comparison['interval_95']
        md.append(f'| {arm} | {comparison["delta_f1"]*100:+.2f} | '+
                  (f'[{ci[0]*100:+.2f}, {ci[1]*100:+.2f}]' if ci else 'Unavailable: incomplete')+' |')
    md += ['', report['uncertainty'], '',
           'Primary scores retain failures and missing results in the denominator. Successful-record-only scores, resource usage, per-repetition results, confusion matrices, taxonomy and exclusions are in report.json. Per-mode precision/recall/F1 are in per-mode.csv.', '',
           'This short-trace pilot is not a full-benchmark reproduction. More calls are part of the harness treatment; compute is not matched. Hosted model weights cannot be independently verified.']
    (mode/'report.md').write_text('\n'.join(md)+'\n')
    return report
