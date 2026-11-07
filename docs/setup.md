# Setup and reproducibility

Use Python 3.12 or 3.13 and the README installation commands. Core runtime dependencies are pinned in pyproject.toml; python-dotenv has a constrained compatible range. uv.lock captures a complete resolved environment. With uv installed, `uv sync --extra dev --frozen` reproduces that environment. The package includes the ontology, domain fixtures, benchmark and browser assets, so a wheel installation runs independently of the checkout.

## Commands

```bash
python -m pytest -q
scientific-dss benchmark --k 3 > benchmark.json
uvicorn scientific_dss_kag.api:app --host 127.0.0.1 --port 8091
```

Keep the API on localhost. The Docker container listens on port 8000 internally; Compose publishes it on `127.0.0.1:${DSS_PORT:-8091}`. The host port is a proposed research-demo choice; it is not an approved production endpoint.

## Compose

Copy `.env.example` to `.env` locally if needed; replace the database password only for the optional vector override. Keep that file private. The default API works without `.env` or database credentials. The optional `compose.vector.yaml` override requires POSTGRES_PASSWORD.

```bash
docker compose config --quiet
docker compose up --build
# Stop without deleting retained database volumes:
docker compose stop
```

`config --quiet` verifies configuration only; it does not prove container images build or services run.

## Persistent embeddings (pgvector)

Optional and local. The vector store keeps one embedding per reviewed evidence passage, per domain and embedding model, and the `pgvector` retrieval backend embeds only the query at request time.

```bash
python scripts/init_openspg_env.py            # creates .env.openspg incl. POSTGRES_PASSWORD (skip if it exists)
docker compose -f compose.vector.yaml --env-file .env.openspg --profile vector-store up -d   # 127.0.0.1:5439, image pinned by digest
set -a; . ./.env.openspg; set +a              # exports POSTGRES_PASSWORD (and the gateway token) for the commands below
uv run scientific-dss vector-migrate          # applies the bundled SQL once; safe to repeat
uv run scientific-dss vector-index --domain groundwater-subsidence     # explicit and paid: one batched embedding call
uv run scientific-dss vector-status --domain groundwater-subsidence
uv run scientific-dss compare-backends --domain groundwater-subsidence # len(cases) + 1 embedding calls
```

Point the commands at the gateway with `DSS_GATEWAY_URL` as for any model call. Then `POST /retrieve` with `"backend": "pgvector"` (localhost Host only). If the corpus or model changed since the build, or the index is partial, the API answers 409 `vector_index_stale` and tells you to rebuild; it never answers from stale vectors. The 4096-dimension vectors have no approximate index (pgvector indexes at most 2000 dimensions, or 4000 as `halfvec`), so search is exact, which is fine for a corpus of this size. Stored vectors are float32, so similarities differ from the in-memory backend by about 1e-6. Tests that need the database run only when `POSTGRES_PASSWORD` is exported and the database answers; otherwise they skip. `docker compose -f compose.vector.yaml --env-file .env.openspg --profile vector-store down -v` also deletes the stored vectors (rebuildable).

## Ontology validation

```bash
python -m pyshacl -s ontology/shapes.ttl -e ontology/decision-pathways.ttl ontology/examples/valid.ttl
python -m pyshacl -s ontology/shapes.ttl -e ontology/decision-pathways.ttl ontology/examples/invalid.ttl
```

The second command should report nonconformance. Only parse trusted local RDF. The API never accepts RDF locations or imports remote ontologies.

## Troubleshooting

If port 8091 is busy, change the uvicorn port or DSS_PORT. If Docker is unavailable, use the Python path; offline tests need neither Docker nor credentials. Live KAG requests intentionally return 503. A benchmark with perfect scores on this small synthetic corpus is not evidence of scientific usefulness.

## OpenAI

Read openai.md to configure server-side credentials and enable explicit paid actions. Both direct Python startup from the checkout and Compose support the local .env. Use one server worker; restarting resets the in-memory vector cache and process request budget. Never run `docker compose config` without `--quiet` when sharing output: expanded configuration may contain the API key. Default tests/benchmark do not call OpenAI.

## OpenSPG / KAG local stack (M2 verification)

Everything here is local, localhost-only and uses synthetic data. See `docs/design/2026-11-06-kag-deployment.md` for why each step exists. Docker Desktop needs roughly 5 GB free for the stack (server about 1.4 GB, Neo4j about 1 GB, MariaDB about 0.1 GB, plus the server image build); stop other containers or raise Docker's memory first.

1. Sources (tags are pinned): `git clone --depth 1 --branch v0.8 https://github.com/OpenSPG/openspg.git work/openspg/src` and `git clone --depth 1 --branch v0.8.0 https://github.com/OpenSPG/KAG.git work/kag/KAG`.
2. DozerDB plugin (GPL-3.0; adds the per-project `CREATE DATABASE` that KAG needs): download `dozerdb-plugin-5.26.32-1.2.0.jar` and its `.sha256` from the `5.26.32-1.2.0` release of github.com/DozerDB/dozerdb into `work/neo4j-plugins/`. The Neo4j image build re-verifies the checksum.
3. `python scripts/init_openspg_env.py` creates `.env.openspg` (random passwords and the gateway token, mode 0600, git-ignored).
4. Start the gateway so every model call is rate limited and capped: `DSS_GATEWAY_TOKEN=... DSS_LLM_MAX_CALLS=200 uv run scientific-dss gateway`.
5. `docker compose -f compose.openspg.yaml --env-file .env.openspg up -d --build`. The server is built from source with Maven (several minutes the first time).
6. KAG client: `uv venv --python 3.10 work/kag/.venv && uv pip install --python work/kag/.venv/bin/python -c openspg/kag-constraints.txt -e work/kag/KAG`.
7. `uv run python scripts/render_kag_config.py --domain groundwater-subsidence`, then from `work/kag/project`: `../.venv/bin/python ../../../scripts/kag_create_project.py ../kag_config.yaml`, copy `work/kag/kag_config.yaml` over the project's `kag_config.yaml`, run `python scripts/compose_kag_schema.py work/kag/project/GwSubsidence/schema/GwSubsidence.schema`, then `knext schema commit` in the project directory.
8. Ingest and query from the project directory with `scripts/kag_ingest.py ../../evidence.csv` and `scripts/kag_query.py "question"` (both run with the KAG virtualenv's python).

Stop with `docker compose -f compose.openspg.yaml --env-file .env.openspg stop`; `down -v` also deletes the graph, MySQL and Neo4j volumes (synthetic data only).
