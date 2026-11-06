# Verification record — 2026-11-06

## Completed locally

- Python 3.12.13: **65 tests passed**, including API modes/bounds, streamed body limit, provenance tampering, SHACL positive/negative cases, mapping coverage, catalog mock failures/timeouts, benchmark arithmetic/reproducibility and publication dry-run/order/resume behavior.
- Tests exercised an installed wheel, not an import from the repository root. Source distribution and wheel builds succeeded.
- CLI benchmark generated `experiments/benchmarks/example-result.json`; four synthetic questions across three offline modes. Result scores establish mechanics only.
- Base Compose and optional vector override configuration validation passed. Base Compose image built and the API container started healthy on localhost port 8091 without optional database credentials.
- Browser verification: workbench rendered, compare retrieval produced evidence in all three columns, blank pathway reported missing fields, shared benchmark completed and enabled export. Swagger API docs loaded successfully under route-specific security policy.
- Independent architecture/security review preceded implementation; independent QA/tester review found docs CSP, default Compose variable, streamed body size and duplicate rank defects; all four were corrected with regression tests.

## Not verified

- OpenSPG server deployment, actual SPG schema commit, KAG ingestion/query and citation preservation.
- Live DYNAMO catalog response/auth/version or SVO vocabulary lookup and scientific variable alignment.
- Optional pgvector service startup, migrations, indexing and actual database retrieval.
- Scientific extraction, generated-answer faithfulness, scientific model applicability or real SDM execution.
- Hosted CI results until GitHub Actions has run; local tests do not imply remote CI passed.
- DSO architecture registry changes are proposed in docs/dso-registration.md and tracked as an issue; no changes to the separate checkout were made.

One upstream warning remains: Starlette TestClient deprecates its httpx backend in favor of httpx2. Tests currently pass using the pinned httpx release. This is a future dependency migration, not a failed integration check.
