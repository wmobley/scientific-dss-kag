"""Reviewed crosswalk between fixture records and a live DYNAMO catalog.

Entries are machine-assisted *candidates*. A fixture record counts as aligned only after a human
sets review.status to "accepted" (with reviewer, date and the accepted catalog ID).
"""
REVIEW_STATES = {"unreviewed", "accepted", "rejected"}
KINDS = {"variable": "standardvariables", "model": "models"}


def validate_crosswalk(crosswalk, catalog_index, fixture):
    """catalog_index: {"standardvariables": {id: normalized}, "models": {id: normalized}}."""
    problems = []
    fixture_ids = {"variable": {v["id"] for v in fixture["variables"]}, "model": {m["id"] for m in fixture["models"]}}
    counts = {"unreviewed": 0, "accepted": 0, "rejected": 0}
    candidates_with_svo = candidates_without_svo = 0
    for entry in crosswalk.get("entries", []):
        where = f"{entry.get('kind')}:{entry.get('fixture_id')}"
        kind = entry.get("kind")
        if kind not in KINDS:
            problems.append(f"{where}: unknown kind")
            continue
        if entry.get("fixture_id") not in fixture_ids[kind]:
            problems.append(f"{where}: fixture record does not exist")
        records = catalog_index[KINDS[kind]]
        by_id = {}
        for cand in entry.get("candidates", []):
            record = records.get(cand.get("catalog_id"))
            if record is None:
                problems.append(f"{where}: catalog ID {cand.get('catalog_id')!r} not found in the catalog")
                continue
            by_id[cand["catalog_id"]] = cand
            if cand.get("label") != record["label"]:
                problems.append(f"{where}: label {cand.get('label')!r} differs from catalog label {record['label']!r}")
            if kind == "variable":
                uris = record["svo_uris"]
                if cand.get("svo_uri") is None and uris:
                    problems.append(f"{where}: catalog offers SVO URI(s) but the candidate has none")
                elif cand.get("svo_uri") is not None and cand["svo_uri"] not in uris:
                    problems.append(f"{where}: svo_uri is not one of the catalog record's sameAs URIs")
                candidates_with_svo += bool(cand.get("svo_uri"))
                candidates_without_svo += not cand.get("svo_uri")
        review = entry.get("review") or {}
        status = review.get("status")
        if status not in REVIEW_STATES:
            problems.append(f"{where}: invalid review status")
            continue
        counts[status] += 1
        if status == "accepted":
            if not (review.get("reviewer") and review.get("date") and review.get("accepted_catalog_id") in by_id):
                problems.append(f"{where}: accepted entries need reviewer, date and an accepted_catalog_id among the candidates")
        elif review.get("accepted_catalog_id") is not None:
            problems.append(f"{where}: only accepted entries may name an accepted_catalog_id")
    for gap in crosswalk.get("gaps", []):
        if not gap.get("concept") or not gap.get("reason"):
            problems.append("gap entries need a concept and a reason")
    return {"ok": not problems, "problems": problems, "review_counts": counts,
            "variable_candidates_with_svo": candidates_with_svo, "variable_candidates_without_svo": candidates_without_svo,
            "gaps": [g.get("concept") for g in crosswalk.get("gaps", [])]}


def aligned(crosswalk):
    """Fixture ID -> accepted catalog ID (and SVO URI for variables). Unreviewed candidates never appear."""
    out = {}
    for entry in crosswalk.get("entries", []):
        review = entry.get("review") or {}
        if review.get("status") != "accepted":
            continue
        chosen = next(c for c in entry["candidates"] if c["catalog_id"] == review["accepted_catalog_id"])
        out[entry["fixture_id"]] = {"catalog_id": chosen["catalog_id"], "svo_uri": chosen.get("svo_uri")}
    return out
