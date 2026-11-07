"""Deterministic teaching baselines, not a substitute for OpenSPG reasoning."""
import hashlib
import math
import re
from collections import Counter
from .models import Backend, Evidence, Mode, RetrievalRequest
from .domain import DEFAULT_DOMAIN, domain_name, load

CONCEPTS = frozenset("DecisionProblem Stakeholder Objective Alternative Uncertainty InformationNeed ScientificMethod ComputationalModel Dataset Evidence ScientificClaim ScientificVariable Assumption ValidationActivity DecisionPathway".split())


REMOTE_BACKENDS = (Backend.openai, Backend.pgvector)


class IntegrationUnavailable(RuntimeError):
    pass


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def vector(text):
    # Stable signed character-trigram hashing. No downloaded embedding model.
    out = [0.0] * 256
    text = " ".join(tokens(text))
    for i in range(max(0, len(text) - 2)):
        digest = hashlib.sha256(text[i:i+3].encode()).digest()
        out[digest[0]] += 1 if digest[1] % 2 else -1
    norm = math.sqrt(sum(v*v for v in out)) or 1
    return [v / norm for v in out]


def validate_evidence(evidence, sources):
    source = sources.get(evidence.source_id)
    if source is None:
        raise ValueError("unknown source")
    text = source["text"]
    if hashlib.sha256(text.encode()).hexdigest() != evidence.source_hash:
        raise ValueError("source checksum mismatch")
    if not evidence.start < evidence.end <= len(text):
        raise ValueError("invalid evidence offsets")
    if text[evidence.start:evidence.end] != evidence.passage:
        raise ValueError("passage does not match source span")
    if not evidence.concepts or not set(evidence.concepts) <= CONCEPTS:
        raise ValueError("unknown or empty ontology concepts")


class Retriever:
    def __init__(self, corpus=None, domain=DEFAULT_DOMAIN):
        self.domain = domain_name(domain)
        self.corpus = corpus or load(self.domain, "corpus.json")
        self.sources = {s["id"]: s for s in self.corpus["sources"]}
        if len(self.sources) != len(self.corpus["sources"]):
            raise ValueError("duplicate source IDs")
        self.evidence = [Evidence.model_validate(e) for e in self.corpus["evidence"]]
        if len({e.id for e in self.evidence}) != len(self.evidence):
            raise ValueError("duplicate evidence IDs")
        for e in self.evidence:
            validate_evidence(e, self.sources)
        self.corpus_hash = hashlib.sha256(__import__("json").dumps(self.corpus, sort_keys=True).encode()).hexdigest()

    def retrieve(self, request: RetrievalRequest, provider=None):
        if request.mode == Mode.kag:
            raise IntegrationUnavailable("KAG schema import and query have not been verified")
        if request.mode == Mode.ontology and not request.context:
            raise ValueError("ontology mode requires explicit decision context")
        if request.backend in REMOTE_BACKENDS and request.mode == Mode.lexical:
            raise ValueError("lexical mode uses the offline backend")
        if request.backend in REMOTE_BACKENDS and provider is None:
            raise IntegrationUnavailable("OpenAI provider is unavailable")
        # Candidate assertions never enter retrieval implicitly.
        reviewed = [e for e in self.evidence if e.review_status == "reviewed"]
        candidates = reviewed
        if request.mode == Mode.ontology:
            candidates = [e for e in candidates if set(e.concepts) & set(request.context)]
        query_terms = Counter(tokens(request.query))
        def lexical(e):
            words = Counter(tokens(e.passage))
            return sum(min(n, words[t]) for t, n in query_terms.items()) / (len(words) or 1)
        embedding_usage = []
        provider_scores = {}
        if request.backend in REMOTE_BACKENDS and candidates:
            provider_scores, embedding_usage = provider.embedding_scores(request.query, reviewed, self.corpus_hash)
        qv = vector(request.query)
        def cosine(e):
            if request.backend in REMOTE_BACKENDS:
                return provider_scores.get(e.id, 0)
            return sum(a*b for a,b in zip(qv, vector(e.passage)))
        lex = sorted(((lexical(e), e) for e in candidates), key=lambda x: (-x[0], x[1].id))
        lex = [(s,e) for s,e in lex if s > 0]
        if request.mode == Mode.lexical:
            ranked = lex
        else:
            vec = sorted(((cosine(e),e) for e in candidates), key=lambda x: (-x[0], x[1].id))
            vec = [(s,e) for s,e in vec if s > 0]
            scores = Counter()
            for ranking in (lex, vec):
                for rank, (_, e) in enumerate(ranking, 1):
                    scores[e.id] += 1/(60+rank)
            ranked = sorted(((scores[e.id],e) for e in candidates if scores[e.id]), key=lambda x: (-x[0], x[1].id))
        method = "token-overlap" if request.mode == Mode.lexical else "rrf(token-overlap,signed-char-trigram-256)"
        if request.backend in REMOTE_BACKENDS:
            method = f"rrf(token-overlap,{request.backend.value}:{provider.settings.embedding_model})"
        return {"mode": request.mode, "backend": request.backend, "embedding_usage": embedding_usage, "query": request.query, "context": request.context,
                "corpus_hash": self.corpus_hash, "synthetic": True,
                "method": method,
                "results": [{"score": s, "evidence": e.model_dump(), "source": self.sources[e.source_id]} for s,e in ranked[:request.k]],
                "limitations": "Synthetic teaching corpus; ranking scores are not probabilities or scientific confidence. No generated answer or SDM execution."}
