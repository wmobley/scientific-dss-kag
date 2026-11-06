# Architecture

The core ontology is independent of the retrieval engine. Stable prototype IRIs use `https://example.org/scientific-dss/decision-pathways#`; replace this example namespace through an explicit versioned migration before publishing a durable ontology. These IRIs are identifiers, not fetch endpoints.

The bundled corpus has three logical concerns: immutable source records, evidence assertions with review status, and decision-specific pathways. Source hashes and exact passage offsets are checked before ranking. Candidate assertions never become eligible merely because a question retrieves related text. In this release pathways are request-scoped and are not stored.

## Retrieval

Token overlap is the lexical baseline. Local vectors hash normalized character trigrams into 256 signed dimensions using SHA-256; cosine similarity ranks them. Reciprocal rank fusion combines positive-score lexical and vector rankings with constant 60. Ontology mode filters reviewed evidence by intersection with caller-supplied core class names, then ranks it. It is a schema-tag filter, not a traversable knowledge graph or KAG reasoning engine.

API routes: GET `/health`, `/integrations`, `/catalog/models`, `/catalog/variables`; POST `/retrieve`, `/answer`, `/validate/pathway`, `/evaluate`. The same-origin workbench is at `/`. FastAPI serves interactive API documentation at `/docs` with a route-specific nonce and Swagger CDN permission. Offline browsers can use `/openapi.json`; the workbench has no CDN dependency. Requests have typed bounded fields and forbidden extras. The local demo has no authentication or persistence.

## Validation layers

Pydantic validates API and evidence record types. Application provenance checks ensure hashes, exact spans and known concepts. SHACL validates canonical RDF required properties, datatypes, status and offsets; it does not prove an assertion true or match hashes against external documents. Pathway completeness reports missing fields and unknown/unreviewed evidence IDs, separately from scientific validation (always false in this release).

## Integration boundaries

`CatalogClient` accepts an operator-configured HTTPS base URL and supports GET of `models` and `standardvariables`, a bounded first page only. It does not execute or register models. Endpoint shapes were checked against local catalog OpenAPI and are tested using HTTP mocks; no live service compatibility has been established. The fixture variable alignment is not an SVO lookup implementation. Draft SPG schema/mapping preserves selected directed relations and explicitly loses OWL/SHACL semantics. Provenance literals remain outside its initial projection.

The optional Compose pgvector service is infrastructure scaffolding only. A production version needs persistent ingestion, semantic embeddings, authentication, isolated projects, provenance-preserving graph indexing and independently evaluated scientific applicability.

## OpenAI provider

The opt-in provider uses fixed official HTTPS REST endpoints through httpx, with no retries, no redirects and no environment proxy configuration. Server settings load the ignored local .env with process environment precedence; no credentials are accepted from or returned to the browser. Requests choose offline/openai retrieval backend; generation through /answer always uses OpenAI. Offline defaults and benchmark remain deterministic. The local-only origin guard and one-operation lock wrap paid requests. A process-local quota counts every outbound HTTP attempt; it is not a dollar cap.

Reviewed corpus vectors are atomically cached only after full index/count/dimension/finite-value validation; query vectors are checked against corpus dimensions. Raw Responses message/output_text JSON is validated against bounded models and actual retrieved evidence IDs. Refusal, truncation and invalid citations fail explicitly. Sources are untrusted prompt data, and no tools are available. Reference integrity is distinct from entailment/truth. Full configuration and data-sharing details: openai.md.
