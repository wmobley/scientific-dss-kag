"""Vector store tests. Offline tests use a fake store; database tests run only when POSTGRES_PASSWORD is set and a
local pgvector database answers (docs/setup.md), and use throwaway domain names that they clean up."""
import json
import math
import os
import uuid
import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from scientific_dss_kag.api import create_app
from scientific_dss_kag.models import Backend, RetrievalRequest
from scientific_dss_kag.openai_provider import OpenAIProvider
from scientific_dss_kag.retrieval import Retriever
from scientific_dss_kag.settings import OpenAISettings
from scientific_dss_kag.vector_store import PersistentEmbeddings, StaleIndex, VectorSettings, VectorStore, build_index, vector_literal

DOMAIN = "groundwater-subsidence"
KEY = "test-key-never-a-real-credential"
MODEL = "E5-Mistral-7B-Instruct"


@pytest.fixture(scope="module")
def retriever():
    return Retriever(domain=DOMAIN)


def reviewed(retriever):
    return [e for e in retriever.evidence if e.review_status == "reviewed"]


# ---------- offline ----------

def test_vector_literal_formats_and_rejects_bad_values():
    assert vector_literal([0.5, -1, 2]) == "[0.5,-1.0,2.0]"
    for bad in ([], [float("nan")], [float("inf")], ["x"], None):
        with pytest.raises(ValueError):
            vector_literal(bad)


@pytest.mark.parametrize("bad", [dict(host="192.168.1.5"), dict(host="db.example.com"), dict(password=""), dict(user="Robert'); DROP"),
                                 dict(database="has space"), dict(port=0), dict(port=70000)])
def test_settings_reject_unsafe_values(bad):
    with pytest.raises(ValueError):
        VectorSettings(**{"password": "x", **bad})


class FakeStore:
    def __init__(self, table=None, error=None):
        self.table, self.error, self.calls = table, error, []

    def scores(self, domain, model, corpus_hash, query_vector, evidence):
        self.calls.append((domain, model, corpus_hash, len(query_vector)))
        if self.error:
            raise self.error
        return self.table or {e.id: 0.5 for e in evidence}


def embeddings_transport(log):
    def handler(request):
        body = json.loads(request.content)
        log.append((request.url.path, body))
        if request.url.path == "/v1/chat/completions":  # /answer's generation step: a valid abstention
            answer = {"status": "abstained", "claims": [], "gaps": ["test"], "uncertainties": []}
            return httpx.Response(200, json={"id": "c", "model": "m", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(answer)}}]})
        assert request.url.path == "/v1/embeddings"
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [1.0, float(i + 1), .5]} for i in range(len(body["input"]))],
                                         "model": body["model"], "usage": {"prompt_tokens": 3, "total_tokens": 3}})
    return httpx.MockTransport(handler)


def provider(log):
    return OpenAIProvider(OpenAISettings(enabled=True, api_key=KEY, embedding_model=MODEL), embeddings_transport(log))


def test_persistent_embeddings_embed_only_the_query_and_check_the_index(retriever):
    log, store = [], FakeStore()
    p = PersistentEmbeddings(provider(log), store, DOMAIN)
    scores, usage = p.embedding_scores("pumping and subsidence", reviewed(retriever), retriever.corpus_hash)
    assert len(log) == 1 and len(log[0][1]["input"]) == 1 and log[0][1]["input"][0].startswith("Instruct:")  # query only, with E5's instruction
    assert store.calls == [(DOMAIN, MODEL, retriever.corpus_hash, 3)] and set(scores) == {e.id for e in reviewed(retriever)}
    assert usage[0]["operation"] == "query_embedding" and p.embedding_scores("x", [], "h") == ({}, [])


def test_stale_and_unreachable_stores_fail_loudly(retriever):
    for error in (StaleIndex("stale"), psycopg.OperationalError("connection refused")):
        p = PersistentEmbeddings(provider([]), FakeStore(error=error), DOMAIN)
        with pytest.raises(StaleIndex):
            p.embedding_scores("q", reviewed(retriever), retriever.corpus_hash)


