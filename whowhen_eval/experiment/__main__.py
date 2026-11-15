"""python -m whowhen_eval.experiment prepare|doctor|run|report"""
import argparse
import json
import os
from pathlib import Path
import sys

from .config import load_config
from .data import ensure_data, prepare
from .runner import run, verify
from .report import summarize
from .client import ProviderError


def main(argv=None):
    p = argparse.ArgumentParser(description='Frozen Qwen judge-harness pilot (text only)')
    p.add_argument('command', choices=['prepare','doctor','run','report'])
    p.add_argument('--config', type=Path)
    p.add_argument('--data-root', type=Path, default=Path('experiment-data'))
    p.add_argument('--run-root', type=Path, default=Path('experiment-runs'))
    p.add_argument('--run-dir', type=Path, help='Use an already prepared experiment')
    p.add_argument('--offline', action='store_true', help='Synthetic responses only; never a model evaluation')
    args = p.parse_args(argv)
    try:
        # Fail before download/setup when credentials are the only missing prerequisite.
        if args.command == 'run' and not args.offline and not os.environ.get('OPENROUTER_API_KEY','').strip():
            raise ProviderError('Set OPENROUTER_API_KEY or use --offline for synthetic validation')
        if args.run_dir:
            root = args.run_dir
            if args.config and verify(root)['identity']['config'] != load_config(args.config):
                raise ValueError('Config differs from prepared experiment')
        else:
            cfg = load_config(args.config)
            ensure_data(cfg, args.data_root)
            root = prepare(cfg, args.data_root, args.run_root)
        if args.command == 'prepare': print(root.resolve())
        elif args.command == 'doctor':
            m = verify(root)
            print(json.dumps({'ready': True, 'run_dir': str(root.resolve()),
                'evaluation_cases':len(m['evaluation']), 'development_cases':len(m['development']),
                'taxonomy_modes':len(m['taxonomy_codes']), 'model':m['identity']['config']['model'],
                'provider':m['identity']['config']['provider'],
                'api_key_present':bool(os.environ.get('OPENROUTER_API_KEY','').strip()),
                'live_authentication_tested':False}, indent=2))
        else:
            result = run(root, args.offline) if args.command == 'run' else summarize(root, args.offline)
            print('Report:', (root/('offline' if args.offline else 'live')/'report.md').resolve())
            if result['missing']: return 2
            if any(a['failed'] for a in result['arms'].values()): return 3
        return 0
    except (ValueError, RuntimeError, OSError) as e:
        # Known local diagnostics only; HTTP errors can carry credential-bearing URLs.
        if isinstance(e, (ValueError, ProviderError, RuntimeError)):
            print(f'Error: {e}', file=sys.stderr)
        else: print(f'Error: {type(e).__name__}; check dataset/network access and paths', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Interrupted. Completed results and spending reservations are preserved; rerun to resume.', file=sys.stderr)
        return 130


if __name__ == '__main__': raise SystemExit(main())
