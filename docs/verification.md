# Verification record — 2026-11-06

## Completed locally

- Python 3.12.13: **65 tests passed**, including API modes/bounds, streamed body limit, provenance tampering, SHACL positive/negative cases, mapping coverage, catalog mock failures/timeouts, benchmark arithmetic/reproducibility and publication dry-run/order/resume behavior.
- Tests exercised an installed wheel, not an import from the repository root. Source distribution and wheel builds succeeded.
- CLI benchmark generated `experiments/benchmarks/example-result.json`; four synthetic questions across three offline modes. Result scores establish mechanics only.
- Base Compose and optional vector override configuration validation passed. Base Compose image built and the API container started healthy on localhost port 8091 without optional database credentials.
- Browser verification: workbench rendered, compare retrieval produced evidence in all three columns, blank pathway reported missing fields, shared benchmark completed and enabled export. Swagger API docs loaded successfully under route-specific security policy.
- Independent architecture/security review preceded implementation; independent QA/tester review found docs CSP, default Compose variable, streamed body size and duplicate rank defects; all four were corrected with regression tests.

- GitHub Actions passed both Python 3.12 and 3.13 jobs: https://github.com/wmobley/scientific-dss-kag/actions/runs/42290329473 (initial implementation commit bd0e96b).
- Public repository created and pushed; three milestones and nine issues published. Each issue added immediately to Research Dashboard project 5. Published links are in planning/published-links.json.

## Not verified

- OpenSPG server deployment, actual SPG schema commit, KAG ingestion/query and citation preservation.
- Live DYNAMO catalog response/auth/version or SVO vocabulary lookup and scientific variable alignment.
- Optional pgvector service startup, migrations, indexing and actual database retrieval.
- Scientific extraction, generated-answer faithfulness, scientific model applicability or real SDM execution.
- DSO architecture registry changes are proposed in docs/dso-registration.md and tracked as an issue; no changes to the separate checkout were made.

One upstream warning remains: Starlette TestClient deprecates its httpx backend in favor of httpx2. Tests currently pass using the pinned httpx release. This is a future dependency migration, not a failed integration check.

## M2 step 0 — LLM policy, gateway, endpoint (2026-11-06)

- 143 tests pass locally, including policy, gateway (auth, route allowlist, shared rate limit, call cap, 429 pause, no body/key leaks) and chat-completions contracts.
- Live, through the local gateway to `ai.tejas.tacc.utexas.edu`: `openai-smoke` succeeded (`live_verified: true`) with `gpt-oss-120b` and `E5-Mistral-7B-Instruct`; the answer cited retrieved evidence. 15 upstream calls were counted against a cap of 20.
- Not verified: behaviour under a real upstream 429 (only mocked), Compose-to-gateway connectivity, answer quality beyond protocol checks, OpenSPG/KAG, DYNAMO, SVO, pgvector (unchanged).

## M2 DYNAMO catalog and crosswalk (2026-11-06)

- 182 tests pass locally, including contract tests against responses recorded from the dev catalog (paging, list-valued fields, nested `sameAs`, failure modes) and crosswalk validation (missing IDs, wrong SVO URIs, review-state rules).
- Live, anonymous, GET-only: the dev catalog returned 692 standard variables (294 with SVO `sameAs`) and 23 models. `scientific-dss catalog-verify` passed for `groundwater-subsidence` (7 unreviewed entries; 4 candidates with SVO, 1 without) and `vector-borne-disease` (2 unreviewed entries; documented gaps).
- Not verified: production catalog host, authenticated reads, writes, human review of any crosswalk entry (none accepted), scientific suitability of any candidate.

## M2 OpenSPG/KAG local verification (2026-11-07)

Setup: OpenSPG server v0.8 built from the GitHub source (commit `ceeb3ef549df`), KAG v0.8.0 (commit `de777280584f`), official `mariadb:10.5` and `neo4j:5.26` (5.26.32, APOC 5.26.32) images pinned by digest, DozerDB plugin 5.26.32-1.2.0 (sha256 verified), models `Qwen3-235B-A22B-Instruct-2507` (extraction), `gpt-oss-120b` (answers), `E5-Mistral-7B-Instruct` (4096-dimension embeddings), all through the local gateway. 210+ offline tests pass.

Verified live (synthetic `groundwater-subsidence` corpus):
- Project created on the server; the schema (KAG scaffold plus our decision-pathway types, 32 types) committed; KAG added its system types.
- Ingested 4 reviewed passages with 0 failures (about 14 model calls). The graph has 114 entities, many typed with our classes (27 ScientificVariable, 16 ComputationalModel, 10 ScientificMethod, 3 DecisionProblem), 4 Chunk nodes and 112 entity-to-chunk `source` relationships. **Chunk `id` equals our canonical evidence ID** (`ev-gw-drawdown`, ...).
- One question through KAG's solver (25 calls) returned a referenced answer. Every reference's `chunk_id` was one of our evidence IDs, ranked with scores; the drawdown evidence was ranked first and supported both cited statements. Total gateway use: 82 of 200 calls, no 429s.

Findings and limitations:
- KAG rewrites chunk text (quotes, title prefix, one sentence per line). The passage is equivalent after normalisation but not byte-identical, and KAG does not store our source hash or offsets: both must be resolved from our corpus by evidence ID.
- Inside the answer, KAG uses tags `chunk:{step}_{index}`. The trace did not expose the tag-to-document mapping, so per-sentence attribution is **not independently verified**; the retrieved set is.
- KAG v0.8.0's knowledge-unit extractor crashes on every model tried because its prompt contradicts itself ("Core Entities" as dict vs string); the schema-free extractor is used instead. The generic template's `default_generator` does not exist in v0.8.0; `llm_index_generator` is used.
- The final answer was written in Chinese for an English question although the English prompt was selected and the project language is `en`; the cause is unresolved.
- The OpenSPG server makes model calls itself during project creation (config checks), so the gateway must be reachable from the container.
- Not verified: the KAG adapter behind `/retrieve mode=kag` (still 503), failure paths (server down, malformed results, gateway cap reached), quality of the answer or the extracted graph, anything beyond one domain and one question.
