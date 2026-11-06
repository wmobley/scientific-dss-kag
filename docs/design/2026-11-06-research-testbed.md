# Scientific DSS KAG research testbed

## Status
Implemented

## Objective
Scaffold a runnable, tested, reusable Decision Pathways Ontology guided scientific decision support research repository. First domain: vector-borne disease species distribution modeling (SDM).

## User need
Students need a transparent testbed comparing conventional retrieval, hybrid retrieval, and ontology-guided evidence selection, with traceable sources and model/variable discovery boundaries.

## Current code/system summary
The workspace contains no existing application or .wolf context. Recovered prior chat proposes portable ontology plus OpenSPG/KAG mappings, DYNAMO/SVO discovery, validation and evaluation. DSO docs found at /Users/wmobley/Documents/Github/DSO-Architecture/docs; configured /Volumes path is unavailable. GitHub connector authenticates wmobley, exposes no organizations and no existing matching repository. Local gh authentication reports invalid credentials. Repository destination/visibility are pending user clarification.

## Proposed design
Create a Python package with FastAPI and a small same-origin HTML student workbench. Default mode runs fully offline with explicitly synthetic SDM teaching fixtures. Return retrieved evidence and pathway gaps rather than fabricated LLM answers. Implement lexical baseline, deterministic local vector similarity plus reciprocal rank fusion, and ontology-constrained hybrid selection as distinct research modes. State that local vectors are a teaching baseline, not pretrained semantic embeddings or OpenSPG reasoning.

Canonical ontology: RDF/OWL Turtle with 15 decision/science classes and explicit properties; SHACL checks evidence provenance and pathway required fields. Separate source records, candidate literature assertions and project decisions; no automatic promotion of extracted assertions. Validate source hash and exact evidence span before retrieval. Read-only DYNAMO/SVO connector interfaces with fixture adapters and explicit live-unverified status. Initial SPG schema/mapping and upstream setup instructions; no claim that importing OWL preserves reasoning. KAG is optional and must fail explicitly when unavailable rather than silently falling back.

API: health, integration status, fixture catalog/variables, retrieval, pathway validation and benchmark evaluation. Inputs bounded, mode enumerations enforced, no arbitrary URL fetch, no execution or remote writes. Workbench compares modes and displays source IDs, scores and evaluation results. Run results exported by CLI as JSON. Compose runs API bound to localhost; optional postgres/pgvector service as future integration scaffold, clearly unused by default. OpenSPG managed separately using verified upstream deployment instructions, not an invented all-in-one image.

