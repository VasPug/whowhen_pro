import json
import pytest
from tests.test_experiment_data import release,taxonomy
from tests.test_experiment_harnesses import Scripted,ANSWER,numeric_constraint
from whowhen_eval.experiment.config import load_config
from whowhen_eval.experiment.data import bundle
from whowhen_eval.experiment.harnesses import run_harness
from whowhen_eval.experiment.checks import semantic_result,InvalidOutput


def test_semantic_resolves_strings_and_objects_to_original_text():
    sources={'event:0':'The original observation.'}
    for ref in ['event:0',{'ref':'event:0','quote':'FABRICATED','extra':'ignored'}]:
        r=semantic_result({'result':'violated','reason':'Reason','evidence':[ref]},sources)
        assert r['evidence']==[{'ref':'event:0','quote':'The original observation.'}]


@pytest.mark.parametrize('refs',[[],['event:99'],[{'ref':['event:0']}],['task:N']])
def test_review_cannot_support_with_unusable_evidence(refs):
    with pytest.raises(InvalidOutput):
        semantic_result({'verdict':'support','reason':'Reason','evidence':refs},{'event:0':'Text','task':'Task'},reviewer=True)


def test_clean_review_contract_and_all_roles_use_ids(release,taxonomy):
    call=Scripted({'initial':ANSWER,'default':{'verdict':'support','reason':'Supported','evidence':['event:0']}})
    r=run_harness('raffles',bundle(release,taxonomy),taxonomy,load_config(),call)
    assert r['audit']['stop']=='consensus'
    assert r['audit']['parse_warnings']==[]
    for role,parts in call.calls[1:]:
        text='\n'.join(p['text'] for p in parts)
        assert 'Agent Name:' not in text
        assert 'Step Number:' not in text
        assert 'SECRET_ANSWER' not in text
    assert r['audit']['history'][0]['reviews']['fault']['evidence'][0]['quote'].startswith('Step 1')


def test_agentrx_id_requirements_constraints_semantics(release,taxonomy):
    c={'requirement':'Budget','source':'task','assertion':'Price within budget','applicable':True,'method':'semantic'}
    call=Scripted({'requirements':{'requirements':[{'text':'Budget','source':'task'}]},
        'constraints':[{'constraints':[c]},{'constraints':[]}],
        'semantic':{'result':'violated','reason':'Over budget','evidence':['event:0','task']},'final':ANSWER})
    r=run_harness('agentrx',bundle(release,taxonomy),taxonomy,load_config(),call)
    assert not r['audit']['parse_warnings']
    assert r['audit']['checks'][0]['result']=='violated'
    assert r['audit']['requirements'][0]['source']=={'ref':'task'}


def test_agentrx_rejects_future_reference(release,taxonomy):
    c={'requirement':'Budget','source':'task','assertion':'Price within budget','applicable':True,'method':'semantic'}
    call=Scripted({'requirements':{'requirements':[]},'constraints':[{'constraints':[c]},{'constraints':[]}],
        'semantic':{'result':'violated','reason':'Over budget','evidence':['event:1']},'final':ANSWER})
    r=run_harness('agentrx',bundle(release,taxonomy),taxonomy,load_config(),call)
    assert r['audit']['checks'][0]['result']=='inconclusive'
    assert r['audit']['parse_warnings']


def test_revision_keeps_source_coordinates_without_repeating_evidence(release,taxonomy):
    call=Scripted({'initial':ANSWER,'revision':ANSWER,
        'default':{'verdict':'challenge','reason':'Earlier fault','evidence':['event:0']}})
    r=run_harness('raffles',bundle(release,taxonomy),taxonomy,load_config(),call)
    revision=next(parts for role,parts in call.calls if role=='revision')
    context=json.loads(revision[-1]['text'].split('\n',2)[2])
    assert context['history'][0]['reviews']['fault']['evidence']==[{'ref':'event:0'}]
    assert context['source_coordinates']['event:0']=={'agent':'agent','step':'1'}
    assert 'quote' in r['audit']['history'][0]['reviews']['fault']['evidence'][0]


def test_intermediate_schema_arguments_leave_final_protocol_unchanged(release,taxonomy):
    formats={}
    class Recording(Scripted):
        def __call__(self,role,parts,**kwargs):
            formats.setdefault(role,[]).append(kwargs.get('response_format'))
            return super().__call__(role,parts,**kwargs)
    c={'requirement':'Budget','source':'task','assertion':'Price within budget','applicable':True,'method':'semantic'}
    call=Recording({'requirements':{'requirements':[]},'constraints':[{'constraints':[c]},{'constraints':[]}],
        'semantic':{'result':'violated','reason':'Over budget','evidence':['event:0']},'final':ANSWER})
    run_harness('agentrx',bundle(release,taxonomy),taxonomy,load_config(),call)
    assert formats['requirements'][0]['type']=='json_schema'
    assert formats['constraints'][0]=={'type':'json_object'}
    assert formats['semantic'][0]['json_schema']['schema']['properties']['evidence']['items']['properties']['ref']['enum']==['task','event:0']
    assert formats['final']==[None]