def test_retrieval_labels_the_pgvector_backend_and_rejects_lexical(retriever):
    p = PersistentEmbeddings(provider([]), FakeStore(), DOMAIN)
    out = retriever.retrieve(RetrievalRequest(query="pumping subsidence head", mode="hybrid", backend=Backend.pgvector), p)
    assert out["backend"] == "pgvector" and out["method"] == f"rrf(token-overlap,pgvector:{MODEL})"
    with pytest.raises(ValueError):
        retriever.retrieve(RetrievalRequest(query="pumping", mode="lexical", backend=Backend.pgvector), p)


def app(store, log=None):
    return TestClient(create_app(settings=OpenAISettings(enabled=True, api_key=KEY, embedding_model=MODEL), domain=DOMAIN, store=store,
                                 provider=provider(log if log is not None else [])), base_url="http://127.0.0.1")


def test_api_pgvector_route(monkeypatch):
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    body = {"query": "pumping and subsidence", "mode": "hybrid", "backend": "pgvector"}
    log = []
    with app(FakeStore(), log) as client:
        out = client.post("/retrieve", json=body).json()
        assert out["backend"] == "pgvector" and out["results"] and len(log) == 1  # one query embedding, no corpus embedding
        assert client.post("/retrieve", json=body, headers={"Origin": "http://evil.example"}).status_code == 403
        assert client.post("/retrieve", json={**body, "mode": "lexical"}).status_code == 422
    with app(FakeStore(error=StaleIndex("rebuild it"))) as client:
        response = client.post("/retrieve", json=body)
        assert response.status_code == 409 and response.json()["detail"]["code"] == "vector_index_stale"
    with TestClient(create_app(settings=OpenAISettings(enabled=True, api_key=KEY), domain=DOMAIN, provider=provider([]), store=None), base_url="http://127.0.0.1") as client:
        response = client.post("/retrieve", json=body)
        assert response.status_code == 503 and response.json()["detail"]["code"] == "pgvector_unavailable"
    with TestClient(create_app(settings=OpenAISettings(enabled=True, api_key=KEY), domain=DOMAIN, provider=provider([]), store=FakeStore())) as client:  # Host 'testserver'
        assert client.post("/retrieve", json=body).status_code == 403


def test_answer_with_pgvector_never_falls_back_to_in_memory_corpus_embedding():
    log = []
    with app(FakeStore(), log) as client:
        client.post("/answer", json={"query": "pumping and subsidence", "mode": "hybrid", "backend": "pgvector"})
    embedding_calls = [body for path, body in log if path == "/v1/embeddings"]
    assert embedding_calls and all(len(body["input"]) == 1 for body in embedding_calls), "the corpus must not be embedded per request when pgvector is selected"


# ---------- database ----------

def connectable():
    try:
        VectorStore(VectorSettings.from_env()).connect().close()
        return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(not os.environ.get("POSTGRES_PASSWORD") or not connectable(), reason="local pgvector database not available")


@pytest.fixture
def store():
    s = VectorStore(VectorSettings.from_env())
    s.migrate()
    domain = f"test-{uuid.uuid4().hex[:8]}"
    yield s, domain
    with s.connect() as conn:
        conn.execute("DELETE FROM evidence_embeddings WHERE domain LIKE 'test-%'")


def unit(vector):
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector]


def rows_for(retriever, offset=0.0, dims=4):
    return [(e.id, e.source_hash, unit([1.0 + i * 0.3 + offset, 2.0 - i * 0.1, 0.5 + (i % 2), 1.0] + [0.2] * (dims - 4))) for i, e in enumerate(reviewed(retriever))]


@needs_db
def test_migration_is_idempotent(store):
    s, _ = store
    assert s.migrate() == []


@needs_db
def test_scores_equal_the_dot_product_within_float32_rounding(store, retriever):
    s, domain = store
    rows = rows_for(retriever)
    assert s.replace_domain(domain, MODEL, retriever.corpus_hash, rows) == len(rows)
    query = unit([0.9, 1.7, 1.2, 0.8])
    scores = s.scores(domain, MODEL, retriever.corpus_hash, query, reviewed(retriever))
    for evidence_id, _, vector in rows:
        assert abs(scores[evidence_id] - sum(a * b for a, b in zip(query, vector))) < 1e-6  # pgvector stores float32
    assert [d["rows"] for d in s.status(domain)] == [len(rows)] and s.status(domain)[0]["dimension"] == 4


