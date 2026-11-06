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
# Optional unused vector-store experiment infrastructure:
docker compose -f compose.yaml -f compose.vector.yaml --profile vector-store up --build
# Stop without deleting retained database volumes:
docker compose stop
```

The optional database has no published host port. Its named volume is retained. No automatic SQL migrations, vector indexing or database retrieval are implemented. `config --quiet` verifies configuration only; it does not prove container images build or services run.

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
