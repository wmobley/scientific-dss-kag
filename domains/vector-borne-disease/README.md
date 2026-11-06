# Vector-borne disease SDM teaching case

Question: which evidence and modeling prerequisites are needed to support mosquito surveillance allocation using habitat suitability?

`corpus.json` contains five synthetic source notes and exact-span evidence: sampling/validation, presence-background assumptions, predictor readiness, decision formulation, and one deliberately unsupported candidate. These are not literature findings. `catalog.json` is a fabricated MaxEnt discovery record plus temperature/precipitation variable placeholders. SVO IDs remain null. No model is installed or run.

`pathway.json` demonstrates objectives, information needs, alternatives, uncertainty and eligible evidence IDs. Post it to `/validate/pathway`. A complete pathway still requires expert scientific assessment and geographically/temporally appropriate data.

Reuse in a new domain by creating a separate domain directory with the same record schema and reviewed corpus, then explicitly wiring the selected domain into application configuration. Runtime domain selection is not yet implemented; the default retriever uses this SDM fixture only.
