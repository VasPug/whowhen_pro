import pytest
from whowhen_eval.experiment.evidence import locate


def test_normalization_returns_original_source():
    sources={'task':'Use the “type”  column.\nThen return it.'}
    r=locate({'ref':'task:0','quote':'Use the "type" column.'},sources,'aliases')
    assert r['status']=='matched'
    assert r['ref']=='task'
    assert r['quote']=='Use the “type”  column.'
    assert sources['task'][r['start']:r['end']]==r['quote']


@pytest.mark.parametrize('quote', ['Price 20 pounds','Price -620 pounds','Do buy it.'])
def test_meaning_changes_do_not_match(quote):
    assert locate({'ref':'event:0','quote':quote},{'event:0':'Price 620 pounds. Do not buy it.'},'aliases')['status']=='unresolved'


def test_wrong_step_is_not_remapped():
    assert locate({'ref':'event:2','quote':'The price is 620 pounds.'},
        {'event:1':'The price is 620 pounds.','event:2':'The price is 500 pounds.'},'aliases')['status']=='unresolved'


def test_ellipsis_recovers_condition_but_does_not_certify_claim():
    s='This call will fail unless the directory is current because the filename is relative.'
    r=locate({'ref':'event:1','quote':'This call will fail ... because the filename is relative.'},{'event:1':s},'ellipsis')
    assert r['status']=='located_needs_review'
    assert r['quote']==s
    assert 'unless' in r['quote']


def test_ambiguous_spans_require_review():
    s='The price is 500 pounds. The price is 500 pounds.'
    assert locate({'ref':'event:0','quote':'The price is 500 pounds.'},{'event:0':s},'aliases')['status']=='ambiguous'


def test_numeric_suffix_cannot_be_accepted():
    assert locate({'ref':'event:0','quote':'20 pounds'},{'event:0':'Price 620 pounds'},'aliases')['status']=='unresolved'


@pytest.mark.parametrize('source,quote', [('Amount 1e-3 pounds.','-3 pounds.'),('Amount 1.5 pounds.','.5 pounds.'),('Amount 1e+3 pounds.','+3 pounds.')])
def test_signed_or_decimal_suffix_cannot_cut_numeric_token(source,quote):
    assert locate({'ref':'event:0','quote':quote},{'event:0':source},'aliases')['status']=='unresolved'