@needs_db
def test_replace_is_atomic_and_leaves_the_previous_index_on_failure(store, retriever):
    s, domain = store
    rows = rows_for(retriever)
    s.replace_domain(domain, MODEL, retriever.corpus_hash, rows)
    broken = rows + [rows[0]]  # duplicate primary key part-way through the inserts
    with pytest.raises(psycopg.errors.UniqueViolation):
        s.replace_domain(domain, MODEL, retriever.corpus_hash, broken)
    assert s.status(domain)[0]["rows"] == len(rows)
    with pytest.raises(ValueError):
        s.replace_domain(domain, MODEL, retriever.corpus_hash, [])
    with pytest.raises(ValueError):
        s.replace_domain(domain, MODEL, retriever.corpus_hash, [rows[0], (rows[1][0], rows[1][1], [1.0, 0.0])])


@needs_db
def test_stale_indexes_are_detected(store, retriever):
    s, domain = store
    ev, query = reviewed(retriever), unit([0.9, 1.7, 1.2, 0.8])
    with pytest.raises(StaleIndex):  # nothing built yet
        s.scores(domain, MODEL, retriever.corpus_hash, query, ev)
    s.replace_domain(domain, MODEL, retriever.corpus_hash, rows_for(retriever))
    with pytest.raises(StaleIndex):  # corpus changed
        s.scores(domain, MODEL, "f" * 64, query, ev)
    with pytest.raises(StaleIndex):  # a reviewed passage was added since the build
        s.scores(domain, MODEL, retriever.corpus_hash, query, ev[:-1] + ev[-1:] + [ev[0].model_copy(update={"id": "ev-new"})])
    with pytest.raises(StaleIndex):  # a passage was dropped
        s.scores(domain, MODEL, retriever.corpus_hash, query, ev[:-1])
    with pytest.raises(StaleIndex):  # a passage's source hash changed
        s.scores(domain, MODEL, retriever.corpus_hash, query, [ev[0].model_copy(update={"source_hash": "0" * 64})] + ev[1:])
    with pytest.raises(StaleIndex):  # query embedded by a different model (different dimension)
        s.scores(domain, MODEL, retriever.corpus_hash, unit([1.0, 2.0, 3.0]), ev)


@needs_db
def test_models_and_domains_are_isolated_and_dimension_is_enforced(store, retriever):
    s, domain = store
    s.replace_domain(domain, "model-a", retriever.corpus_hash, rows_for(retriever))
    s.replace_domain(domain, "model-b", retriever.corpus_hash, rows_for(retriever, dims=6))
    s.replace_domain(domain + "-other", "model-a", retriever.corpus_hash, rows_for(retriever))
    assert sorted((d["embedding_model"], d["dimension"]) for d in s.status(domain)) == [("model-a", 4), ("model-b", 6)]
    s.replace_domain(domain, "model-a", retriever.corpus_hash, rows_for(retriever, offset=1.0))  # replaces only model-a of this domain
    assert {d["embedding_model"] for d in s.status(domain)} == {"model-a", "model-b"} and s.status(domain + "-other")[0]["rows"] == len(reviewed(retriever))
    with s.connect() as conn, pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO evidence_embeddings VALUES (%s,'x',%s,%s,'m',3,'[1,2]'::vector)", (domain, "0" * 64, "0" * 64))


@needs_db
def test_build_index_from_the_provider_stores_the_batch(store, retriever):
    s, domain = store
    log = []
    p = provider(log)
    fake = type("R", (), {"domain": domain, "corpus_hash": retriever.corpus_hash, "evidence": retriever.evidence})()
    report = build_index(p, s, fake)
    assert report["rows"] == len(reviewed(retriever)) and report["dimension"] == 3 and len(log) == 1  # one batched model call
    assert len(log[0][1]["input"]) == len(reviewed(retriever)) and not any(x.startswith("Instruct:") for x in log[0][1]["input"])
