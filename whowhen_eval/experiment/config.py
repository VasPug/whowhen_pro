"""Explicit pilot defaults. Credentials are never part of configuration."""
from pathlib import Path
import math
import yaml

DEFAULTS = {
    'model': 'qwen/qwen3.5-122b-a10b', 'provider': 'alibaba',
    'dataset_revision': '0bd196c8a040841c4ae167ab33cc8151de246f1f',
    'text_sha256': '51403bfd1b6570d0a9f8e62d25a50aa62504cb1264c33a3627ead893b7e2dd51',
    'taxonomy_sha256': 'f5d77edee84622e025519c31404a5b741ff4e008171392e35df0cceebd41d140',
    'modality': 'text', 'sample_size': 24, 'dev_size': 6, 'repetitions': 1,
    'seed': 20261115, 'temperature': 0.0, 'max_tokens': 2048,
    'max_steps': 12, 'max_source_chars': 12000, 'max_input_chars': 60000,
    'max_constraints': 3, 'max_evidence_chars': 12000,
    'review_cycles': 2, 'timeout': 120, 'retries': 2, 'max_cost_usd': 25.0,
    'input_price_per_million': 0.26, 'output_price_per_million': 2.08,
    'bootstrap_samples': 1000,
}
ARMS = ('baseline', 'agentrx', 'raffles')


def load_config(path=None):
    cfg = dict(DEFAULTS)
    supplied = yaml.safe_load(Path(path).read_text()) if path else {}
    if supplied is None: supplied = {}
    if not isinstance(supplied, dict): raise ValueError('Config must be a mapping')
    unknown = set(supplied) - set(cfg)
    if unknown: raise ValueError(f'Unknown configuration keys: {sorted(unknown)}')
    cfg.update(supplied)
    if cfg['modality'] != 'text': raise ValueError('Initial experiment supports text only')
    for key in ('sample_size', 'repetitions', 'max_tokens', 'max_steps', 'max_source_chars',
                'max_input_chars', 'max_constraints', 'max_evidence_chars', 'timeout', 'bootstrap_samples'):
        if type(cfg[key]) is not int or cfg[key] < 1: raise ValueError(f'{key} must be a positive integer')
    for key in ('dev_size', 'retries', 'seed'):
        if type(cfg[key]) is not int or cfg[key] < 0: raise ValueError(f'{key} must be a nonnegative integer')
    if cfg['review_cycles'] != 2: raise ValueError('This version implements exactly two review cycles')
    for key in ('max_cost_usd', 'input_price_per_million', 'output_price_per_million', 'temperature'):
        v = cfg[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            raise ValueError(f'{key} must be a finite nonnegative number')
    if cfg['max_cost_usd'] <= 0: raise ValueError('max_cost_usd must be positive')
    if cfg['temperature'] > 2: raise ValueError('temperature must be at most 2')
    for key in ('model', 'provider', 'dataset_revision'):
        if not isinstance(cfg[key], str) or not cfg[key].strip(): raise ValueError(f'{key} must be nonempty')
    return cfg
