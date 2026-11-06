import hashlib
import json
from . import __version__
from .models import Mode, RetrievalRequest
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
