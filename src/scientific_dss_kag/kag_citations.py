"""Resolve KAG solver references to our canonical, reviewed evidence.

KAG keeps our evidence ID as the chunk ID but rewrites the text (outer quotes, the title as a first line,
one sentence per line) and does not store our source hash or offsets. So each reference is joined to our own
record by ID, and its text must match ours after normalisation. Anything else is rejected whole: no partial
or best-effort citation results.
"""
import re

ANSWER_TAG = re.compile(r'<reference id="(chunk:\d+_\d+)"></reference>')


class CitationError(ValueError):
    pass


def normalize(text):
    """KAG's trace keeps newlines as the two characters backslash and n (its own prompt-building code undoes
    that), so those count as whitespace along with real newlines."""
    text = text.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    return " ".join(text.replace("\\n", " ").split())


def resolve_citations(trace, evidence_by_id, sources):
    """Return [(score, evidence)] best-first, one entry per evidence ID, from a KAG trace's reference list."""
    references = trace.get("reference") if isinstance(trace, dict) else None
    if not isinstance(references, list):
        raise CitationError("KAG result has no reference list")
    best = {}
    for reference in references:
        if not isinstance(reference, dict) or not isinstance(reference.get("chunk_id"), str) or not isinstance(reference.get("content"), str):
            raise CitationError("KAG returned a malformed reference")
        chunk_id = reference["chunk_id"]
        evidence = evidence_by_id.get(chunk_id)
        if evidence is None:
            raise CitationError("KAG referenced a chunk that is not reviewed evidence of this domain")
        expected = normalize(sources[evidence.source_id]["title"]) + " " + normalize(evidence.passage)
        if normalize(reference["content"]) != expected:
            raise CitationError("KAG reference text differs from our evidence passage")
        try:
            score = float(reference.get("score", 0))
        except (TypeError, ValueError):
            raise CitationError("KAG returned a non-numeric reference score") from None
        if chunk_id not in best or score > best[chunk_id][0]:
            best[chunk_id] = (score, evidence)
    return sorted(best.values(), key=lambda pair: (-pair[0], pair[1].id))


def answer_tags(answer):
    """Tags such as chunk:0_0 used inside KAG's answer text. KAG's mapping from a tag to a document is internal and
    was not exposed in its trace, so these are reported as unverified and never used for per-sentence attribution."""
    return sorted(set(ANSWER_TAG.findall(answer or "")))
