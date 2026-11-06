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
