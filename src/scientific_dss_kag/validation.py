from .models import Pathway


def validate_pathway(pathway: Pathway, retriever):
    gaps = []
    for field in ("objective", "information_needs", "alternatives", "uncertainties", "evidence_ids"):
        if not getattr(pathway, field) or (field == "objective" and not pathway.objective.strip()):
            gaps.append(field)
    reviewed = {e.id for e in retriever.evidence if e.review_status == "reviewed"}
    invalid = sorted(set(pathway.evidence_ids) - reviewed)
    return {"structurally_complete": not gaps and not invalid, "missing": gaps,
            "invalid_or_unreviewed_evidence": invalid,
            "scientifically_validated": False,
            "note": "Completeness does not establish model suitability, epidemiological risk, or causal claims."}
