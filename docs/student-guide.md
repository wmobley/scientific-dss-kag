# Student evaluation guide

Start with README setup. Open the workbench and compare lexical, hybrid and ontology-filtered evidence for the same question. Record question, selected context, k, retrieved IDs and ranking. Change the context deliberately and inspect which evidence disappears. An incorrect context can exclude useful evidence.

Inspect every source passage and its hash/offset metadata. The fixture corpus is authored synthetic teaching text, not an ingested literature collection or a scientific gold standard. “Reviewed” only permits inclusion in this fixture experiment. The unsupported candidate illustrates why extraction and promotion must be separate.

## Reproduce a run

Run `scientific-dss benchmark --k 3 > benchmark.json` twice. Outputs should match exactly: corpus and benchmark hashes, method/version, k, questions, context, rankings and metrics. Recall@k is retrieved relevant evidence divided by all judged relevant evidence. Reciprocal rank is one divided by the first relevant rank, or zero. These retrieval metrics do not measure generated-answer faithfulness.

The workbench lets you formulate a pathway, check structural gaps and export the shared benchmark. It does not persist student projects or human ratings. Keep your study records separately and avoid identifiable health data.

## Plan a scientific study

1. Assemble licensed literature with stable identifiers and reviewed passage-level claims. Separate documents used for development from held-out evaluation documents and questions.
2. Have independent domain reviewers label relevance, applicability conditions, uncertainty, unsupported inference and citation correctness. Measure inter-rater agreement and adjudicate disagreements.
3. Fix context before running retrieval; never derive it from gold evidence IDs. Compare identical corpora, k, model versions and computational budgets. Log latency/cost when real models are added.
4. Compare lexical, learned vector, hybrid, verified KAG and optionally other GraphRAG baselines. Include no-answer and wrong-context cases. Report distributions and uncertainty, not only means.
5. Evaluate extraction separately from retrieval and answer generation. Human assessors should distinguish “used as a predictor” from “shown to be effective” and habitat suitability from transmission risk.

## Contribution workflow

Pick a roadmap issue, describe the expected behavior and review the design before substantial changes. Add focused tests; run pytest and benchmark; document verified behavior and limitations. Never commit credentials, unlicensed PDFs, sensitive observations or unreviewed claims labeled as authoritative. Model execution and external publication require separate authorization.

## OpenAI comparison

When configured, choose OpenAI semantic embeddings for a paid retrieval comparison or request a cited OpenAI answer. The vector selector controls retrieval only; generation is always OpenAI and explicitly paid. Keep offline smoke results separate from semantic-model experiments. Record actual requested/returned model, response ID, corpus hash, context, k and reported usage; provider availability is not evidence of scientific effectiveness. Citation IDs are checked against retrieved passages, but human reviewers still assess support, applicability and uncertainty. The shared benchmark continues using offline vectors; a full OpenAI benchmark is future work. See openai.md before sending real data.
