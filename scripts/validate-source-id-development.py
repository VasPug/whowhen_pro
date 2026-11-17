"""Run all three complete harnesses on the existing development partition only."""
import argparse
from collections import Counter
import json
from pathlib import Path

from whowhen_eval.prompts import load_taxonomy
from whowhen_eval.experiment.client import Client,ProviderError,FatalProviderError,BudgetExceeded,validate_credentials,collapse_attempts
from whowhen_eval.experiment.config import ARMS
from whowhen_eval.experiment.data import atomic_json,code_hash,file_hash
from whowhen_eval.experiment.harnesses import run_harness
from whowhen_eval.experiment.runner import run_lock


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--parent',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();root=args.out
    with run_lock(root):
        m=json.loads((args.parent/'manifest.json').read_text());cfg={**m['identity']['config'],'max_cost_usd':5.0}
        if file_hash(args.parent/'taxonomy.yaml')!=m['identity']['files']['taxonomy']:raise ValueError('Taxonomy changed')
        for entry in m['development']:
            if file_hash(args.parent/'cases'/f"{entry['case_id']}.json")!=m['case_hashes'][entry['case_id']]:raise ValueError('Case changed')
        identity={'parent':m['run_id'],'config':cfg,'case_ids':[e['case_id'] for e in m['development']],
            'case_hashes':{e['case_id']:m['case_hashes'][e['case_id']] for e in m['development']},
            'taxonomy_hash':file_hash(args.parent/'taxonomy.yaml'),'code_hash':code_hash(),'script_hash':file_hash(Path(__file__))}
        manifest=root/'manifest.json'
        if manifest.exists() and json.loads(manifest.read_text())!=identity:raise ValueError('Development identity changed')
        atomic_json(manifest,identity);validate_credentials(cfg);taxonomy=load_taxonomy(args.parent)
        for entry in m['development']:
            cid=entry['case_id'];case=json.loads((args.parent/'cases'/f'{cid}.json').read_text())
            for arm in ARMS:
                name=f'{arm}__{cid}';dest=root/'results'/f'{name}.json'
                if dest.exists():continue
                c=Client(cfg,root/'calls'/f'{name}.jsonl',root/'budget.json')
                rec={'case_id':cid,'arm':arm}
                try:rec.update(run_harness(arm,case,taxonomy,cfg,c));rec['status']='completed'
                except (FatalProviderError,BudgetExceeded):raise
                except ProviderError as e:rec.update(status='failed',error=str(e))
                atomic_json(dest,rec)
                print(name+': '+rec['status']+', warnings='+str(len(rec.get('audit',{}).get('parse_warnings',[]))),flush=True)
        counts=Counter();warnings=Counter();attempts=[]
        for p in (root/'results').glob('*.json'):
            r=json.loads(p.read_text());counts[r['status']]+=1
            warnings[r['arm']]+=len(r.get('audit',{}).get('parse_warnings',[]))
        for p in (root/'calls').glob('*.jsonl'):
            attempts+=collapse_attempts([json.loads(l) for l in p.read_text().splitlines()])
        summary={'counts':dict(counts),'warnings':dict(warnings),'calls':len(attempts),
            'reported_cost_usd':sum((a.get('usage') or {}).get('cost') or 0 for a in attempts),
            'attempts_without_cost':sum((a.get('usage') or {}).get('cost') is None for a in attempts),
            'interpretation':'Development workflow smoke test, not benchmark scores'}
        atomic_json(root/'summary.json',summary);print(json.dumps(summary,indent=2))
        return 0 if counts['completed']==len(m['development'])*len(ARMS) else 3

if __name__=='__main__':raise SystemExit(main())
