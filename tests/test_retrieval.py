from copy import deepcopy
import pytest
from scientific_dss_kag.models import RetrievalRequest
from scientific_dss_kag.retrieval import Retriever, IntegrationUnavailable
from scientific_dss_kag.evaluation import metrics, evaluate


@pytest.fixture
def retriever():
    return Retriever()


def test_provenance_and_candidates(retriever):
    result = retriever.retrieve(RetrievalRequest(query="mosquito habitat disease", k=20))
    for item in result["results"]:
        e = item["evidence"]
        assert e["id"] != "ev-candidate"
        assert e["passage"] == item["source"]["text"][e["start"]:e["end"]]


@pytest.mark.parametrize('field,value', [('passage','tampered'), ('source_hash','0'*64), ('start',1), ('end',99999), ('source_id','missing'), ('concepts',['Unknown'])])
def test_tampering_fails_closed(retriever, field, value):
    corpus = deepcopy(retriever.corpus)
    corpus['evidence'][0][field] = value
    with pytest.raises(ValueError):
        Retriever(corpus)


def test_explicit_ontology_context_changes_evidence(retriever):
    query = "MaxEnt habitat validation spatial"
    hybrid = retriever.retrieve(RetrievalRequest(query=query,mode="hybrid",k=20))
    guided = retriever.retrieve(RetrievalRequest(query=query,mode="ontology",context=["ValidationActivity"],k=20))
    assert len(hybrid['results']) > len(guided['results']) == 1
    assert guided['results'][0]['evidence']['id'] == 'ev-sampling'
    assert all('ValidationActivity' in x['evidence']['concepts'] for x in guided['results'])


def test_zero_overlap_empty_lexical(retriever):
    assert retriever.retrieve(RetrievalRequest(query="zzzzzz",mode="lexical"))['results'] == []


def test_no_silent_kag_fallback(retriever):
    with pytest.raises(IntegrationUnavailable):
        retriever.retrieve(RetrievalRequest(query='habitat',mode='kag'))
    with pytest.raises(ValueError):
        retriever.retrieve(RetrievalRequest(query='habitat',mode='ontology'))


def test_metrics_hand_calculated():
    assert metrics(['wrong','a','b'],['a','c'],3) == {'recall_at_k':.5,'reciprocal_rank':.5}
    assert metrics([],['a'],3) == {'recall_at_k':0,'reciprocal_rank':0}
    assert metrics(['a','a'],['a','b'],2)['recall_at_k'] == .5
    with pytest.raises(ValueError): metrics([],[],3)


def test_evaluation_reproducible(retriever):
    first = evaluate(retriever)
    assert first == evaluate(retriever)
    assert len(first['rows']) == 12
    assert len(first['corpus_hash']) == 64
    assert set(first['summary']) == {'lexical','hybrid','ontology'}
    with pytest.raises(ValueError): evaluate(retriever,cases=[])


def test_duplicate_metric_preserves_original_rank():
    assert metrics(['wrong','wrong','a'],['a'],3)['reciprocal_rank'] == 1/3
