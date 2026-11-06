# Groundwater pumping and land subsidence teaching case

Question: which evidence and modeling prerequisites are needed to evaluate pumping scenarios against land subsidence using a MODFLOW-type model?

This domain exists because the DYNAMO dev catalog contains real MODFLOW 6 / MODFLOW 2005 models and subsidence, compaction and groundwater variables, so the catalog and SVO integration can be verified here (the species-distribution domain has no catalog counterparts).

- `corpus.json`: five **synthetic** teaching notes with exact-span evidence (one deliberately unsupported candidate). Not literature findings. IDs are prefixed `gw-`/`ev-gw-` so they stay unique across domains.
- `catalog.json`: fixture model and variable records (`origin: synthetic_fixture`).
- `crosswalk.json`: candidate links to real catalog records (IDs and SVO URIs copied from the live dev catalog on 2026-11-06). All entries are `unreviewed`; a human must accept an entry before it counts as aligned.
- `pathway.json`, `domain.json`: example decision pathway and manifest.

Verify against the live catalog: `DSS_CATALOG_URL=https://mintdevapi.pods.portals.tapis.io/v2.0.0 scientific-dss catalog-verify --domain groundwater-subsidence`. Select the domain for the server with `DSS_DOMAIN=groundwater-subsidence`. No model is installed or run.
