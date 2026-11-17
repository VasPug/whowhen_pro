"""Development-only format/evidence probes; never score these as a benchmark run."""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import difflib
import json
from pathlib import Path
import random

from ..parse import parse_all_at_once
from ..prompts import load_taxonomy
from .checks import json_object, citation, InvalidOutput
from .client import Client, ProviderError, FatalProviderError, BudgetExceeded, validate_credentials, collapse_attempts
from .data import atomic_json, code_hash, digest, file_hash
from .runner import run_lock
from .evidence import locate, normalized
from .harnesses import PREAMBLE, REVIEWERS, part, sources_for, _json_prompt

VARIANTS=('original_quotes','clean_quotes','schema_quotes','schema_ids')


from .contracts import schema_for


def review_parts(case,taxonomy,pred,name,variant):
    sources=sources_for(case)
    if variant=='original_quotes':
        instruction=('\nReview the candidate, do not produce a new attribution. '+REVIEWERS[name]+
            '\nReturn JSON {"verdict":"support|challenge|inconclusive", '
            '"reason":"brief reason", "evidence":[{"ref":"task or event:N", '
            '"quote":"exact span"}]}. Cite relevant source spans when available. '
            'Do not infer causality from confidence alone.\n')
        return case['baseline_parts']+[part(PREAMBLE+instruction+json.dumps({'candidate':pred,'sources':sources},ensure_ascii=False))]
    style='ids' if variant=='schema_ids' else 'quotes'
    evidence='[{"ref":"one available source ID"}]' if style=='ids' else '[{"ref":"one available source ID", "quote":"exact span"}]'
    instruction=('Review the candidate; do not produce a new attribution. '+REVIEWERS[name]+
        ' Return JSON {"verdict":"support|challenge|inconclusive", "reason":"brief reason", '
        '"evidence":'+evidence+'}. Cite relevant evidence for a conclusive verdict. '
        'Use inconclusive if evidence is insufficient. Source existence does not establish causality. '
        'Use only the exact source IDs provided; do not invent task:N aliases.')
    return _json_prompt(instruction,{'candidate':pred,'sources':sources,'taxonomy':taxonomy.block})


def assess(value,sources,kind,style):
    result={'shape_valid':False,'grounded':False,'strict_grounded':False,
            'usable':False,'semantic_support_verified':False,'evidence':[]}
    try:
        out=json_object(value) if isinstance(value,str) else value
        if not isinstance(out,dict):raise InvalidOutput('Expected object')
        if kind=='requirements':
            items=out.get('requirements')
            if not isinstance(items,list):raise InvalidOutput('Missing requirements list')
            if any(not isinstance(x,dict) or not isinstance(x.get('text'),str) or not x['text'].strip() for x in items):
                raise InvalidOutput('Malformed requirement')
            refs=[x.get('source') for x in items]; result['verdict']='requirements'
        else:
            key,allowed=('verdict',('support','challenge','inconclusive')) if kind=='review' else ('result',('satisfied','violated','inconclusive'))
            if out.get(key) not in allowed or not isinstance(out.get('reason'),str) or not out['reason'].strip():raise InvalidOutput('Missing verdict/reason')
            refs=out.get('evidence');result['verdict']=out[key]
            if not isinstance(refs,list):raise InvalidOutput('Missing evidence list')
        if any(not isinstance(x,dict) or not isinstance(x.get('ref'),str) or
               (style=='quotes' and not isinstance(x.get('quote'),str)) for x in refs):
            raise InvalidOutput('Malformed evidence reference')
        result['shape_valid']=True
        accepted=[]; strict=[]
        for ref in refs:
            if style=='ids':
                ok=ref['ref'] in sources
                accepted.append(ok);strict.append(ok)
                if ok:result['evidence'].append({'ref':ref['ref'],'quote':sources[ref['ref']],'method':'source_id'})
            else:
                try:citation(ref,sources);strict.append(True)
                except InvalidOutput:strict.append(False)
                located=locate(ref,sources,'aliases');accepted.append(located['status']=='matched')
                result['evidence'].append(located)
        result['grounded']=bool(refs) and all(accepted)
        result['strict_grounded']=bool(refs) and all(strict)
        result['usable']=result['grounded'] or (not refs and (kind=='requirements' or result['verdict']=='inconclusive'))
        result['parsed']=out
    except (InvalidOutput,TypeError) as e:result['error']=str(e)
    return result


def _references(value):
    if isinstance(value,dict):
        if 'ref' in value and 'quote' in value:yield value
        else:
            for x in value.values():yield from _references(x)
    elif isinstance(value,list):
        for x in value:yield from _references(x)


def fuzzy_score(quote,source):
    q=normalized(quote)[0];s=normalized(source)[0]
    if not q:return 0
    match=difflib.SequenceMatcher(None,q,s,autojunk=False).find_longest_match()
    start=max(0,match.b-match.a)
    return difflib.SequenceMatcher(None,q,s[start:start+len(q)],autojunk=False).ratio()


