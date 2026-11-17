import pytest
from whowhen_eval.experiment.validation_probe import review_parts, assess, schema_for
from tests.test_experiment_data import release, taxonomy
from whowhen_eval.experiment.data import bundle


def test_clean_review_has_no_baseline_output_instruction(release,taxonomy):
    parts=review_parts(bundle(release,taxonomy),taxonomy,{'error_mode':'R.2'},'fault','clean_quotes')
    text='\n'.join(p['text'] for p in parts)
    assert 'Agent Name:' not in text
    assert 'Step Number:' not in text
    assert 'support|challenge|inconclusive' in text
    assert 'SECRET_ANSWER' not in text


def test_ids_are_resolved_but_not_declared_semantically_correct():
    result=assess({'verdict':'support','reason':'Claim','evidence':[{'ref':'event:0'}]},
                  {'event:0':'Original text'},'review','ids')
    assert result['shape_valid'] and result['grounded']
    assert result['evidence'][0]['quote']=='Original text'
    assert result['semantic_support_verified'] is False


def test_invalid_ids_remain_invalid():
    result=assess({'verdict':'support','reason':'Claim','evidence':[{'ref':'event:9'}]},
                  {'event:0':'Original text'},'review','ids')
    assert result['shape_valid'] and not result['grounded']


def test_schema_is_limited_to_actual_available_refs():
    schema=schema_for('review','ids',['task','event:0'])['json_schema']['schema']
    item=schema['properties']['evidence']['items']
    assert item['properties']['ref']['enum']==['task','event:0']
    assert 'quote' not in item['properties']

from tests.test_experiment_runner import prepared


def test_probe_locks_budget_before_reading_inputs(tmp_path):
    from whowhen_eval.experiment.runner import run_lock
    from whowhen_eval.experiment.validation_probe import live
    with run_lock(tmp_path/'out'):
        with pytest.raises(RuntimeError,match='running'):
            live(tmp_path/'missing',tmp_path/'out')


def test_probe_rejects_modified_taxonomy_before_auth(prepared,tmp_path,monkeypatch):
    import whowhen_eval.experiment.validation_probe as probe
    p=prepared/'taxonomy.yaml';p.write_text(p.read_text()+'\n# changed\n')
    monkeypatch.setattr(probe,'validate_credentials',lambda _:pytest.fail('Auth must not run'))
    with pytest.raises(ValueError,match='taxonomy'):probe.live(prepared,tmp_path/'out')


def test_semantic_variants_share_requirements(prepared,tmp_path,monkeypatch):
    import json
    import whowhen_eval.experiment.validation_probe as probe
    from tests.test_experiment_harnesses import ANSWER
    payloads=[]
    class FakeClient:
        def __init__(self,*args,**kwargs):pass
        def __call__(self,role,parts,*,response_format=None):
            if role=='initial':return ANSWER
            style=response_format['json_schema']['name'] if response_format else ''
            if role=='requirements':
                source={'ref':'task'}
                if style.endswith('quotes'):source['quote']='500 pounds'
                return json.dumps({'requirements':[{'text':style,'source':source}]})
            if role=='semantic':
                assert 'Return JSON' in parts[0]['text']
                payloads.append(json.loads(parts[0]['text'].split('\nDATA:\n')[1]))
                return json.dumps({'result':'inconclusive','reason':'Unknown','evidence':[]})
            return json.dumps({'verdict':'inconclusive','reason':'Unknown','evidence':[]})
    monkeypatch.setattr(probe,'Client',FakeClient)
    monkeypatch.setattr(probe,'validate_credentials',lambda _:None)
    probe.live(prepared,tmp_path/'out')
    assert len(payloads)==4
    assert payloads[0]['requirements']==payloads[1]['requirements']
    assert payloads[2]['requirements']==payloads[3]['requirements']
