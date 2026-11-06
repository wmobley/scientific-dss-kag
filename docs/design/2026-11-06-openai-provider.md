# OpenAI embeddings and evidence-grounded responses

## Status
Implementing

## Objective
Add opt-in OpenAI API support to the scientific DSS: real embedding-based hybrid retrieval and structured, evidence-cited answers in the student workbench.

## User need
The user wants to continue the runnable project using OpenAI APIs rather than stop at deterministic teaching baselines. Students need to inspect sources, abstention and provider metadata without seeing API credentials.

## Current code/system summary
Version 0.1.0 has 65 passing tests and public GitHub CI. Retriever supports lexical, hashed-character-vector hybrid and ontology-filtered hybrid modes. API/UI use synthetic SDM evidence with exact provenance, no generation. KAG remains unavailable. Catalog/SVO remain fixtures. No .wolf memory exists in this new repository. DSO docs inspected previously establish no live deployment. OPENAI_API_KEY is absent from the agent process and project .env does not yet exist; user says they will add .env in the repository. Clarified that this means the ignored local checkout, never the public remote.

## Proposed design
Implement a small synchronous OpenAI REST adapter over the existing pinned httpx dependency using fixed https://api.openai.com/v1 endpoint. Use POST embeddings with text-embedding-3-small, and POST responses with configurable gpt-4.1-mini default, strict JSON schema and store=false. Defaults verified against official OpenAI docs; no model access or live success claimed. API keys only read from process environment (Compose injects from local .env; direct Python uses explicit env loading at startup). No arbitrary base URL, model, key or custom prompt parameters accepted from clients.

Retain offline default and benchmark reproducibility. Add retrieval request backend offline/openai default offline; lexical OpenAI backend is rejected. OpenAI corpus vectors are computed on first explicit OpenAI retrieval for reviewed passages only, cached in bounded process memory by corpus hash+embedding model; queries embedded per explicit request. Cache is never persisted or primed at startup; rebuilding after restart costs embeddings. Fuse lexical and provider vectors with existing RRF; retain explicit ontology context. New /answer accepts existing query/context/k/mode/backend bounded fields and generates a structured response from eligible retrieved evidence only. Empty retrieval returns local abstention with no paid generation. No automatic retry or background requests.

Structured output: status answered/abstained, bounded claims each with text and nonempty evidence IDs, gaps and uncertainties. Reject citations outside actual retrieval; answered requires claims, abstained must have none. Return application-resolved citations with source hash/span. These checks prove reference integrity only, not entailment or scientific truth; output is explicitly not scientifically validated. Prompt treats question and source text as untrusted data, forbids embedded instructions/tool use/execution, asks abstention for insufficient evidence and avoids treating habitat suitability as disease incidence.

Settings: DSS_OPENAI_ENABLED=false, OPENAI_API_KEY, OPENAI_RESPONSE_MODEL=gpt-4.1-mini, OPENAI_EMBEDDING_MODEL=text-embedding-3-small. Fixed output limit 1200 tokens; input query <=2000 chars, up to 20 retrieved passages with total context <=24000 chars. Embedding corpus <=100 reviewed passages of <=4000 chars with total <=100000 chars; explicit fail if larger. One in-flight OpenAI operation and a process-local 60-request operation budget; fail after budget rather than unbounded paid requests. Budget counts attempts before HTTP and no refunds/retries; restart resets budget. Record tokens/usage per operation, model/response ID and corpus hash; no raw credential/error text. Localhost binding and strict same-origin checks on paid routes; no production/multiuser security claimed.

Workbench has explicit backend selector and a separate Generate cited answer button. The existing offline shared benchmark remains offline. Display model, claims/citations, abstention and limitations with textContent. Disable paid buttons if provider is not configured. /integrations reports enabled/configured and process-local live verification state only after successful calls, without credentials. Add an explicit CLI OpenAI smoke command using synthetic corpus that emits redacted structured verification metadata; never part of default tests/CI.

## Files likely affected
src/scientific_dss_kag/{openai_provider,settings}.py (new); retrieval.py; models.py; api.py; connectors.py; cli.py; static/{index.html,workbench.js}; tests/test_openai.py and tests/test_api.py; .env.example; compose.yaml; docs/{setup,integrations,architecture,verification,student-guide}.md; README.md; this spec. .gitignore retains .env exclusion. No canonical ontology schema changes.

## API/schema changes
RetrievalRequest adds backend enum offline/openai. New POST /answer uses same retrieval options and strict bounded answer response. /integrations adds OpenAI configuration/verification metadata. Offline response metadata accurately distinguishes hashed vectors vs OpenAI model. Existing defaults and fixture catalog APIs unchanged.

