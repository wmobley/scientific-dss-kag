# Integration status and verification

## OpenSPG / KAG

Status: **draft mapping; live schema import and queries unverified**. `/retrieve` with `mode: kag` fails explicitly with 503. The offline ontology mode is not KAG.

The [upstream KAG README](https://github.com/OpenSPG/KAG) documents deployment using [OpenSPG's Compose configuration](https://github.com/OpenSPG/openspg/blob/master/dev/release/docker-compose-west.yml), then toolkit installation in a separate environment. This repository does not vendor or automatically launch that large stack. Review the upstream configuration, bind exposed services to localhost, change default credentials and record exact Git commits/image digests before running it. The inspected upstream README described KAG 0.8.0, but no compatibility with that or a later release is asserted.

The draft schema syntax follows [the upstream Medicine example](https://github.com/OpenSPG/KAG/blob/master/kag/examples/medicine/schema/Medicine.schema). The [upstream example guide](https://github.com/OpenSPG/KAG/blob/master/kag/examples/README.md) describes project initialization and schema commits. Create a development project using that guide, copy `ontology/mappings/openspg/decision-pathways.schema` into its schema directory, and run its documented `knext schema commit` workflow against an explicitly selected local project. Project creation/configuration is version-specific; do not paste a guessed project ID.

Before marking live KAG verified: record server/toolkit commits and model configurations; commit the draft schema successfully; verify class/relation lookup; ingest a synthetic passage preserving canonical ID, source hash and offsets; query it through KAG and confirm citations; test unavailable server and malformed result behavior; attach logs with credentials removed. KAG adapter implementation remains a tracked issue. Full OWL semantics are not preserved by the mapping.

## DYNAMO Model Catalog

Status: **fixture adapter and mocked read-only catalog HTTP client; no live verification**. Authoritative local DSO documentation `services/mint-platform.md` describes the migrated TypeScript/Fastify catalog over Hasura/PostgreSQL. The corresponding `model-catalog-api/openapi.yaml` supports GET `/models` and `/standardvariables`, with `label`, `page`, `per_page`. Production API URL is not documented. The MINT UI URL must not be assumed to be a catalog API.

Operator-only Python example, after confirming deployment contract and obtaining authorized credentials:

```python
from scientific_dss_kag.connectors import CatalogClient
client = CatalogClient("https://YOUR-VERIFIED-CATALOG-BASE")
try:
    records = client.list_resources("models", label="MaxEnt")
finally:
    client.close()
```

No default URL, automatic remote probe or credential reading exists. The bounded first-page result is not a complete catalog synchronization. Before enabling a live adapter, verify auth, schema/version, pagination, standard-variable relationships, catalog-to-ontology identifiers, provenance, timeouts and failure modes. A successful HTTP response is insufficient to validate scientific applicability.

## SVO

Status: **synthetic alignment fixtures only**. Fixture `svo_uri` values are null; no ontology identity is fabricated. DSO's `svo-adapter-service` translates semantic variables into workflow inputs. Its documented GET `/transform-specs` is not a general ontology search endpoint. Do not substitute workflow translation for SVO vocabulary resolution. Confirm a vocabulary source/version, align variables with units and context, record mapping confidence and human review, then add a real client and contract tests. Workflow planning/execution is outside this scaffold.

## PostgreSQL / pgvector

Status: **optional Compose scaffold; unused by retrieval**. Provisioning a database does not establish working hybrid RAG. Future work must add migrations, source/evidence indexing, real embedding version records, transactional validation and comparison against the same evaluation corpus.

## OpenAI

Status: **implemented REST adapter, mocked contracts verified; live calls unverified until local credentials are configured**. Supports real embeddings, reciprocal-rank hybrid retrieval and Responses strict structured answers with citation membership checks. Optional and disabled by default; no startup or CI calls. See openai.md for local setup, explicit paid actions, usage metadata, quota/cache semantics, data sharing and the opt-in live smoke command. This does not change KAG/DYNAMO/SVO status or establish scientific answer validity.
