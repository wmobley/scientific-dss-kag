"""Persistent evidence embeddings in PostgreSQL + pgvector (local, loopback only).

The index is built explicitly from reviewed evidence and records the model, dimension and corpus hash for each
row. A query fails loudly, rather than answering from stale or partial vectors, if the stored index no longer
matches the current corpus. Vectors are stored normalised, so cosine similarity is 1 - pgvector's cosine distance
and equals the in-memory dot product used by the OpenAI backend.
"""
from dataclasses import dataclass, field
from importlib.resources import files
import os
import re
import psycopg
from .settings import LOOPBACK_HOSTS


class StaleIndex(RuntimeError):
    """The stored index is missing, partial or built from a different corpus or model."""


@dataclass(frozen=True)
class VectorSettings:
    host: str = "127.0.0.1"
    port: int = 5439
    user: str = "scientific_dss"
    database: str = "scientific_dss"
    password: str = field(default="", repr=False)

    def __post_init__(self):
        if self.host not in LOOPBACK_HOSTS:
            raise ValueError("The vector store must be on a loopback address")
        if not 1 <= self.port <= 65535 or not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", self.user) or not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", self.database):
            raise ValueError("Invalid vector store settings")
        if not self.password:
            raise ValueError("POSTGRES_PASSWORD is required for the vector store")

    @classmethod
    def from_env(cls):
        env = os.environ
        return cls(host=env.get("DSS_VECTOR_HOST", cls.host), port=int(env.get("DSS_VECTOR_PORT", cls.port)),
                   password=env.get("POSTGRES_PASSWORD", ""))


def vector_literal(vector):
    if not vector or any(not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")) for v in vector):
        raise ValueError("invalid vector")
    return "[" + ",".join(repr(float(v)) for v in vector) + "]"


class VectorStore:
    def __init__(self, settings):
        self.settings = settings

    def connect(self):
        s = self.settings
        return psycopg.connect(host=s.host, port=s.port, user=s.user, dbname=s.database, password=s.password, connect_timeout=5)

    def migrate(self):
        """Apply the bundled .sql files in name order, once each. Returns the versions applied now."""
        applied_now = []
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
            done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
            for resource in sorted(files("scientific_dss_kag").joinpath("migrations").iterdir(), key=lambda r: r.name):
                if resource.name.endswith(".sql") and resource.name not in done:
                    conn.execute(resource.read_text())
                    conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (resource.name,))
                    applied_now.append(resource.name)
        return applied_now

    def replace_domain(self, domain, model, corpus_hash, rows):
        """Atomically replace every row for (domain, model). rows: [(evidence_id, source_hash, vector)]."""
        if not rows:
            raise ValueError("refusing to replace an index with nothing")
        dimensions = {len(vector) for _, _, vector in rows}
        if len(dimensions) != 1:
            raise ValueError("all vectors in an index must have one dimension")
        dimension = dimensions.pop()
        with self.connect() as conn:  # one transaction: a failure leaves the previous index untouched
            conn.execute("DELETE FROM evidence_embeddings WHERE domain = %s AND embedding_model = %s", (domain, model))
            for evidence_id, source_hash, vector in rows:
                conn.execute("INSERT INTO evidence_embeddings (domain, evidence_id, source_hash, corpus_hash, embedding_model, dimension, embedding) "
                             "VALUES (%s, %s, %s, %s, %s, %s, %s::vector)",
                             (domain, evidence_id, source_hash, corpus_hash, model, dimension, vector_literal(vector)))
        return len(rows)

    def scores(self, domain, model, corpus_hash, query_vector, evidence):
        """Cosine similarity of the query to each stored vector, after checking the index matches the corpus."""
        with self.connect() as conn:
            # Postgres refuses to compare vectors of different sizes, so check the stored size before computing distances.
            stored_dimensions = {r[0] for r in conn.execute("SELECT DISTINCT dimension FROM evidence_embeddings WHERE domain = %s AND embedding_model = %s",
                                                            (domain, model))}
            if stored_dimensions and stored_dimensions != {len(query_vector)}:
                raise StaleIndex("The stored vectors and the query vector differ in dimension (different embedding model?).")
            rows = conn.execute("SELECT evidence_id, source_hash, corpus_hash, dimension, 1 - (embedding <=> %s::vector) "
                                "FROM evidence_embeddings WHERE domain = %s AND embedding_model = %s",
                                (vector_literal(query_vector), domain, model)).fetchall()
        stored = {r[0]: r for r in rows}
        expected = {e.id: e.source_hash for e in evidence}
        if set(stored) != set(expected):
            raise StaleIndex("The vector index does not cover exactly the reviewed evidence; rebuild it with `scientific-dss vector-index`.")
        if any(r[2] != corpus_hash or r[1] != expected[r[0]] for r in rows):
            raise StaleIndex("The vector index was built from a different corpus; rebuild it with `scientific-dss vector-index`.")
        if {r[3] for r in rows} != {len(query_vector)}:
            raise StaleIndex("The stored vectors and the query vector differ in dimension (different embedding model?).")
        return {evidence_id: float(similarity) for evidence_id, _, _, _, similarity in rows}

    def status(self, domain):
        with self.connect() as conn:
            rows = conn.execute("SELECT embedding_model, count(*), min(dimension), max(dimension), min(corpus_hash), max(corpus_hash), max(created_at) "
                                "FROM evidence_embeddings WHERE domain = %s GROUP BY embedding_model", (domain,)).fetchall()
        return [{"embedding_model": r[0], "rows": r[1], "dimension": r[2] if r[2] == r[3] else None, "corpus_hash": r[4] if r[4] == r[5] else None,
                 "built_at": r[6].isoformat()} for r in rows]


class PersistentEmbeddings:
    """Drop-in for the provider's embedding_scores: query embedded live, corpus vectors read from PostgreSQL."""

    def __init__(self, provider, store, domain):
        self.provider, self.store, self.domain = provider, store, domain
        self.settings = provider.settings

    def embedding_scores(self, query, evidence, corpus_hash):
        if not evidence:
            return {}, []
        vector, usage = self.provider.embed_query(query)
        try:
            scores = self.store.scores(self.domain, self.settings.embedding_model, corpus_hash, vector, evidence)
        except psycopg.Error:
            raise StaleIndex("The vector store is unreachable or not migrated; start it and run `scientific-dss vector-migrate`.") from None
        return scores, [{"operation": "query_embedding", "usage": usage}]


def build_index(provider, store, retriever):
    """Embed the reviewed evidence (one batched model call) and replace the stored index for this domain and model."""
    reviewed = [e for e in retriever.evidence if e.review_status == "reviewed"]
    vectors, usage = provider.embed_corpus(reviewed)
    rows = [(e.id, e.source_hash, vector) for e, vector in zip(reviewed, vectors)]
    count = store.replace_domain(retriever.domain, provider.settings.embedding_model, retriever.corpus_hash, rows)
    return {"domain": retriever.domain, "embedding_model": provider.settings.embedding_model, "rows": count,
            "dimension": len(vectors[0]), "corpus_hash": retriever.corpus_hash, "usage": usage}
