# M2 issue #1: deploy and verify OpenSPG/KAG (deployment plan)

## Status
Implementing (infrastructure only; KAG client install awaits approval)

## Objective
Run a pinned, localhost-only OpenSPG server, commit the draft decision-pathways schema, ingest a domain's synthetic evidence through KAG using only our rate-limited LLM gateway, answer a question through KAG, and verify that citations (our canonical evidence ID, source hash and offsets) survive. Then replace the 503 on `/retrieve mode=kag` with a real adapter. Parent spec: `2026-11-06-m2-verified-integrations.md`.

## User need
The repo is named for KAG, and M2 only counts as done when KAG is verified, not just drafted. The owner approved Docker use, the OpenAI-compatible-endpoint policy and the shared call limit (100/min total on the TACC endpoint).

## Current code/system summary
- KAG adapter does not exist; `/retrieve mode=kag` returns 503. A draft schema exists at `ontology/mappings/openspg/decision-pathways.schema`.
- Gateway, policy check, per-domain loading and a live-verified TACC endpoint exist (see the parent spec and `docs/verification.md`).
- This machine: Apple Silicon (arm64), Docker Desktop 29.9, **8 GB memory allocated to Docker** (host has 48 GB), 372 GB disk free, ports 8887/3306/7474/7687/9000/9001 free.

## What upstream actually is (inspected 2026-11-06, nothing run)
- KAG: latest release **v0.8.0** (2025-06-28), Apache-2.0; repo active (last push 2026-01-28). OpenSPG server: latest release **v0.8** (2025-06-29), last push 2025-07-05, i.e. the server has been idle for about 16 months while KAG master moved on. Plan: use KAG tag `v0.8.0` only, never master.
- The upstream compose file (`dev/release/docker-compose-west.yml`):
  - images come from `spg-registry.us-west-1.cr.aliyuncs.com/spg/...` (a third-party Alibaba Cloud registry) with `:latest` tags;
  - default credentials: MySQL root `openspg`, Neo4j `neo4j@openspg`, MinIO `minio@openspg`;
  - publishes ports 8887, 3306, 7474, 7687, 9000, 9001 on all interfaces;
  - JVM `-Xmx8192m` plus Neo4j heap 4G and page cache 1G: does not fit in Docker's current 8 GB;
  - `--builder.model.execute.num=20` (server-side LLM concurrency of 20).
- Image digests (multi-arch, include arm64), looked up without pulling: server `0.8` = `latest` = `sha256:fe6708deef9ebb8da8da7b1cb643e83b827769a5be8811961311639aa1f2cb88`; mysql `0.8` = `sha256:491e44f0e91dacdc8e76b66d875e6cbae75ab7fff0101f71fb3460a8bfb6509b` (its `latest` is newer and differs); neo4j `latest` = `sha256:4bc5b7f6b83d333b1d2c8f60ac145c068d77d50bca65b3a07c927f9e2a541eb9` and minio `latest` = `sha256:9493c8e8f77edb10d556255d49ba8b5761b0fe57889235dfd10619c0513da007` (no version tags exist for these two).
- KAG's LLM config (`kag_config.yaml`) has `openie_llm`, `chat_llm` (`type: maas`, `base_url`, `api_key`, `model`) and `vectorize_model` (`type: openai`, `base_url`, `model`, `vector_dimensions`). Builders and solvers run in the **client Python process**; the server stores the graph. Concurrency is set by `num_threads_per_chain` x `num_chains`.
- KAG's LLM client wraps the official `openai` SDK, whose defaults include automatic retries; the client timeout defaults to none. Because every call goes through our gateway, retries are counted and rate limited, and an upstream 429 pauses all callers.
- Not yet read: how KAG chunk objects can carry our evidence ID, source hash and offsets. This is the main unknown for the citation requirement (see Risks).

## Proposed design
1. **Our own compose file** `compose.openspg.yaml` at the repo root (matching `compose.yaml` and `compose.vector.yaml`), not the upstream file. **Option A (chosen 2026-11-06): no images from the Alibaba registry.**
   - the server is built from the GitHub source at tag `v0.8` (commit `ceeb3ef549df`, cloned to `work/openspg/src`) with `openspg/Dockerfile.server`: Maven in an official `maven:3.9-eclipse-temurin-8` stage, then an official `eclipse-temurin:8-jre-jammy` runtime, running as a non-root user;
   - MySQL is the official `mariadb:10.5` image with the repo's init SQL mounted read-only (this is what upstream's image is made of);
   - Neo4j is the official `neo4j:4.4` image with the APOC plugin (the server uses the Neo4j 4.4.7 driver); MinIO is omitted because the server config never references it, and is added only if the server needs it;
   - all base images pinned by digest (the Alibaba digests listed above are kept only as the fallback, option B);
   - every port bound to `127.0.0.1`;
   - passwords generated randomly into a new git-ignored `.env.openspg` (never the upstream defaults);
   - JVM `-Xmx3g`, Neo4j heap 1G/2G and page cache 512m so it fits Docker's 8 GB (a restart of Docker Desktop with 12-16 GB would be better; that is a Docker setting you would change);
   - `--builder.model.execute.num=2`;
   - **no LLM key or LLM settings anywhere in the containers**: we use only the client-side workflow, so the server never calls an LLM.