## Data flow
Explicit request -> validate origin/work bounds/configuration -> retrieve reviewed evidence (optional OpenAI embeddings) -> constrained evidence JSON + question sent to Responses -> reject incomplete/refusal/malformed/unknown citations -> return claims with source-resolved citations and usage. API key goes only server-to-api.openai.com over TLS. Synthetic evidence/questions cross that boundary only for explicit OpenAI operations; no external service writes or model execution. In-memory vectors and operation budget reset on restart.

## Risks and tradeoffs
Paid API usage requires user credentials and billing; local request budget is not a monetary hard cap. Prompt injection defenses/structured outputs cannot establish factual faithfulness. Any future real corpus needs appropriate data-sharing authorization. Store=false is not a zero-data-retention guarantee. Network failures, refusal and incomplete outputs must fail explicitly without fabricated fallback. Server-only key plus same-origin guards and localhost help local demo safety but do not provide production auth. A character-hash baseline and semantic vectors have different behavior; metadata must identify them. Persistent pgvector and live KAG remain outside this increment.

## Alternatives considered
SDK adds a new dependency; existing documented REST API via pinned httpx is sufficient and easy to contract-test. Browser-side key rejected because public UI must never receive credentials. Replacing all baselines rejected to preserve reproducibility. Hosted file search/vector stores deferred to keep scientific evidence and passage provenance under application control. Automatic extraction deferred until reviewed promotion workflow exists.

## Test plan
Use httpx.MockTransport; inspect actual serialized POST URLs/bodies/auth without real credentials or paid calls. Embedding tests reordered indices, dimension/length/nonfinite/zero vector failures, model/corpus cache separation and reuse, candidate exclusion. Generation tests valid citations, invented IDs, empty/malformed claims, abstention, refusal, truncation, HTTP/timeouts and key redaction. API tests disabled/missing key 503, invalid backend/oversized context, cross-origin rejection, budget/concurrency, offline regression and no startup calls. Verify workbench controls and unavailable state. Run full suite/build/Compose config; if key configured, run one explicit bounded synthetic live smoke test and report actual results. Otherwise distinguish tested adapter contracts from unverified live provider.

## Documentation plan
Explain ignored local .env, server-only injection for Python/Compose, models/output limits, exact data sent, paid actions, restart cache behavior, opt-in test command, citation limitations and statuses. Keep KAG/DYNAMO/SVO verification unchanged. Record hosted verification and exact tests.

## Rollout/rollback plan
Build/test locally first, then rebuild existing local demo with OpenAI disabled until user configures local key and enable flag. User continue instruction extends original public repository publishing scope. Push only code/config examples/docs without secrets after QA. Roll back by DSS_OPENAI_ENABLED=false or earlier commit; no persisted graph or database mutation. Do not commit .env or credentials. DSO architecture registration remains tracked separately with deployment unassigned.

## Open questions
Credential availability and permitted model access. No key has been requested in chat. Live smoke remains conditional on local configuration. Broader scientific benchmark and real corpus licensing are future work.

## Decisions
### 2026-11-06 - OpenAI implementation authorized
- Decision: proceed with opt-in server-side embeddings and structured evidence-grounded Responses.
- Reason: user says keep going and use OpenAI APIs, continuing original build/publish instruction.
- Alternatives rejected: browser-side credentials, silent provider fallback, automatic startup/API spend.
- User feedback: user will place .env in repository; clarified local ignored checkout only.
- Impact: prepare reviewed design, implement adapter and mocked tests, verify live only with configured credentials.

## User feedback / decisions
"ok keep going then. We need to use openai api s"; "i will add it a a .env in the github repo". No model selection, API key access or live success inferred.

### 2026-11-06 - Review clarifications
- Decision: proceed after document, architecture and security review under explicit continue instruction.
- Reason: no unresolved blocker with concrete boundaries. Budget unit is each outbound HTTP attempt (corpus embeddings, query embedding, response); entire logical paid operation holds one lock. Claims <=5, text <=1200 chars, citation IDs <=20 per claim; gaps/uncertainties <=10 each of <=500 chars. Oversized generation context is rejected, never silently truncated.
- Alternatives rejected: SDK-only output_text on raw REST, permissive citation parsing, cache publication before validation, Origin checks trusting arbitrary Host.
- User feedback: user is configuring local .env; no key value accessed or sent yet.
- Impact: /answer backend selects retrieval only; generation is always OpenAI. Host allowlist with exact Origin and cross-site rejection; CLI missing Origin only with local Host. httpx trust_env=false, redirects off, fixed official TLS endpoint. Cache includes ordered reviewed IDs/passages+corpus/model and is atomically replaced after validation. Use one worker; process budgets multiply with workers. Local .env loading uses python-dotenv rather than shell evaluation.
