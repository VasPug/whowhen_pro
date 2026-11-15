import json
import urllib.error

import pytest

from whowhen_eval.experiment.client import Client, BudgetExceeded, ProviderError
from whowhen_eval.experiment.config import load_config


def response(cfg, usage=True):
    r = {'model': cfg['model'], 'provider': 'Alibaba',
         'choices': [{'message': {'content': 'answer'}, 'finish_reason': 'stop'}]}
    if usage: r['usage'] = {'prompt_tokens': 10, 'completion_tokens': 3, 'total_tokens': 13, 'cost': 0.00001}
    return r


def client(tmp_path, monkeypatch, transport, **overrides):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-secret-key')
    cfg = load_config(); cfg.update(overrides)
    return Client(cfg, tmp_path/'calls.jsonl', tmp_path/'budget.json', transport=transport, sleep=lambda _: None)


def test_client_pins_routing_and_never_logs_key(tmp_path, monkeypatch):
    requests = []
    def transport(payload, key, timeout):
        requests.append(payload)
        assert key == 'test-secret-key'
        return response(load_config())
    c = client(tmp_path, monkeypatch, transport)
    assert c('baseline', [{'type':'text', 'text':'task'}]) == 'answer'
    assert requests[0]['provider']['only'] == ['alibaba']
    assert requests[0]['provider']['allow_fallbacks'] is False
    assert requests[0]['provider']['require_parameters'] is True
    assert requests[0]['reasoning'] == {'enabled': False}
    assert 'test-secret-key' not in (tmp_path/'calls.jsonl').read_text()


def test_missing_key_is_clear(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    with pytest.raises(ProviderError, match='OPENROUTER_API_KEY'):
        Client(load_config(), tmp_path/'calls', tmp_path/'budget')


def test_retries_are_counted_and_reservation_survives_resume(tmp_path, monkeypatch):
    requests = []
    def transport(*args):
        requests.append(1)
        if len(requests) == 1: raise urllib.error.HTTPError('https://api', 429, 'rate limit', {}, None)
        return response(load_config(), usage=False)
    c = client(tmp_path, monkeypatch, transport)
    c('x', [{'type':'text','text':'hello'}])
    before = json.loads((tmp_path/'budget.json').read_text())['reserved_usd']
    assert len(requests) == 2 and before > 0
    again = client(tmp_path, monkeypatch, transport)
    again('x', [{'type':'text','text':'hello'}])
    assert json.loads((tmp_path/'budget.json').read_text())['reserved_usd'] > before
    calls = [json.loads(l) for l in (tmp_path/'calls.jsonl').read_text().splitlines()]
    assert calls[-1]['usage'] is None


def test_budget_and_input_cap_prevent_transport(tmp_path, monkeypatch):
    def forbidden(*args): pytest.fail('transport must not run')
    c = client(tmp_path, monkeypatch, forbidden, max_cost_usd=0.000001)
    with pytest.raises(BudgetExceeded): c('x',[{'type':'text','text':'task'}])
    c = client(tmp_path, monkeypatch, forbidden, max_input_chars=1)
    with pytest.raises(ProviderError, match='input'): c('x',[{'type':'text','text':'task'}])


def test_nonretryable_error_is_sanitized(tmp_path, monkeypatch):
    def bad(*args): raise urllib.error.HTTPError('https://test-secret-key@api', 401, 'test-secret-key', {}, None)
    c = client(tmp_path, monkeypatch, bad)
    with pytest.raises(ProviderError, match='401'): c('x',[{'type':'text','text':'hello'}])
    assert 'test-secret-key' not in (tmp_path/'calls.jsonl').read_text()
    from whowhen_eval.experiment.client import collapse_attempts
    assert len(collapse_attempts([json.loads(l) for l in (tmp_path/'calls.jsonl').read_text().splitlines()])) == 1


def test_response_model_mismatch_fails(tmp_path, monkeypatch):
    def wrong(*args): return {**response(load_config()), 'model': 'different-model'}
    c = client(tmp_path, monkeypatch, wrong)
    with pytest.raises(ProviderError, match='model'): c('x',[{'type':'text','text':'hello'}])


def test_offline_never_needs_key(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    c = Client(load_config(), tmp_path/'calls', tmp_path/'budget', offline=True)
    result = c('baseline',[{'type':'text','text':'Step 1 | Agent: agent\nError: R.2'}])
    assert 'OFFLINE' in result
    assert json.loads((tmp_path/'calls').read_text())['offline'] is True
    assert not (tmp_path/'budget').exists()


def test_auth_preflight_uses_nonbillable_key_endpoint(monkeypatch):
    from whowhen_eval.experiment.client import validate_credentials
    monkeypatch.setenv('OPENROUTER_API_KEY', 'secret')
    seen = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{"data":{"limit":null,"limit_remaining":null}}'
    def open_url(request, timeout):
        seen.append(request)
        return Response()
    monkeypatch.setattr('urllib.request.urlopen', open_url)
    validate_credentials(load_config())
    assert seen[0].full_url == 'https://openrouter.ai/api/v1/key'
    assert seen[0].get_method() == 'GET'


def test_interrupted_transport_has_persistent_started_attempt(tmp_path, monkeypatch):
    def interrupt(*args): raise KeyboardInterrupt()
    c = client(tmp_path, monkeypatch, interrupt)
    with pytest.raises(KeyboardInterrupt): c('constraints', [{'type':'text', 'text':'trace'}])
    lines = [json.loads(l) for l in (tmp_path/'calls.jsonl').read_text().splitlines()]
    assert len(lines) == 1 and lines[0]['phase'] == 'started'
    assert lines[0]['attempt_id'] and lines[0]['role'] == 'constraints'
    assert json.loads((tmp_path/'budget.json').read_text())['attempts'] == 1


def test_transient_payload_error_retries_like_http_status(tmp_path, monkeypatch):
    calls = []
    def transport(*args):
        calls.append(1)
        return {'error': {'code': 503, 'message': 'server overloaded'}} if len(calls)==1 else response(load_config())
    c = client(tmp_path, monkeypatch, transport)
    assert c('x', [{'type':'text', 'text':'trace'}]) == 'answer'
    assert len(calls) == 2