def offline(run_dir,out_dir):
    rows=[]
    for path in sorted((run_dir/'live/calls').glob('*.jsonl')):
        for lineno,line in enumerate(path.read_text().splitlines(),1):
            call=json.loads(line)
            if call.get('phase')!='completed' or call['role'] in ('baseline','initial','revision','final'):continue
            try:answer=json_object(call['response'])
            except InvalidOutput:continue
            prompt=call['request']['messages'][-1]['content'][-1]['text']
            data=json.loads(prompt.split('\nDATA:\n',1)[1]) if '\nDATA:\n' in prompt else json.loads(prompt[prompt.index('{"candidate":'):])
            sources=data.get('sources',{'task':data.get('task','')})
            for ref in _references(answer):
                try:citation(ref,sources);exact=True
                except InvalidOutput:exact=False
                policies={k:locate(ref,sources,k) for k in ('normalized','aliases','ellipsis')}
                rows.append({'file':path.name,'line':lineno,'role':call['role'],'reference':ref,'sources':sources,
                             'original_exact_accepted':exact,'policies':policies,
                             'fuzzy_diagnostic_score':fuzzy_score(ref['quote'],sources.get(ref['ref'],''))})
    counts={}
    rejected=[x for x in rows if not x['original_exact_accepted']]
    for policy in ('normalized','aliases','ellipsis'):
        counts[policy]=dict(Counter(x['policies'][policy]['status'] for x in rejected))
    # Predeclared negative controls: similarity is explicitly NOT a support test.
    negative=[('Price 620 pounds.','Price 20 pounds.'),('Price 620 pounds.','Price -620 pounds.'),
        ('Do not buy the ticket.','Do buy the ticket.'),('Use price <= 500.','Use price >= 500.'),
        ('The transfer must not be executed.','The transfer must be executed.'),
        ('The call fails unless the directory is current.','The call fails.'),
        ('Price 1,500 pounds.','500 pounds.'),('Amount 1e3 pounds.','3 pounds.'),('Amount 1e-3 pounds.','-3 pounds.'),
        ('Amount 1.5 pounds.','.5 pounds.'),('Amount 1e+3 pounds.','+3 pounds.')]
    controls=[]
    for source,quote in negative:
        controls.append({'source':source,'quote':quote,'expected':'unresolved',
            'result':locate({'ref':'event:0','quote':quote},{'event:0':source},'aliases'),
            'fuzzy_diagnostic_score':fuzzy_score(quote,source)})
    summary={'citations':len(rows),'originally_rejected_citations':len(rejected),
        'rejected_calls':len({(x['file'],x['line']) for x in rejected}),'recovery':counts,
        'previously_accepted_now_unresolved':sum(x['original_exact_accepted'] and x['policies']['aliases']['status']!='matched' for x in rows),
        'negative_controls':controls,'negative_controls_unexpected_matches':sum(x['result']['status']=='matched' for x in controls),
        'note':'Location recovery only; no final predictions re-scored. Fuzzy scores diagnostic, never accepted automatically.'}
    atomic_json(out_dir/'offline-citations.json',rows);atomic_json(out_dir/'offline-summary.json',summary)
    return summary


def live(run_dir,out_dir):
    with run_lock(out_dir):
        return _live_locked(run_dir,out_dir)