## Files likely affected
pyproject.toml; src/scientific_dss_kag/{api,models,retrieval,validation,connectors,evaluation,cli}.py; src/scientific_dss_kag/static/index.html; ontology/decision-pathways.ttl; ontology/shapes.ttl; ontology/mappings/openspg/*; domains/vector-borne-disease/*; experiments/benchmarks/*; tests/*; Dockerfile; compose.yaml; .env.example; .github/workflows/tests.yml; docs/{setup,architecture,integrations,student-guide,roadmap}.md; planning/issues.json and milestones.json; scripts/publish_github.py.

## API/schema changes
New /health, /integrations, /catalog/models, /catalog/variables, /retrieve, /validate/pathway, /evaluate routes. Typed request/response models; evidence has source ID, source text hash, exact passage, offsets and review status. Pathway has objective, information needs, alternatives and uncertainty; completeness is distinct from scientific validity. Benchmark cases contain expected evidence IDs and fixed split; metrics recall@k and reciprocal rank only. No claims of answer faithfulness without generated answers and human adjudication.

## Data flow
Bundled synthetic source text -> immutable source record and checksum -> validated passage/ontology tags -> lexical and local vector ranking -> reciprocal rank fusion -> optional ontology filter -> cited evidence response. Separate fixture catalog/variables are displayed with synthetic origin. Benchmark questions use same fixed corpus and mode settings. No model execution or disease risk inference.

## Risks and tradeoffs
Tiny synthetic benchmarks establish mechanics only, not scientific effectiveness. Local vectors are weaker than learned embeddings. KAG deployment may require substantial resources and compatible external model credentials. DYNAMO/SVO endpoints and credentials must be validated before enabling live adapters. App is a local research demo without authentication, multiuser persistence or production deployment. OWL-to-SPG mapping loses semantics and requires live schema-commit checks. Pin dependencies and test reproducibility; package fixtures so installed distributions work outside repository root.

## Alternatives considered
Full live infrastructure from first commit rejected because credentials and runtime availability are unknown. Pure pseudocode rejected because user needs runnable tests. Making OpenSPG canonical ontology owner rejected to preserve portability. Production LLM agent and SDM execution deferred to subsequent milestones.

## Test plan
Run pytest: all API modes and bounds; invalid modes; no evidence and empty query; deterministic rankings; provenance tampering/invalid offsets; SHACL positive and negative fixtures; ontology/schema mapping coverage; connector fixture parsing and explicit unavailable live status; benchmark metrics including empty cases; installed package resource access. Run CLI benchmark and API smoke check. Validate Compose if Docker available, distinguish config validation from actual startup. Verify OpenSPG schema using real CLI/server only if runtime available; otherwise report unverified.

## Documentation plan
README quickstart and limitations, setup/Compose, architecture, live integration verification checklist with statuses, student reproducibility guide, benchmark methodology and roadmap/issues/milestones. Include sources and upstream version references. Prepare DSO architecture registration updates without inventing deployment targets; do not mutate external docs repo without permission to its write path.

## Rollout/rollback plan
Deliver locally under outputs/scientific-dss-kag. Publish only after owner and visibility resolved. Start new empty repository without overwriting any existing one. User explicitly requested creation/push and issues/milestones; authorization limited to chosen destination. Add each created issue immediately to wmobley Research Dashboard project 5. If GitHub credentials or project access prevent this, keep local artifacts and report exact pending work. Rollback local run by stopping API/Compose; no automatic deletion of repository or data.

## Open questions
GitHub owner and visibility. Live catalog/SVO auth details if not discoverable in DSO docs. OpenSPG runtime availability.

## Decisions
### 2026-11-06 - Start implementation authorized
- Decision: bounded runnable offline research scaffold with explicit live integration boundaries.
- Reason: user explicitly requests starting project now and forbids unsupported integration claims.
- Alternatives rejected: simulated claims of working live integrations.
- User feedback: current request authorizes building, testing and eventual publishing after destination resolution; no separate design approval claimed.
- Impact on implementation: use proceed exception in design-spec workflow; complete review before editing application code.

## User feedback / decisions
Current task request supplies scope and explicit proceed instruction. Publishing destination clarification is pending.

### 2026-11-06 - Specialist review and implementation approach
- Decision: proceed under user's explicit start-building instruction after document, architecture and security review.
- Reason: reviews found no blocker for bounded local scaffold. KAG mode returns 503 until verified; ontology context is explicit, never benchmark gold labels. Benchmark outputs record corpus checksum, ontology version, vector method, k and cases, with hand-calculated metric tests.
- Alternatives rejected: silent KAG fallback, arbitrary URL ingestion and automatic assertion promotion.
- User feedback: owner/visibility still pending; no external destination inferred.
- Impact: same-origin UI with textContent and CSP, localhost Compose, bounded workloads, no remote RDF imports. Catalog /models and /standardvariables contracts inspected locally; SVO workflow adapter is a different service. GitHub auth works with network access enabled; CLI reveals IS-GEO, mintproject and In-For-Disaster-Analytics memberships unlike connector's empty list.

### 2026-11-06 - Public destination and QA fixes
- Decision: publish to public wmobley/scientific-dss-kag.
- Reason: user explicitly selected this destination/visibility and then instructed continue.
- Alternatives rejected: inferring an organization from membership alone.
- User feedback: "wmobley/scientific-dss-kag — public".
- Impact: create a new public repository only after checks, then push initial scaffold; publish milestones/issues with immediate Dashboard addition.

### 2026-11-06 - Implementation verification and deviations
- Decision: complete bounded scaffold with 65 passing tests and successful local Docker/workbench checks.
- Reason: independent QA exposed and regression-tested request-size, docs CSP, Compose optional-secret and rank-accounting edge cases.
- Alternatives rejected: Content-Length-only limit; relaxed application-wide CSP; optional database credentials in base Compose.
- User feedback: continue instruction applies; no live integration success inferred.
- Impact: optional database moved to compose.vector.yaml; Swagger uses route-specific nonce/CDN policy; actual streamed bytes capped; metric ranks retained. DSO registration stays a concrete proposal/tracked follow-up because its separate checkout has existing unrelated edits and cluster/port assignment is unconfirmed. Live KAG/DYNAMO/SVO and scientific validation remain unverified as designed. No LLM generation/extraction or model execution in this first scaffold.

### 2026-11-06 - Publication verified
- Decision: initial scaffold published to https://github.com/wmobley/scientific-dss-kag, public main branch.
- Reason: user-selected destination, implementation/test/QA complete.
- Alternatives rejected: publishing into an unrelated organization/repository.
- User feedback: explicit public destination selection; original request authorizes creation/push/issues/milestones.
- Impact: initial commit bd0e96b; hosted Python 3.12/3.13 CI successful; three milestones and nine issues created with immediate Research Dashboard additions. No external scientific service was mutated or model executed.
