# Experimental OpenSPG projection

Status: **draft, not committed or queried against an OpenSPG server**.

`decision-pathways.schema` projects the 15 canonical classes and selected directed relationships into namespace `DecisionPathways`. The `EntityType`, `properties`, `TextAndVector`, and `relations` syntax was inspected in the [upstream Medicine example](https://github.com/OpenSPG/KAG/blob/master/kag/examples/medicine/schema/Medicine.schema). This is a syntax reference, not proof of compatibility with a particular deployed version.

`mapping.json` explicitly records omitted literal properties and semantic losses. Keep exact source records, passage offsets/hashes, review status, and decision context in the canonical RDF/application layer. The initial projection carries descriptions only; it cannot independently validate provenance or scientific applicability. Preserve canonical IDs in an ingestion-side identifier map before loading entities.

Follow the upstream KAG developer setup for the chosen pinned release, create its project, review namespace configuration, then run its schema commit command in that project. Record the KAG/OpenSPG versions, schema commit result, and a query linking InformationNeed → ScientificMethod → ComputationalModel before changing this status. No local test here verifies a live KAG integration.

The lower-case `objective`, `informationNeed`, `alternative`, and `uncertainty` properties are string-valued pathway summaries used by the initial application validation contract. They are distinct from object links such as `hasObjective` (DecisionProblem → Objective). A summary string does not create or identify an Objective node. The projection does not translate these convenience fields into object links. Each provenance scalar has SHACL datatype and single-value constraints; pathway summary strings are required but may be repeated.
