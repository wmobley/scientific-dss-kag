# scientific-dss-kag

A reusable **Decision Pathways Ontology guided scientific DSS research testbed**. The first teaching domain is vector-borne disease species distribution modeling (SDM).

**Version 0.1 is an offline, runnable scaffold.** It includes a portable OWL/RDF ontology, SHACL validation, a draft OpenSPG schema, FastAPI, a student workbench, traceable synthetic evidence and reproducible retrieval comparisons. OpenSPG/KAG, DYNAMO and SVO are **not live-verified**. There is no LLM answer generation, automated scientific extraction, model execution or disease risk prediction.

## Run locally

Requires Python 3.12 or 3.13. From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install '.[dev]'
python -m pytest -q
uvicorn scientific_dss_kag.api:app --host 127.0.0.1 --port 8091
```

Open [the student workbench](http://127.0.0.1:8091) or [API docs](http://127.0.0.1:8091/docs). Port 8091 is a proposed local research-demo port, not a deployed DSO service assignment; use another free port if needed.

```bash
scientific-dss benchmark --k 3 > benchmark.json
curl -s http://127.0.0.1:8091/retrieve -H 'Content-Type: application/json' \
  -d '{"query":"How should occurrence observations be validated?","mode":"ontology","context":["ValidationActivity"],"k":3}'
```

## Run with Compose

```bash
cp .env.example .env
# Set a local random POSTGRES_PASSWORD in .env; optional vector profile uses it.
docker compose up --build
```

The API binds only to localhost. `docker compose -f compose.yaml -f compose.vector.yaml --profile vector-store up --build` additionally provisions a pgvector database. **The default retriever does not use that database.** See [setup](docs/setup.md) for validation and stopping instructions. OpenSPG uses its own upstream deployment, described in [integrations](docs/integrations.md).

## What students can compare

- `lexical`: normalized word-overlap baseline.
- `hybrid`: reciprocal rank fusion of word overlap and deterministic signed character-trigram vectors.
- `ontology`: the hybrid method, filtered by explicitly selected ontology classes.
- `kag`: returns HTTP 503 until real schema loading and queries are implemented and verified.

These are teaching baselines, not full conventional generative RAG, learned semantic embeddings or graph reasoning. The four synthetic benchmark cases test mechanics; their scores do not demonstrate scientific effectiveness. Ontology context is supplied independently of relevance judgments.

All retrieved passages carry exact source spans and SHA-256 hashes. Candidate assertions are excluded. The word “reviewed” in the bundled fixtures denotes teaching-fixture eligibility, **not expert scientific review**. Habitat suitability must not be interpreted as disease incidence or transmission risk.

## Repository guide

- [Ontology and shapes](ontology/): 15 core classes, relationships, validation examples and [draft SPG mapping](ontology/mappings/openspg/README.md).
- [SDM fixtures](domains/vector-borne-disease/): synthetic source notes, model/variable records and a worked decision pathway.
- [Architecture](docs/architecture.md), [integration status and verification](docs/integrations.md), [student guide](docs/student-guide.md).
- [Benchmarks](experiments/benchmarks/): shared queries, contexts and relevance judgments.
- [Roadmap](docs/roadmap.md), [issue plan](planning/issues.json), [milestones](planning/milestones.json).
- [Design and decisions](docs/design/2026-11-06-research-testbed.md).

## Boundaries

This local demo has no authentication, multiuser storage, external ingestion endpoint, automatic knowledge promotion or production deployment. The configured catalog Python client is read-only and tested with mocked HTTP contracts. SVO identifiers in fixtures remain unset until expert alignment. No secrets belong in source control. See [verification](docs/verification.md) for checks actually performed and outstanding work.
