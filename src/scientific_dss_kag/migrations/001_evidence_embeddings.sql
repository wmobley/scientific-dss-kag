-- Persistent embeddings for reviewed evidence. One row per (domain, evidence, embedding model).
-- The vector column has no fixed dimension and no ANN index: pgvector indexes at most 2000 dimensions
-- (vector) or 4000 (halfvec), and E5-Mistral produces 4096. Exact search is fine for a corpus this size.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS evidence_embeddings (
    domain          text        NOT NULL,
    evidence_id     text        NOT NULL,
    source_hash     char(64)    NOT NULL,
    corpus_hash     char(64)    NOT NULL,
    embedding_model text        NOT NULL,
    dimension       integer     NOT NULL CHECK (dimension > 0),
    embedding       vector      NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (domain, evidence_id, embedding_model),
    CHECK (vector_dims(embedding) = dimension)
);
