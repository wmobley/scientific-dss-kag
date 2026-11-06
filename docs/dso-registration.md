# DSO architecture registration proposal

This scaffold is a new local research testbed. Proposed cluster: **new research cluster** pending DSO maintainer confirmation. Proposed development host port: **8091**, configurable with DSS_PORT. Production URL and deployment target: **none**. No live dependency is enabled by default.

The supplied DSO path was stale; the readable local checkout is `/Users/wmobley/Documents/Github/DSO-Architecture/`. Its context pages currently live under `docs/claude-context/`, not `docs/Codex-context/`.

A follow-up issue tracks applying this registration in the separate architecture repository. Prepare a `docs/services/scientific-dss-kag.md` service page using its existing template:

- Locations: repository `https://github.com/wmobley/scientific-dss-kag`, Python/FastAPI, local research-only.
- Start locally: README Python setup; uvicorn localhost port 8091 or Compose.
- API endpoints: GET health/integrations/catalog models/catalog variables; POST retrieve/validate pathway/evaluate. No execution endpoints.
- Integrations: OpenSPG draft mapping, mocked read-only DYNAMO client, synthetic SVO alignment; all live unverified. pgvector optional unused infrastructure.

After maintainer confirms cluster and port, add service to `docs/claude-context/repo-map.md`, `docs/dev/port-reference.md`, and `mkdocs.yml` nav; run the repository's `python generate.py` and inspect resulting graph changes. No edits or pushes to that separate repository were made as part of this scaffold. This proposal is not a claim of completed DSO registration.
