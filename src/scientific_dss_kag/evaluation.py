import hashlib
import json
from . import __version__
from .models import Backend, Mode, RetrievalRequest
from .domain import benchmark_cases


def metrics(retrieved: list[str], expected: list[str], k: int):
    if k < 1 or not expected:
        raise ValueError("positive k and nonempty relevance judgments required")
    expected = set(expected)
    top = retrieved[:k]
    recall = len(set(top) & expected) / len(expected)
    rr = next((1/r for r,v in enumerate(top, 1) if v in expected), 0.0)
    return {"recall_at_k": recall, "reciprocal_rank": rr}


def evaluate(retriever, k=3, cases=None):
    cases = cases if cases is not None else benchmark_cases(retriever.domain)
    if not cases:
        raise ValueError("benchmark requires cases")
    available = {e.id for e in retriever.evidence if e.review_status == "reviewed"}
    for case in cases:
        if not case["expected_ids"] or not set(case["expected_ids"]) <= available:
            raise ValueError("benchmark judgments must reference reviewed evidence")
    rows = []
    for mode in (Mode.lexical, Mode.hybrid, Mode.ontology):
        for case in cases:
            request = RetrievalRequest(query=case["query"], mode=mode, k=k, context=case["context"])
            response = retriever.retrieve(request)
            ids = [r["evidence"]["id"] for r in response["results"]]
            rows.append({"case_id": case["id"], "query": case["query"], "context": case["context"],
                         "mode": mode.value, "retrieved_ids": ids, "expected_ids": case["expected_ids"],
                         **metrics(ids, case["expected_ids"], k)})
    summary = {}
    for mode in ("lexical", "hybrid", "ontology"):
        selected = [r for r in rows if r["mode"] == mode]
        summary[mode] = {key: sum(r[key] for r in selected)/len(selected) for key in ("recall_at_k", "reciprocal_rank")}
    return {"version": __version__, "corpus_hash": retriever.corpus_hash,
            "benchmark_hash": hashlib.sha256(json.dumps(cases,sort_keys=True).encode()).hexdigest(),
            "ontology_version": "0.1.0", "k": k, "vector_method": "signed-char-trigram-256",
            "fusion": "rrf-60", "split": "synthetic-smoke-only", "summary": summary, "rows": rows,
            "limitations": "Teaching smoke test; no held-out scientific evaluation, generated answers, or evidence of KAG superiority."}


class _Precomputed:
    """Embedding scores worked out once and replayed, so each backend is ranked on identical vectors without more model calls."""

    def __init__(self, settings, table):
        self.settings, self.table = settings, table

    def embedding_scores(self, query, evidence, corpus_hash):
        return self.table[query], []


def compare_backends(retriever, provider, store, k=3, cases=None):
    """Rank the benchmark with offline vectors, in-memory model embeddings and the pgvector index, and check that the
    last two agree. The corpus and each query are embedded once (len(cases) + 1 model calls); both score tables are
    computed from those same vectors."""
    cases = cases if cases is not None else benchmark_cases(retriever.domain)
    reviewed = [e for e in retriever.evidence if e.review_status == "reviewed"]
    model = provider.settings.embedding_model
    corpus_vectors, corpus_usage = provider.embed_corpus(reviewed)
    query_vectors, usage = {}, [{"operation": "corpus_embeddings", "usage": corpus_usage}]
    for case in cases:
        query_vectors[case["query"]], query_usage = provider.embed_query(case["query"])
        usage.append({"operation": "query_embedding", "usage": query_usage})
    memory = {q: {e.id: sum(a * b for a, b in zip(qv, cv)) for e, cv in zip(reviewed, corpus_vectors)} for q, qv in query_vectors.items()}
    stored = {q: store.scores(retriever.domain, model, retriever.corpus_hash, qv, reviewed) for q, qv in query_vectors.items()}
    max_diff = max(abs(memory[q][i] - stored[q][i]) for q in memory for i in memory[q])
    backends = {"offline": (Backend.offline, None), "openai_in_memory": (Backend.openai, _Precomputed(provider.settings, memory)),
                "pgvector": (Backend.pgvector, _Precomputed(provider.settings, stored))}
    rows = []
    for name, (backend, embedder) in backends.items():
        for mode in (Mode.hybrid, Mode.ontology):
            for case in cases:
                request = RetrievalRequest(query=case["query"], mode=mode, k=k, context=case["context"], backend=backend)
                ids = [r["evidence"]["id"] for r in retriever.retrieve(request, embedder)["results"]]
                rows.append({"backend": name, "mode": mode.value, "case_id": case["id"], "retrieved_ids": ids, "expected_ids": case["expected_ids"],
                             **metrics(ids, case["expected_ids"], k)})
    summary = {}
    for name in backends:
        for mode in ("hybrid", "ontology"):
            chosen = [r for r in rows if r["backend"] == name and r["mode"] == mode]
            summary[f"{name}/{mode}"] = {key: sum(r[key] for r in chosen) / len(chosen) for key in ("recall_at_k", "reciprocal_rank")}
    same_ranking = all(a["retrieved_ids"] == b["retrieved_ids"] for a in rows if a["backend"] == "openai_in_memory"
                       for b in rows if b["backend"] == "pgvector" and (a["mode"], a["case_id"]) == (b["mode"], b["case_id"]))
    return {"version": __version__, "domain": retriever.domain, "corpus_hash": retriever.corpus_hash, "embedding_model": model,
            "dimension": len(corpus_vectors[0]), "k": k, "cases": len(cases), "model_calls": len(usage),
            "max_abs_cosine_difference_memory_vs_pgvector": max_diff, "identical_rankings_memory_vs_pgvector": same_ranking,
            "summary": summary, "rows": rows,
            "limitations": "Synthetic teaching corpus with a handful of cases: the metrics saturate and do not rank the methods. "
                           "What this does show is that the database search reproduces the in-memory similarity. KAG is not included "
                           "(each KAG question costs 25 to 50 paid model calls)."}
