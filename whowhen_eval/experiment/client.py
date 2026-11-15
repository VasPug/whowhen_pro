"""Explicit OpenRouter transport, persistent cost reservations, and offline fixture mode."""
import json
import os
from pathlib import Path
import re
import socket
import time
import urllib.error
import urllib.request
import uuid

from .data import atomic_json, digest


class ProviderError(RuntimeError):
    pass


class BudgetExceeded(ProviderError):
    pass


class FatalProviderError(ProviderError):
    """Run-level setup/account error; do not cache a failed experiment outcome."""


def validate_credentials(cfg):
    key = os.environ.get('OPENROUTER_API_KEY', '').strip()
    if not key: raise FatalProviderError('Set OPENROUTER_API_KEY before a live run')
    request = urllib.request.Request('https://openrouter.ai/api/v1/key',
                                     headers={'Authorization': f'Bearer {key}'})
    try:
        with urllib.request.urlopen(request, timeout=cfg['timeout']) as response:
            result = json.load(response)
    except urllib.error.HTTPError as e:
        raise FatalProviderError(f'OpenRouter key preflight failed (HTTP {e.code}); no experiment outcomes cached') from None
    except Exception:
        raise FatalProviderError('OpenRouter key preflight unavailable; no experiment outcomes cached') from None
    data = result.get('data')
    if not isinstance(data, dict): raise FatalProviderError('Unexpected OpenRouter key preflight response')
    if data.get('limit') is not None and data.get('limit_remaining') is not None and data['limit_remaining'] <= 0:
        raise FatalProviderError('OpenRouter key spending limit exhausted; no experiment outcomes cached')


def collapse_attempts(events):
    """One report row per attempt, including starts lacking a completion record."""
    attempts = {}
    for index, row in enumerate(events):
        attempts[row.get('attempt_id', f'legacy-{index}')] = row
    out = []
    for row in attempts.values():
        if row.get('phase') == 'started':
            row = {**row, 'unknown_outcome': True, 'error': 'Interrupted attempt; usage/outcome unknown'}
        out.append(row)
    return out