2. **KAG client** installed at tag `v0.8.0` into `work/kag/` (git-ignored, outside the project environment), with its own virtual environment. Its dependency set is large and third-party; installing it executes third-party code, so it is part of what you approve.
3. **`scripts/render_kag_config.py`** generates `kag_config.yaml` from our settings into `work/kag/`: `base_url` = the local gateway (`http://127.0.0.1:8092/v1`), `api_key` = the throwaway gateway token (never the TACC key), models from `.env`, `vector_dimensions: 4096` for `E5-Mistral-7B-Instruct`, and low concurrency (1 chain, 1 thread to start).
4. **Policy extension**: `policy-check` also validates the rendered KAG config (every LLM `base_url` is the gateway; no upstream key present) and the OpenSPG compose file (loopback-only ports, no LLM environment variables, no `:latest`).
5. **Verification run** on the `groundwater-subsidence` domain, with `DSS_LLM_MAX_CALLS=200` on the gateway:
   1. server health; schema commit; class and relation lookup;
   2. ingest the four reviewed synthetic passages, each carrying evidence ID, source hash and offsets;
   3. query through KAG and map the answer's supporting chunks back to our evidence IDs;
   4. failure paths: server down, malformed result, gateway cap reached;
   5. record gateway call counts, versions and digests, with credentials removed, in `docs/verification.md`.
6. **Adapter** `kag_adapter.py` behind `mode: kag`, returning results in the same shape as the other modes, with explicit 503s when the server is unavailable.

## Files likely affected
New: `compose.openspg.yaml`, `scripts/render_kag_config.py`, `src/scientific_dss_kag/kag_adapter.py`, tests (policy, adapter with recorded responses), `.env.openspg` (ignored). Changed: `policy.py`, `retrieval.py`, `api.py`, `connectors.py` (status), `.gitignore`, docs.

## API/schema changes
`/retrieve mode=kag` becomes functional once verified. `/integrations` kag status moves from `mapping_draft` only after the verification run passes. The OpenSPG schema is committed to a **local** OpenSPG project; nothing is published anywhere external.

## Data flow
Synthetic passages -> KAG client (local) -> gateway (local, rate limited) -> TACC endpoint (chat, embeddings) -> KAG client -> OpenSPG server (local, localhost-only) -> query -> results mapped to evidence IDs. The OpenSPG containers make no outbound LLM calls.

## Risks and tradeoffs
- **Citation preservation is unproven.** KAG chunks may not carry custom properties such as our source hash and offsets. If not, options are a custom builder component or storing our identifiers in chunk names/content and mapping back. If neither works, we report that KAG does not preserve citations as-is, which is a valid M2 finding.
- **Third-party images from a foreign registry**, unaudited, pinned by digest but not scanned. Containers will run with default Docker isolation on localhost only; no host mounts beyond named volumes.
- **Server idle since July 2025** while KAG evolves; pinned versions limit skew but may be unsupported upstream.
- **Memory**: the reduced heap may be too small for larger corpora; fine for four passages.
- **Throughput and cost**: at the gateway default of 40 calls/min a 200-call ingestion takes at least 5 minutes, longer if the shared endpoint is busy. KAG/SDK retries consume the same call cap.
- **Model quality**: KAG's extraction prompts were tuned on other models; `gpt-oss-120b` (reasoning) and `Qwen3-235B-A22B-Instruct-2507` will be compared on the synthetic passages. KAG sends raw text to the embedding model, so `E5-Mistral-7B-Instruct` queries will lack the instruction prefix our own adapter adds, which can lower retrieval quality.
- **KAG's `think` option** sends `chat_template_kwargs`; the TACC endpoint may reject or ignore it (to be probed).
- Verification here means protocol and citation mechanics, not scientific quality.

## Alternatives considered
- Use the upstream compose file as-is: rejected (default credentials, all-interface ports, `:latest`, heap too large).
- KAG's server-side product UI for models: rejected; it would store LLM settings in the server's database and bypass the gateway.
- Skip KAG and rely on pgvector: rejected; verifying KAG is the stated M2 goal. pgvector follows as the comparison baseline.
- Build the adapter before verifying: rejected; verify the mechanics first.

## Test plan
Offline: policy tests for KAG config and compose; adapter tests against recorded responses (shape, citation mapping, unavailable server, malformed results). Live (explicit, local): the verification run in the Proposed design, capped at 200 gateway calls, recorded with versions and digests. If the citation mapping fails, the failing behavior is recorded as the result.

## Documentation plan
Update `docs/integrations.md` (KAG), `docs/setup.md` (start/stop, memory, ports), `docs/verification.md`, and later the DSO-Architecture service page (with approval).

## Rollout/rollback plan
Local only. Start with `docker compose -f compose.openspg.yaml --env-file .env.openspg up -d`; stop and remove with `down -v` (deletes the local graph, MySQL and MinIO volumes, which only hold synthetic data). Remove `work/kag/` to uninstall the client. No external writes.

