"""Pinned data, baseline-visible cases, and label-independent cohort selection."""
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import re
import tempfile
import urllib.request
from collections import defaultdict, Counter

from ..prompts import all_at_once, load_taxonomy
from ..render import get_renderer
from ..render.base import TASK_ANCHOR
from ..run import release_from_row


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def code_hash():
    root = Path(__file__).resolve().parents[1]
    return digest({str(p.relative_to(root)): file_hash(p) for p in sorted(root.rglob('*.py'))})


def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.'+path.name)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def json_file_hash(value):
    content = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    return hashlib.sha256(content.encode()).hexdigest()


def download_verified(url, path, expected):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and file_hash(path) == expected: return
    fd, tmp = tempfile.mkstemp(dir=path.parent); os.close(fd)
    try:
        urllib.request.urlretrieve(url, tmp)
        if file_hash(tmp) != expected: raise ValueError(f'Download checksum mismatch: {path.name}')
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def ensure_data(cfg, root):
    root = Path(root)
    base = f'https://huggingface.co/datasets/Leoxx/whowhen_pro/resolve/{cfg["dataset_revision"]}'
    for rel, key in [('data/text.jsonl', 'text_sha256'), ('taxonomy.yaml', 'taxonomy_sha256')]:
        if not cfg[key]: raise ValueError('Verified downloads require both dataset checksums')
        download_verified(f'{base}/{rel}', root / rel, cfg[key])


_HIDDEN = {'ground_truth', 'accepted_predictions', 'is_injected', 'injected', 'is_replayed',
           'injection_via', 'post_injection_turns', 'eval_status', 'eval_error_preview',
           'error_code_original', 'error_scope', 'gt_agent', 'source', 'trace_id', 'task_id', 'id'}


def _clean(value):
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if k not in _HIDDEN}
    if isinstance(value, list): return [_clean(x) for x in value]
    return value


def bundle(release, taxonomy):
    clean = _clean(copy.deepcopy(release))
    clean['task'].pop('answer', None)
    rr = get_renderer(clean['framework'])(clean)
    if any(b.images for b in rr.blocks): raise ValueError('Text pilot cannot silently drop images')
    events = []
    native = dict(rr.step_index)
    for block in rr.blocks:
        if block.coord in (None, TASK_ANCHOR): continue
        text = block.text + ('\n' + block.body_text if block.body_text else '')
        match = re.search(r'^Step\s+\S+\s*\|\s*Agent:\s*(\S+)', text)
        if not match: raise ValueError('Cannot recover agent from renderer header')
        events.append({'ref': f'event:{len(events)}', 'coord': block.coord,
                       'native_coord': list(native.get(block.coord, ())),
                       'agent': match.group(1), 'text': text})
    parts = all_at_once(rr, problem=clean['task'].get('query') or '', taxonomy=taxonomy)
    case = {'task': clean['task'].get('query') or '', 'events': events,
            'step_format_hint': rr.step_format_hint, 'baseline_parts': parts}
    case['source_hash'] = digest(case)
    return case


def prepare(cfg, data_root, run_root):
    data_root, run_root = Path(data_root), Path(run_root)
    hashes = {'text': file_hash(data_root / 'data/text.jsonl'),
              'taxonomy': file_hash(data_root / 'taxonomy.yaml')}
    for key in hashes:
        expected = cfg[f'{key}_sha256']
        if expected and expected != hashes[key]: raise ValueError(f'{key} checksum mismatch')
    identity = {'config': cfg, 'files': hashes, 'code_hash': code_hash()}
    taxonomy = load_taxonomy(data_root)
    candidates, excluded, all_modes = [], [], Counter()
    seen = set()
    with (data_root / 'data/text.jsonl').open() as f:
        for line_number, line in enumerate(f, 1):
            if not line.strip(): continue
            row = json.loads(line)
            if row['id'] in seen: raise ValueError('Duplicate dataset trace ID')
            seen.add(row['id'])
            release = release_from_row(row, 'text', data_root)
            gt = release['ground_truth']; all_modes[gt.get('mode')] += 1
            if gt.get('mode') not in taxonomy.codes: raise ValueError('Gold mode absent from pinned taxonomy')
            try:
                case = bundle(release, taxonomy)
                if not case['task'] or not case['events']: raise ValueError('empty task/steps')
                if len(case['events']) > cfg['max_steps']: raise ValueError('step limit')
                if sum(len(p.get('text', '')) for p in case['baseline_parts']) > cfg['max_source_chars']:
                    raise ValueError('source character limit')
            except (ValueError, KeyError) as e:
                excluded.append({'trace_id': row['id'], 'reason': str(e)[:160]}); continue
            group = digest([row['benchmark'], ' '.join(case['task'].split())])
            candidates.append({'trace_id': row['id'], 'framework': row['framework'],
                               'benchmark': row['benchmark'], 'modality': 'text', 'group': group,
                               'case': case, 'ground_truth': gt, 'line': line_number})
    # Randomize before selecting one variant per source task; no label-based selection.
    rng = random.Random(cfg['seed']); rng.shuffle(candidates)
    unique, groups = [], set()
    for c in candidates:
        if c['group'] in groups: continue
        groups.add(c['group']); unique.append(c)
    buckets = defaultdict(list)
    for c in unique: buckets[c['framework']].append(c)
    order = []
    while any(buckets.values()):
        for fw in sorted(buckets):
            if buckets[fw]: order.append(buckets[fw].pop())
    needed = cfg['sample_size'] + cfg['dev_size']
    if len(order) < needed: raise ValueError(f'Only {len(order)} eligible task groups; need {needed}')
    selected = order[:needed]
    manifest = {'taxonomy_codes': list(taxonomy.codes),
                'population_modes': dict(all_modes), 'eligible_groups': len(order),
                'excluded': excluded, 'evaluation': [], 'development': [], 'case_hashes': {}}
    labels, cases = {}, {}
    for index, c in enumerate(selected):
        cid = f'case-{index:04d}'
        entry = {k: c[k] for k in ('trace_id', 'framework', 'benchmark', 'modality', 'group')}
        entry.update(case_id=cid, source_hash=c['case']['source_hash'])
        partition = 'evaluation' if index < cfg['sample_size'] else 'development'
        manifest[partition].append(entry)
        cases[cid] = c['case']
        manifest['case_hashes'][cid] = json_file_hash(c['case'])
        labels[cid] = c['ground_truth']
    manifest['labels_hash'] = json_file_hash(labels)
    # Bind membership, grouping/framework metadata, and all prepared artifacts to
    # the same identity used by caches. A modified denominator cannot reuse a run.
    identity['prepared_hash'] = digest(manifest)
    run_id = digest(identity)
    manifest.update(run_id=run_id, identity=identity)
    out = run_root / run_id[:16]
    if (out / 'manifest.json').exists():
        from .runner import verify
        if verify(out) != manifest: raise ValueError('Manifest differs from prepared cohort')
        return out
    for cid, case in cases.items(): atomic_json(out / 'cases' / f'{cid}.json', case)
    atomic_json(out / 'labels.json', labels)
    (out / 'taxonomy.yaml').write_bytes((data_root / 'taxonomy.yaml').read_bytes())
    atomic_json(out / 'manifest.json', manifest)  # written last: marks preparation complete
    return out
