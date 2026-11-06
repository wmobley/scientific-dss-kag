# OpenAI setup and verification

> **Policy (M2):** "OpenAI API" here means the OpenAI-compatible protocol. All runtime LLM and embedding calls go through `OpenAIProvider` (or the LLM gateway) to one configured endpoint whose host is allowlisted in `settings.py` (`api.openai.com`, `ai.tejas.tacc.utexas.edu`). `scientific-dss policy-check` and `tests/test_llm_policy.py` fail on other provider SDKs, unaudited network clients, other providers' env vars or an unlisted endpoint host, and warn when `LANGSMITH_TRACING=true`.

## Endpoints, models and the gateway

- `OPENAI_BASE_URL` selects the endpoint (default `https://api.openai.com/v1`; a bare host gets `/v1`). `OPENAI_RESPONSE_API=chat|responses` selects the answer API; **`chat` is the default** because it is the portable one.
- Verified on 2026-11-06 against the TACC endpoint: `E5-Mistral-7B-Instruct` embeddings (4096 dimensions) and `gpt-oss-120b` on `/chat/completions` with strict `json_schema` (the schema is enforced: a contradicting prompt still returned the enum value). On that endpoint `/responses` accepted the request but **did not enforce** the schema, and `Qwen3-235B-A22B-Instruct-2507` did not reliably follow it, so use `gpt-oss-120b` with `chat`. E5-Mistral queries get its instruction prefix automatically; passages are embedded raw.
- The TACC endpoint reportedly allows 100 calls/minute in total across all users. Run the gateway so one limiter covers every consumer: `scientific-dss gateway` (binds 127.0.0.1:8092). It holds `OPENAI_API_KEY`, queues callers to `DSS_LLM_RATE_PER_MINUTE` (default 40), applies an optional `DSS_LLM_MAX_CALLS` cap, pauses on upstream 429 and never resends. Point the app at it with `DSS_GATEWAY_URL=http://127.0.0.1:8092/v1` and a `DSS_GATEWAY_TOKEN` of 16+ characters (the gateway needs the same token). The Compose API service does not yet reach a host gateway; Compose uses the endpoint directly with the in-process 60-attempt budget.

The server supports opt-in OpenAI semantic embeddings and structured, cited answers. There are no API calls at startup, in default tests or in the shared offline benchmark. **Live OpenAI verification is pending a locally configured key.** Mocked contract tests do not prove access to a model or billing account.

## Configure locally

In your local checkout (never GitHub's file editor), copy `.env.example` to `.env` if that file does not already exist. Preserve any existing settings. Add your API key as `OPENAI_API_KEY` and set `DSS_OPENAI_ENABLED=true`. `.env` is ignored by Git and excluded from the Docker build context. Do not paste the key into chat, browser fields, issues or documentation.

The application reads `.env` from its current working directory using python-dotenv, without executing shell code. Existing environment variables take precedence. Compose passes only the four named OpenAI settings into the server. To apply changes, restart the Python server or recreate the Compose API container:

```bash
# Run from repository root, with the Python environment active:
uvicorn scientific_dss_kag.api:app --host 127.0.0.1 --port 8091 --workers 1
# Or:
docker compose up --build --wait
```

Keep one worker and the localhost binding. This is a local demo, not an authenticated production gateway. `/integrations` reports enabled/configured state and model names without the key. `live_verified` becomes true in that server process only after valid embedding and response operations succeed; a separate CLI smoke process does not change the running server's status. “Verified” here means the API contract succeeded, not that an answer is scientifically correct.

## Explicit paid actions

The workbench vector selector defaults to offline teaching vectors. Selecting OpenAI semantic embeddings and clicking Compare triggers real embedding requests for hybrid and ontology modes; lexical stays offline. On the first OpenAI retrieval, reviewed corpus passages are embedded once, then the question is embedded. Subsequent requests reuse in-memory corpus vectors but embed each question again.

Generate cited answer with OpenAI always calls OpenAI for generation if eligible evidence exists, including when the retrieval selector is offline. It uses ontology-filtered evidence for the chosen decision context. Empty retrieval returns an abstention locally without a generation call. A provider failure is displayed explicitly; no offline answer is fabricated.

Example API request (after configuring the server):

```bash
curl -s http://127.0.0.1:8091/answer -H 'Content-Type: application/json' \
  -d '{"query":"What affects MaxEnt habitat suitability interpretation?","mode":"ontology","context":["ScientificMethod"],"backend":"openai","k":2}'
```

The `backend` field chooses retrieval vectors; generation always uses OpenAI. `mode: kag` remains unavailable. Browser paid requests require the same local origin. Command-line JSON requests may omit Origin, but must use a localhost Host. Arbitrary URLs, keys, prompts, models and tool definitions are not accepted in request bodies.

## Models, data and limits

Defaults: `OPENAI_EMBEDDING_MODEL=text-embedding-3-small` and `OPENAI_RESPONSE_MODEL=gpt-4.1-mini`. Change these only on the server and confirm the chosen model supports the required API and strict structured output. The provider URL is fixed to `https://api.openai.com/v1/`, TLS verification stays enabled, environment proxies are ignored and redirects are not followed.

OpenAI receives selected reviewed passage text, the question and answer instructions; embedding calls receive reviewed corpus passages and the question. The source fixture is synthetic. Before using real literature or sensitive data, establish appropriate licensing and sharing authority. Responses use `store=false`, which does **not** promise zero retention or replace applicable OpenAI data policies.

Hard local bounds: 2000-character questions; k up to 20; generation passage context up to 24000 characters; at most 100 corpus passages, each <=4000 characters and total <=100000 characters. Oversized inputs are rejected. Generation is capped at 1200 output tokens. The server permits one logical OpenAI operation at a time and at most 60 outbound HTTP attempts per process; failed attempts count and there are no automatic retries. One answer can use three attempts on a cold embedding cache (corpus, query, response), or one attempt with offline retrieval. A comparison can use multiple query embeddings. These are request/size limits, **not a monetary cap**; set account-side spending controls as appropriate.

The corpus cache holds at most two validated batches keyed by model, corpus hash and ordered reviewed evidence IDs/passages. It is not persisted. Restarting resets both cache and budget; additional workers multiply budgets. Usage metadata records token counts reported by OpenAI, with embedding usage attached to retrieval and generation usage attached to the answer. Failed requests can still incur charges without reported usage.

## What citation checks establish

Structured answers contain answered/abstained status, up to five brief claims, evidence IDs, gaps and uncertainties. Every claim must cite at least one passage actually included in the generation context. The server resolves those IDs to source metadata, exact offsets and checksums. Unknown IDs, empty claims with answered status, malformed JSON, refusals and incomplete responses fail explicitly. Sources/questions are treated as untrusted prompt data and no tools or model execution are enabled.

This checks reference membership and formatting. It cannot prove entailment, truth, scientific suitability or calibrated uncertainty. All results remain `scientifically_validated: false`; assess them using the student review rubric. Habitat suitability is not disease incidence.

## Live smoke test

Only after configuring the local key and flag, explicitly run:

```bash
scientific-dss openai-smoke
```

This sends the bundled synthetic MaxEnt teaching material and one fixed question to OpenAI; it can incur charges. It runs real embeddings, hybrid retrieval and one structured answer, printing redacted model/corpus/response/usage metadata and cited claims. Never include `.env` or a raw provider error in shared logs. Record the result before claiming live integration works. This smoke test is not part of CI or the default benchmark.

Official references: [Embeddings](https://developers.openai.com/api/docs/guides/embeddings), [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini).
