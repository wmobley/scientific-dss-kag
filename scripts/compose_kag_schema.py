#!/usr/bin/env python3
"""Append our decision-pathway schema to the schema KAG scaffolded for a project (idempotent).

KAG's scaffolded schema holds generic types its schema-free extractor relies on (Concept, Event,
Others, ...), so we extend it instead of replacing it. Our draft's namespace line is dropped because
the project namespace is fixed when the project is created.

    python scripts/compose_kag_schema.py work/kag/project/GwSubsidence/schema/GwSubsidence.schema
"""
import re
import sys
from pathlib import Path

MARKER = "# --- decision pathways (scientific-dss-kag, ontology/mappings/openspg/decision-pathways.schema) ---"
DRAFT = Path(__file__).resolve().parents[1] / "ontology/mappings/openspg/decision-pathways.schema"


def compose(scaffold_text, draft_text):
    if MARKER in scaffold_text:
        return scaffold_text  # already composed
    body = re.sub(r"^namespace\s+\S+\s*\n", "", draft_text, count=1).strip("\n")
    if not scaffold_text.lstrip().startswith("namespace "):
        raise ValueError("scaffold schema must start with a namespace line")
    return scaffold_text.rstrip("\n") + "\n\n" + MARKER + "\n\n" + body + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    target = Path(sys.argv[1])
    target.write_text(compose(target.read_text(), DRAFT.read_text()))
    print(f"Composed {target}")
