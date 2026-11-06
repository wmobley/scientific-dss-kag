import pytest
from scientific_dss_kag.connectors import fixture_catalog
from scientific_dss_kag.domain import available_domains, benchmark_cases, domain_name, load
from scientific_dss_kag.evaluation import evaluate
from scientific_dss_kag.retrieval import Retriever
from scientific_dss_kag.validation import validate_pathway
from scientific_dss_kag.models import Pathway


def test_domains_are_discovered_not_listed():
    assert {"vector-borne-disease", "groundwater-subsidence"} <= set(available_domains())


@pytest.mark.parametrize("bad", ["../ontology", "..", "nope", "VECTOR", "vector-borne-disease/../x", "a" * 100])
def test_unsafe_or_unknown_domain_names_are_rejected(bad):
    with pytest.raises(ValueError):
        domain_name(bad)


def test_env_selects_domain(monkeypatch):
    monkeypatch.setenv("DSS_DOMAIN", "groundwater-subsidence")
    assert domain_name() == "groundwater-subsidence"
    monkeypatch.delenv("DSS_DOMAIN")
    assert domain_name() == "vector-borne-disease"


@pytest.mark.parametrize("domain", ["vector-borne-disease", "groundwater-subsidence"])
def test_each_domain_loads_validates_and_benchmarks(domain):
    retriever = Retriever(domain=domain)
    assert retriever.domain == domain
    assert any(e.review_status == "candidate" for e in retriever.evidence), "an unreviewed candidate must exist"
    assert evaluate(retriever, 3)["summary"]["ontology"]["recall_at_k"] == 1.0
    pathway = Pathway.model_validate(load(domain, "pathway.json"))
    assert validate_pathway(pathway, retriever)["structurally_complete"]
    assert fixture_catalog(domain)["variables"] and benchmark_cases(domain)


def test_domains_have_distinct_corpora():
    a, b = Retriever(domain="vector-borne-disease"), Retriever(domain="groundwater-subsidence")
    assert a.corpus_hash != b.corpus_hash
    assert {e.id for e in a.evidence}.isdisjoint({e.id for e in b.evidence})


def test_candidate_evidence_never_retrieved_in_groundwater_domain():
    from scientific_dss_kag.models import RetrievalRequest
    r = Retriever(domain="groundwater-subsidence")
    out = r.retrieve(RetrievalRequest(query="reducing pumping always reverses subsidence", mode="hybrid", k=10))
    assert "ev-gw-candidate" not in {x["evidence"]["id"] for x in out["results"]}