def _live_locked(run_dir,out_dir):
    manifest=json.loads((run_dir/'manifest.json').read_text());cfg={**manifest['identity']['config'],'max_cost_usd':5.0}
    taxonomy_hash=file_hash(run_dir/'taxonomy.yaml')
    if taxonomy_hash!=manifest['identity']['files']['taxonomy']:raise ValueError('Parent taxonomy changed')
    for entry in manifest['development']:
        if file_hash(run_dir/'cases'/f"{entry['case_id']}.json")!=manifest['case_hashes'][entry['case_id']]:
            raise ValueError('Parent case changed')
    taxonomy=load_taxonomy(run_dir)
    cases={e['case_id']:json.loads((run_dir/'cases'/f"{e['case_id']}.json").read_text()) for e in manifest['development']}
    identity={'parent_run':manifest['run_id'],'case_ids':list(cases),'case_hash':digest(cases),'taxonomy_hash':taxonomy_hash,'code_hash':code_hash(),'config':cfg,
              'purpose':'Development format/evidence probes; not benchmark results'}
    dst=out_dir/'probe-manifest.json'
    if dst.exists() and json.loads(dst.read_text())!=identity:raise ValueError('Probe identity changed; choose a new output directory')
    atomic_json(dst,identity);validate_credentials(cfg)
    def request(cid,variant,role,parts,schema=None):
        name=f'{cid}__{variant}__{role}'
        dest=out_dir/'responses'/f'{name}.json'
        fingerprint=digest({'parts':parts,'schema':schema})
        if dest.exists():
            record=json.loads(dest.read_text())
            if record['request_hash']!=fingerprint:raise ValueError('Cached probe request changed')
            return record
        client=Client(cfg,out_dir/'calls'/f'{name}.jsonl',out_dir/'budget.json')
        record={'case_id':cid,'variant':variant,'role':role,'request_hash':fingerprint}
        try:record['response']=client(role,parts,response_format=schema)
        except (FatalProviderError,BudgetExceeded):raise
        except ProviderError as e:record['error']=str(e)
        atomic_json(dest,record)
        print(name+': '+('completed' if 'response' in record else 'error'),flush=True)
        return record
    evaluations=[]
    rng=random.Random(cfg['seed']);case_ids=list(cases);rng.shuffle(case_ids)
    for cid in case_ids:
        case=cases[cid];sources=sources_for(case)
        baseline=request(cid,'shared','initial',case['baseline_parts'])
        if 'response' not in baseline:raise ProviderError('Shared diagnosis failed; cannot compare reviewers')
        pred=asdict(parse_all_at_once(baseline['response'],taxonomy.codes))
        jobs=[(variant,name) for variant in VARIANTS for name in REVIEWERS];rng.shuffle(jobs)
        for variant,name in jobs:
            style='ids' if variant=='schema_ids' else 'quotes'
            schema=schema_for('review',style,list(sources)) if variant.startswith('schema') else None
            rec=request(cid,variant,'review_'+name,review_parts(case,taxonomy,pred,name,variant),schema)
            evaluations.append({**rec,'assessment':assess(rec.get('response',''),sources,'review',style)})
        styles=['quotes','ids'];rng.shuffle(styles)
        requirements={}
        for style in styles:
            source_example='{"ref":"task"}' if style=='ids' else '{"ref":"task","quote":"exact task span"}'
            instruction=('Derive only explicit requirements from the task; at most three. Return JSON {"requirements":'
                         '[{"text":"requirement", "source":'+source_example+'}]}. An empty list is valid.')
            req=request(cid,'requirements_'+style,'requirements',_json_prompt(instruction,{'task':case['task']}),schema_for('requirements',style,['task']))
            a=assess(req.get('response',''),{'task':case['task']},'requirements',style)
            evaluations.append({**req,'assessment':a})
            requirements[style]=a
        shared=requirements['ids']
        if not shared['usable']:
            for style in styles:
                evaluations.append({'case_id':cid,'variant':'semantic_'+style,'role':'semantic',
                    'assessment':{'shape_valid':False,'usable':False,'error':'Shared requirement extraction unusable; skipped'}})
            continue
        shared_requirements=[{'text':r['text'],'source':{'ref':'task','quote':case['task']}} for r in shared['parsed']['requirements']]
        for style in styles:
            instruction=('Assess whether the TARGET event satisfies or violates the task requirements, using only recorded sources. '
                'Use inconclusive if not yet applicable, unsupported, or ambiguous. Agent claims alone do not prove external state. '
                'Return JSON with result satisfied|violated|inconclusive, reason, and evidence references. '
                +('Each reference contains only ref, an exact available source ID.' if style=='ids' else 'Each reference contains ref and an exact source quote.'))
            sem=request(cid,'semantic_'+style,'semantic',_json_prompt(instruction,
                {'sources':sources,'target':case['events'][-1]['ref'],'requirements':shared_requirements}),schema_for('semantic',style,list(sources)))
            evaluations.append({**sem,'assessment':assess(sem.get('response',''),sources,'semantic',style)})
    groups=defaultdict(Counter)
    for r in evaluations:
        c=groups[r['variant']];a=r['assessment'];c['outputs']+=1
        for key in ('shape_valid','grounded','strict_grounded','usable'):c[key]+=bool(a.get(key))
        c['verdict_'+a.get('verdict','invalid')]+=1
    attempts=[]
    for p in (out_dir/'calls').glob('*.jsonl'):
        attempts+=collapse_attempts([json.loads(l) for l in p.read_text().splitlines()])
    summary={'groups':{k:dict(v) for k,v in groups.items()},'calls':len(attempts),
        'reported_cost_usd':sum((r.get('usage') or {}).get('cost') or 0 for r in attempts),
        'calls_without_cost':sum(not isinstance((r.get('usage') or {}).get('cost'),(int,float)) for r in attempts),
        'provider_errors':sum(bool(r.get('error')) for r in attempts),'cases':case_ids,
        'limitation':'Six development cases, single outputs. Source validity is not semantic correctness; no final F1 evaluated.'}
    atomic_json(out_dir/'live-evaluations.json',evaluations);atomic_json(out_dir/'live-summary.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['offline','live']);parser.add_argument('--run-dir',type=Path,required=True);parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args();args.out_dir.mkdir(parents=True,exist_ok=True)
    print(json.dumps((offline if args.mode=='offline' else live)(args.run_dir,args.out_dir),indent=2))


if __name__=='__main__':main()