## Open questions
1. Approve pulling the four images from the Alibaba Cloud registry (pinned digests, arm64)?
2. Approve cloning KAG `v0.8.0` and installing its dependencies into an isolated environment under `work/kag/`?
3. Docker memory: OK to run with the reduced heaps in 8 GB, or will you raise Docker Desktop's memory first (recommended: 12-16 GB)?
4. Which synthetic domain for the first run: `groundwater-subsidence` (proposed)?

## Decisions
- 2026-11-06: owner chose option A (build from GitHub source and use official Docker Hub images; fall back to the pinned Alibaba images only if the build or Neo4j 4.4 compatibility fails, and report that). Docker Hub's `openspg/*` images (last updated 2024) and GHCR (none) are unusable for v0.8.
- 2026-11-06: use our own pinned, localhost-only compose file and a client-side KAG workflow so no LLM settings live in the containers; KAG talks only to our gateway.

- 2026-11-06 (implementation log, option A): the OpenSPG v0.8 server **builds from the GitHub source** (Maven in an official `maven:3.9-eclipse-temurin-8` stage; image `scientific-dss-openspg-server`, 538 MB). Problems found and fixed: (1) a transient timeout fetching a GeoTools artifact from `repo.osgeo.org` (now retried and cached); (2) the project writes the jar to `dev/release/server/target/`, not the module's `target/`; (3) the non-root user could not create `./logs` (fixed in the Dockerfile). MariaDB 10.5 and Neo4j 4.4 (official images, APOC downloaded at start) start healthy. **Blocked:** the server JVM is killed (exit 137) in a restart loop because Docker Desktop's VM has 8 GB (`MemoryMiB` 8092) and about 26 other containers already use most of it (about 2.2 GB free with our stack stopped). Our stack needs roughly 4-5 GB. Resolution needs more Docker memory (recommended 16 GB; the host has 48 GB) or freeing memory from unrelated containers; both are the owner's call, because changing Docker's memory restarts every container. The stack is stopped (volumes kept); the server has not yet reached a healthy state, and no KAG verification has happened.

- 2026-11-07 (implementation log): after the owner stopped the 26 other Docker containers, the stack runs healthy in Docker's 8 GB: server about 1.4 GiB, Neo4j about 1.0 GiB, MariaDB about 0.1 GiB; `Started Application in 4.5 seconds`; zero error lines in the server log. Checked: ports bound to 127.0.0.1 only (MySQL not published); MariaDB initialised 34 tables from the repo SQL; Neo4j 4.4 has APOC 4.4.0.40; `GET /public/v1/project` returns `[]` with HTTP 200. Not yet exercised: the server's Neo4j connection (needs a project and schema commit), KAG client, ingestion, queries, citations. The other containers stay stopped until the verification run ends; the list of what was running is kept outside the repo so it can be restored, and restarting them is the owner's call.

- 2026-11-07 (implementation log, KAG client approved and installed): KAG v0.8.0 (commit `de777280584f`) installed into `work/kag/.venv` (Python 3.10). Corrections to this plan found by running it:
  1. **Neo4j must be 5.x, not 4.4.** The server issues `CREATE VECTOR INDEX`, which needs Neo4j 5.13+. Switched to the official `neo4j:5.26` image (5.26.32, APOC 5.26.32); a 4096-dimension vector index was created ONLINE as a test and dropped. The empty 4.4 volume was removed.
  2. **The server runs KAG's Python in-process (pemja), so the image needs Python 3.10, pemja 0.4.0, KAG and `git`.** Built from the pinned KAG checkout via a named build context; `--python.paths` is `;`-separated and must include `site-packages/kag` because the server imports the top-level module `bridge`; `KAG_PROJECT_HOST_ADDR` must be set for that Python.
  3. **The server itself makes LLM and embedding calls** (project creation runs `run_llm_config_check` and `run_vectorizer_config_check` inside the container). The earlier statement that no LLM traffic happens in the containers was wrong. They reach the gateway at `host.docker.internal:8092` (verified: 401 without a token), while the host uses `127.0.0.1`; `scripts/kag_create_project.py` swaps the host only in the request sent to the server. Those calls still pass through the gateway and are counted (18 of 200 used so far).
  4. **KAG creates one Neo4j database per project (`CREATE DATABASE`)**, which Neo4j Community does not support (Enterprise only). Upstream's custom image evidently uses DozerDB (it mounts a `dozerdb` directory). **Project creation is blocked on this.** Options: (a) the DozerDB plugin JAR (GPL-3.0, github.com/DozerDB/dozerdb, release `5.26.32-1.2.0`, 8 MB) mounted into the official `neo4j:5.26` image; it was downloaded to `work/neo4j-plugins/` and its sha256 matches the published value, but it has NOT been loaded because it is a third-party binary that needs the owner's approval; (b) Neo4j Enterprise under Neo4j's evaluation licence (the owner would have to accept that licence); (c) upstream's Alibaba `openspg-neo4j` image (unaudited); (d) patching the server source to skip `CREATE DATABASE` (modifies third-party code).

## User feedback / decisions
- Pending review.
