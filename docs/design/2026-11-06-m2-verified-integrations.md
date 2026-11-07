# M2: Verified KAG and scientific integrations, OpenAI-only LLM policy

## Status
Implemented, with one human step outstanding (review of the crosswalk entries) and the follow-ups listed below

## Objective
Complete milestone M2 (issues #1-#4): verify OpenSPG/KAG, the DYNAMO catalog and SVO against real systems, and add persistent hybrid retrieval. Enforce one cross-cutting rule: **every LLM or embedding call made by this project at runtime uses the OpenAI-compatible API protocol, through one audited path, against one configured endpoint.** "OpenAI API" means the protocol: OpenAI-compatible servers such as the TACC-hosted Llama endpoint qualify.

## User need
The owner wants M1's offline scaffold turned into verified integrations, with the OpenAI-compatible API as the only LLM interface so cost, data-sharing and reproducibility have a single point of control.

## Current code/system summary
- 104 tests pass locally. M1 is published on GitHub; the OpenAI provider work is uncommitted.
- `openai_provider.py` is the only LLM client: fixed base URL `https://api.openai.com/v1/` (to be made configurable), embeddings and strict-JSON `/responses`, a 60-attempt process budget, no retries, `store=false`. Settings come from `settings.py` (`DSS_OPENAI_ENABLED`, `OPENAI_API_KEY`, `OPENAI_RESPONSE_MODEL`, `OPENAI_EMBEDDING_MODEL`).
- `/retrieve mode=kag` returns 503; the KAG adapter does not exist. `connectors.py` has a mocked read-only catalog client. SVO URIs are null fixtures. pgvector is provisioned in `compose.vector.yaml` but unused.
- Not verified (per `docs/verification.md`): OpenSPG deployment, schema commit, KAG ingest/query/citations, live DYNAMO and SVO, pgvector retrieval.
- Nothing currently *prevents* a second LLM provider from being introduced. OpenSPG/KAG ships its own LLM client configured separately.

## Proposed design

### 0. OpenAI-only LLM policy (built first; gates everything else)
Scope: runtime behaviour of this project and the services it deploys. Developer tooling (e.g. coding assistants) is out of scope.

1. **Single egress, configurable endpoint.** All LLM/embedding traffic from our code uses `OpenAIProvider`. Extend it rather than adding clients. The base URL becomes server-side config (`OPENAI_BASE_URL`, default `https://api.openai.com/v1`) instead of a hard-coded constant. It must be `https`, and its host must be on an explicit allowlist (`api.openai.com`, `ai.tejas.tacc.utexas.edu`) because the API key is sent to it. Clients can never supply it.
2. **Compatibility is verified, not assumed.** The current adapter uses `/responses` with strict JSON schema. Many OpenAI-compatible servers (including likely the TACC endpoint) support only `/chat/completions` and `/embeddings`, and may not support strict schemas. A read-only probe (`/models`, one tiny chat call, one tiny embedding call) determines what the endpoint supports. The adapter then supports `/chat/completions` with JSON-schema or JSON-mode output, with local validation of claims and citations as today. Embedding dimension is read from the response, not assumed.
3. **Generated KAG config.** The KAG `chat` and `vectorize` blocks are rendered from the same settings by `scripts/render_kag_config.py` into a gitignored path. Base URL, models and key are never hand-edited or committed.
4. **Machine-checked policy** (`tests/test_llm_policy.py`, also `scientific-dss policy-check` CLI):
   - source scan: no vendor-specific provider SDKs and no HTTP client construction outside an allowlist (`openai_provider.py`, `connectors.py` for the non-LLM catalog);
   - rendered KAG config: every LLM `base_url` equals the configured endpoint, and every model equals the configured model;
   - Compose and `.env`: no provider settings that point somewhere other than the configured endpoint; warn if `LANGSMITH_TRACING=true`, since traces would send prompts to a second third party.
5. **Rate limit (100 calls/minute total across the whole endpoint, per the owner; other users share it).** The limit applies to the endpoint as a whole, so every consumer must share one limiter. KAG runs as a separate process with its own client, so an in-app limiter cannot see its calls. Design: a small localhost-only **LLM gateway** (an OpenAI-compatible pass-through, `scientific-dss gateway`) is the only thing that talks to the upstream endpoint. Both our app and the KAG config point at it. The gateway:
   - enforces a sliding-window limit below the real one (default **40/minute**, configurable; the pool is shared with other users, so our share must be conservative), queueing callers instead of failing them, with a bounded queue and timeout;
   - counts every upstream HTTP attempt, replacing the separate per-process counters, and applies the per-run call caps (60 app / 200 KAG ingestion);
   - on a 429 (likely when others are busy), honours `Retry-After` if present, otherwise backs off exponentially up to a bounded wait, pauses all callers, and fails the request with an explicit error after a bounded total wait; the only retries are these limiter-controlled waits, never blind resends;
   - holds the real API key, so KAG's config contains only the local gateway URL and a throwaway token;
   - exposes `/integrations`-style status: calls in the last minute, queue depth, last 429.
   This also gives the policy a single choke point: the allowlist check lives in the gateway, and the policy test only has to prove everything points at it.
6. **Visibility.** `/integrations` reports the configured endpoint host, models, probe-verified capabilities and the last policy-check result. No silent fallback to another provider; failures are explicit.
5. **Budget.** The 60-attempt budget covers only our process. KAG ingestion can make many calls, so M2 adds a separate declared per-run ingestion budget (see Open questions).

### 1. OpenSPG/KAG (issue #1)
Deploy a pinned upstream OpenSPG stack on localhost with exact commits and image digests recorded, using the generated OpenAI config. Commit the draft schema, ingest synthetic passages preserving canonical ID, source hash and offsets, implement a KAG adapter behind `mode: kag`, and verify citations survive retrieval. Test server-down and malformed-result paths. Exact KAG config keys for an OpenAI endpoint are **to be confirmed against the pinned version**, not assumed.

### 2. DYNAMO catalog (issue #2)
Confirm the real base URL, auth and API version (not documented today), run read-only calls only, add contract tests from recorded responses, and implement a human-reviewed model-to-ontology crosswalk file. No LLM is used to auto-approve crosswalk entries.

### 3. SVO (issue #3)
Pick and record a vocabulary source/version, align the scientific variables with units/context, store confidence and reviewer, add a real client with contract tests. LLM-suggested candidates are allowed only via `OpenAIProvider` and are marked unreviewed until a human accepts them.

### 4. Persistent hybrid retrieval (issue #4)
Add migrations and a pgvector index for evidence embeddings with `text-embedding-3-small`, storing model name, dimension and corpus hash per row. Rebuild is explicit. Compare against the existing offline modes on the same benchmark.

### Order and gates
0 policy + commit existing OpenAI work → 2 and 3 (read-only contract checks, cheap) → 4 → 1 (largest deployment). Each step ends with tests plus an updated `docs/verification.md` stating what was and was not verified.

## Files likely affected
New: `scripts/render_kag_config.py`, `src/scientific_dss_kag/kag_adapter.py`, `src/scientific_dss_kag/vector_store.py`, migrations, `tests/test_llm_policy.py`, KAG/catalog/SVO contract tests, crosswalk data under `domains/vector-borne-disease/`. Changed: `openai_provider.py`, `settings.py`, `connectors.py`, `retrieval.py`, `api.py`, `cli.py`, `compose*.yaml`, `.env.example`, `.gitignore`, `docs/{integrations,setup,architecture,verification,openai}.md`, `planning/*`.

## API/schema changes
`/retrieve mode=kag` becomes functional; `/integrations` adds `llm_policy` and per-integration verification state; pgvector tables added (database mutation, local only). Ontology files unchanged except real `svo_uri` values after verification.

## Data flow
Synthetic/reviewed passages → the configured OpenAI-compatible endpoint (embeddings, KAG extraction) → local OpenSPG and pgvector → retrieval → optional answer generation. Catalog and SVO are read-only inbound. The only outbound LLM destination is the one allowlisted endpoint.

## Risks and tradeoffs
- KAG ingestion may issue many paid OpenAI calls; mitigated by a declared budget and the synthetic-only corpus.
- OpenSPG is a large upstream stack with default credentials; it must bind to localhost with changed credentials.
- DYNAMO/SVO contracts may differ from what the docs imply; verification may force scope changes.
- The gateway is one more local service to run and keep healthy; if it is down, LLM features fail explicitly. Throughput is capped: 200 KAG ingestion calls at 40/minute take at least 5 minutes, and longer if others are using the endpoint.
- The 100/minute limit is shared by everyone using the endpoint, so we cannot guarantee capacity; 429s can occur even below our own limit. Long jobs should be resumable and run off-peak.
- A static policy scan catches accidental drift, not a determined bypass.
- Verified means protocol/contract verified, not scientifically validated.

## Alternatives considered
- Provider abstraction layer with pluggable backends: rejected, since the requirement is a single protocol and one configured endpoint, and the abstraction invites the drift we want to prevent.
- Letting KAG use its default model or a different endpoint: rejected by the policy.
- Hard-coding api.openai.com: rejected after the owner clarified the protocol, not the vendor, is the requirement.
- Using OpenAI hosted vector stores/file search: deferred; keeps passage provenance under our control.

## Test plan
Mocked-transport tests stay the default and run in CI with no key. New: policy tests, KAG adapter tests against recorded responses, catalog/SVO contract tests, vector-store tests against a disposable pgvector container, benchmark comparison. Live checks (OpenSPG deployment, OpenAI smoke, DYNAMO) run only when explicitly invoked locally with credentials; results are recorded honestly in `docs/verification.md`.

## Documentation plan
Update the docs listed above. After M2, update the DSO-Architecture repo (service page, port reference, env vars) and commit there, with approval.

## Rollout/rollback plan
Local-only. Feature-flagged by existing `DSS_OPENAI_ENABLED`; `mode: kag` stays 503 until verified. Roll back by reverting commits and dropping the local pgvector volume. No external writes besides optional GitHub pushes and issue updates, each needing approval.

## Follow-up work (after M2, not in scope now)
- **`dso-mint` read-only MCP server** (approved 2026-11-06). Lives in `modflow-suite/mcp-suite/servers/`, not in this repo. Wraps the DYNAMO catalog API (`/models`, `/standardvariables`) for agents such as Claude Code and `ckan-agent-api`, reusing the contract verified in M2 (pagination, list-field normalization, SVO `sameAs`). Anonymous reads only; no model execution (that stays with the approved `mint-runner` workflow). Needs a DSO-Architecture docs update (repo map, port reference, MCP page) with approval. CKAN needs no new server: reuse `dso-ckan`.
- **Self-hosted tracing with Langfuse** (logged 2026-11-06 for later). Open source; adds prompt management, evaluations and per-user views, but self-hosting needs several services (database, column store, queue), so it is heavier than the alternative, Arize Phoenix (single container, OpenTelemetry). Relevant mainly to `ckan-agent-api`/DSO pods, possibly hosted on a Tapis pod. Not needed here: this project logs call metadata at the gateway instead. Re-evaluate when trace review or prompt/eval management is needed; verify current licence and deployment requirements first.

## Open questions
Answered 2026-11-06: Docker yes; policy scope is runtime only; variable vocabulary is the DYNAMO catalog `/standardvariables` (to verify stable IDs/versions); endpoint probe approved; call-count cap preferred over a dollar cap.

Probe result (read-only `GET /v1/models` on the TACC endpoint, 200): Llama-4-Maverick-17B-128E-Instruct, gpt-oss-20b, gpt-oss-120b, gemma-4-31B-it, MiniMax-M2.7, MiniMax-M3, Qwen3-32B, Meta-Llama-3.3-70B-Instruct, Mistral-Large-3-675B-Instruct-2512, DeepSeek-V3.2, Qwen3-235B-A22B-Instruct-2507, E5-Mistral-7B-Instruct. Only `/models` has been called; chat, embeddings and structured-output support are **not yet verified**.

Proposed defaults (to confirm after the capability probe):
- **Embeddings:** `E5-Mistral-7B-Instruct`, the only embedding model listed (4096 dimensions, within the adapter's existing bound). It expects an instruction prefix on queries; the adapter must add it.
- **Answer generation:** `gpt-oss-120b`, chosen for instruction following and structured output; fall back to `Qwen3-235B-A22B-Instruct-2507` or the current `Meta-Llama-3.3-70B-Instruct` if schema adherence fails the probe.
- **KAG extraction:** `Qwen3-235B-A22B-Instruct-2507` or `gpt-oss-120b`, whichever passes extraction checks on the synthetic corpus.
- Avoid reasoning-heavy models (DeepSeek, MiniMax, Qwen3-32B) for strict-JSON paths until tested.
- **Call-count caps:** the corpus is 5 passages (~1,050 characters). Proposed: keep the existing 60 attempts per app process; allow **200 calls per KAG ingestion run**, counted per HTTP attempt with no automatic retries. An embedding batch is one call. Raise only after a measured run.

Remaining:
0. Rate limit: answered, 100/minute total for the endpoint. Gateway default set to 40/minute; adjust after measuring real 429 frequency.
1. DYNAMO catalog API: the DSO docs list production as "not found in source". The dev Tapis Pods deployment documents `https://mintdevapi.pods.portals.tapis.io/v2.0.0` (catalog API) and `https://mintdevgraphql.pods.portals.tapis.io` (Hasura). Auth for reads and whether anonymous reads work are unverified. `DYNAMO_URL` in `.env` (`mintdevui...`) is the UI and should not be used as the API base.
2. Confirm the model defaults above after the probe.

## Decisions
- 2026-11-06: All runtime LLM/embedding calls use the OpenAI-compatible API protocol against one configured, allowlisted endpoint; enforced by a single egress path, generated KAG config and automated policy checks. Vendor-specific SDKs and a multi-provider abstraction rejected.
- 2026-11-06 (correction): the first draft read "OpenAI API" as OpenAI the company and fixed the URL to api.openai.com. The owner clarified it means the protocol, so the TACC Llama endpoint is valid. Revised the design accordingly.
- 2026-11-06: Endpoint has a reported 100 calls/minute limit. Add a shared localhost LLM gateway enforcing a sliding-window limit (default 40/minute) and call caps for all consumers including KAG; an in-app-only limiter rejected because KAG is a separate process.
- 2026-11-06 (implementation, step 0): `/chat/completions` is the default answer API because the TACC `/responses` ignores strict schemas while `gpt-oss-120b` on chat enforces them; `/responses` remains selectable. Model defaults settled: `gpt-oss-120b` (answers), `E5-Mistral-7B-Instruct` (embeddings, query instruction prefix).
- Deviations from the approved design: (a) on an upstream 429 the gateway pauses all callers and returns 429 to that caller; it does not wait and resend; (b) `/integrations` reports endpoint host and gateway use, not the last policy-check result (the check is CLI/test only, since an installed wheel has no source tree); (c) Compose cannot reach a host gateway yet (loopback-only allowlist), so Compose uses the endpoint directly; (d) policy check does not yet cover a rendered KAG config; that arrives with the KAG step.

- 2026-11-06 (scope): Verify the DYNAMO/SVO integration with a second domain, **groundwater and subsidence modeling**, because the dev catalog (692 standard variables, 294 with SVO `sameAs`; 23 models) has real content there and none for species distribution. Evidence: subsidence (`land_surface__subsidence`, `land_surface__displacement_rate`, 5 interbed compaction variables, all with SVO), groundwater (`groundwater__head`, `groundwater__drawdown`, hydraulic conductivity, storativity, pumping; most with SVO) and models MODFLOW 6 and MODFLOW 2005. The vector-borne SDM domain stays as the documented negative case: `domains/vector-borne-disease/crosswalk.json` records its gaps and keeps its two fixture variables as unreviewed candidates. Reason: a crosswalk cannot be verified against a catalog that lacks the concepts, and fabricating matches is not acceptable.
- Consequence: the domain loader must become domain-parametric (today it reads `domains/vector-borne-disease` directly), and a `domains/groundwater-subsidence/` domain (pathway, synthetic evidence, catalog fixtures, crosswalk) is added. Evidence stays synthetic and labelled so in M2; a licensed corpus remains M3.
- 2026-11-06 (implementation, DYNAMO/SVO): domains are discovered from `domains/*/domain.json` rather than listed in code. Catalog host allowlist (`mintdevapi.pods.portals.tapis.io`) is a deliberate hard-coded control; the URL itself comes from `DSS_CATALOG_URL`. Evidence/source IDs are globally unique across domains (`ev-gw-*`). Deviation: no `catalog-sync` snapshot command; `catalog-verify` checks the crosswalk against the live catalog directly. Crosswalk entries remain unreviewed; the human review step is not automated and not done.

- 2026-11-07 (completion): all four M2 issues have an implementation verified locally on synthetic data. **KAG** (#1): local OpenSPG v0.8 stack, ingest, a cited query, and the `mode: kag` adapter with strict citation resolution (set-level verified; per-sentence tags not). **DYNAMO** (#2) and **SVO** (#3): read contract verified against the dev catalog and nine crosswalk candidates prepared, but **no entry is accepted**, so alignment stays unverified until a person reviews them (`docs/crosswalk-review.md`). **pgvector** (#4): persistent index verified equal to the in-memory backend within float32 rounding. Deviations from this spec: no `catalog-sync` snapshot command; no KAG entry in the backend comparison (25 to 50 paid calls per question); the OpenAI-only wording became "OpenAI-compatible endpoint, allowlisted" (see the 2026-11-06 correction); the per-sentence citation requirement was narrowed to the retrieved set after KAG's tag mapping proved opaque.
- Follow-ups not done: crosswalk review by a person; the Chinese-language KAG answers; a larger evaluation corpus and real (licensed) evidence (M3); the `dso-mint` MCP wrapper and tracing evaluation (backlog); a push of the DSO-Architecture docs, which holds unrelated unpushed work.

## User feedback / decisions
- "Make sure that any LLM uses the OpenAI API." Clarified: "Its not OpenAI, its the OpenAI API, those work", i.e. the protocol, and the TACC endpoint is acceptable. (2026-11-06)