def openrouter_transport(payload, key, timeout):
    request = urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',
        data=json.dumps(payload).encode(), headers={'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json', 'X-Title': 'WhoWhen judge harness experiment'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _offline(role, parts):
    if role == 'requirements': return json.dumps({'requirements': []})
    if role == 'constraints': return json.dumps({'constraints': []})
    if role == 'semantic':
        return json.dumps({'result': 'inconclusive', 'reason': 'OFFLINE synthetic check', 'evidence': []})
    if role.startswith('review_'):
        return json.dumps({'verdict': 'challenge', 'reason': 'OFFLINE synthetic review', 'evidence': []})
    text = '\n'.join(p.get('text', '') for p in parts)
    match = re.search(r'^Step\s+(\S+)\s*\|\s*Agent:\s*(\S+)', text, re.M)
    coord, agent = match.groups() if match else ('1', 'agent')
    mode = re.search(r'(?<!\w)([A-Z]+\.\d+)(?!\w)', text)
    return (f'Agent Name: {agent}\nStep Number: {coord}\nError Mode: {mode.group(1) if mode else "R.2"}'
            '\nReason: OFFLINE SYNTHETIC RESPONSE; not model evaluation.')


class Client:
    """Sequential client. The runner holds an exclusive lock for the shared budget."""
    def __init__(self, config, audit_path, budget_path, offline=False, transport=None, sleep=time.sleep):
        self.cfg = config
        self.audit_path, self.budget_path = Path(audit_path), Path(budget_path)
        self.offline, self.transport, self.sleep = offline, transport or openrouter_transport, sleep
        self.key = None if offline else os.environ.get('OPENROUTER_API_KEY', '').strip()
        if not offline and not self.key:
            raise ProviderError('Set OPENROUTER_API_KEY to run live; --offline needs no key')

    def _reserve(self, payload):
        # UTF-8 bytes upper-bound ordinary text tokens, with ample framing allowance.
        input_bound = len(json.dumps(payload['messages'], ensure_ascii=False).encode()) + 1024
        amount = (input_bound * self.cfg['input_price_per_million']
                  + self.cfg['max_tokens'] * self.cfg['output_price_per_million']) / 1_000_000
        state = json.loads(self.budget_path.read_text()) if self.budget_path.exists() else {
            'reserved_usd': 0.0, 'attempts': 0, 'policy': 'no refunds; failed attempts remain reserved'}
        if state['reserved_usd'] + amount > self.cfg['max_cost_usd']:
            raise BudgetExceeded('Experiment reservation budget exhausted; no request was sent')
        state['reserved_usd'] += amount; state['attempts'] += 1
        atomic_json(self.budget_path, state)
        return amount

    def _record(self, value):
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if self.key: text = text.replace(self.key, '[REDACTED]')
        with self.audit_path.open('a') as f:
            f.write(text + '\n'); f.flush(); os.fsync(f.fileno())

    def __call__(self, role, parts):
        if not all(p.get('type') == 'text' and isinstance(p.get('text'), str) for p in parts):
            raise ProviderError('Text pilot requires text content only')
        if sum(len(p['text']) for p in parts) > self.cfg['max_input_chars']:
            raise ProviderError('Generated input exceeds configured limit; no silent truncation')
        payload = {'model': self.cfg['model'], 'messages': [{'role': 'user', 'content': parts}],
                   'temperature': self.cfg['temperature'], 'max_tokens': self.cfg['max_tokens'],
                   'seed': self.cfg['seed'], 'reasoning': {'enabled': False},
                   'provider': {'only': [self.cfg['provider']], 'allow_fallbacks': False,
                                'require_parameters': True,
                                'max_price': {'prompt': self.cfg['input_price_per_million'],
                                              'completion': self.cfg['output_price_per_million']}}}
        if self.offline:
            result = _offline(role, parts)
            self._record({'role': role, 'offline': True, 'phase': 'completed', 'attempt_id': uuid.uuid4().hex,
                          'request': payload, 'response': result,
                          'usage': None, 'latency_seconds': 0, 'attempt': 1, 'error': None})
            return result
        for attempt in range(1, self.cfg['retries'] + 2):
            reserved = self._reserve(payload)
            start = time.monotonic()
            row = {'role': role, 'offline': False, 'request_hash': digest(payload), 'request': payload,
                   'attempt': attempt, 'reserved_usd': reserved, 'usage': None, 'error': None,
                   'attempt_id': uuid.uuid4().hex, 'phase': 'started'}
            self._record(row)  # durable before the possibly billable request
            row['phase'] = 'completed'
            retry, fatal = False, False
            try:
                response = self.transport(payload, self.key, self.cfg['timeout'])
                row.update(returned_model=response.get('model'), returned_provider=response.get('provider'),
                           usage=response.get('usage'))
                if response.get('error'):
                    error = response['error']
                    code = error.get('code') if isinstance(error, dict) else None
                    if isinstance(code, int) or (isinstance(code, str) and code.isdigit()):
                        raise urllib.error.HTTPError('https://openrouter.ai', int(code), 'Provider error payload', {}, None)
                    raise ProviderError('Provider returned an unclassified error payload')
                if response.get('model') != self.cfg['model']: raise FatalProviderError('Returned model differs from frozen model')
                provider = response.get('provider')
                if provider and provider.lower() != self.cfg['provider'].split('/')[0].lower():
                    raise FatalProviderError('Returned provider differs from pinned provider')
                choices = response.get('choices') or []
                if not choices: raise ProviderError('Provider returned no completion')
                choice = choices[0]
                row['finish_reason'] = choice.get('finish_reason')
                result = (choice.get('message') or {}).get('content')
                row['response'] = result
                if choice.get('finish_reason') in ('length', 'content_filter'):
                    raise ProviderError('Completion truncated or filtered')
                if not isinstance(result, str) or not result.strip(): raise ProviderError('Empty completion')
            except urllib.error.HTTPError as e:
                row['error'] = f'Provider HTTP {e.code}'
                retry = e.code in (408, 429, 500, 502, 503, 504)
                fatal = e.code in (400, 401, 402, 403, 404, 422)
            except (urllib.error.URLError, TimeoutError, socket.timeout):
                row['error'] = 'Provider network timeout/error'; retry = True
            except FatalProviderError as e:
                row['error'] = str(e); fatal = True
            except ProviderError as e:
                row['error'] = str(e)
            except Exception as e:
                row['error'] = f'Invalid provider response ({type(e).__name__})'
            row['latency_seconds'] = time.monotonic() - start
            self._record(row)
            if row['error'] is None: return result
            if fatal: raise FatalProviderError(row['error'])
            if not retry or attempt > self.cfg['retries']: raise ProviderError(row['error'])
            self.sleep(min(2 ** (attempt - 1), 8))
        raise AssertionError('unreachable')
