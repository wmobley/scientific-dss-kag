import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("compose_kag_schema", ROOT / "scripts/compose_kag_schema.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SCAFFOLD = "namespace GwSubsidence\n\nConcept(概念): EntityType\n     properties:\n        desc(描述): Text\n            index: Text\n"
DRAFT = (ROOT / "ontology/mappings/openspg/decision-pathways.schema").read_text()


def test_scaffold_types_are_kept_and_ours_are_appended_under_the_project_namespace():
    out = module.compose(SCAFFOLD, DRAFT)
    assert out.startswith("namespace GwSubsidence\n") and out.count("namespace ") == 1
    assert "Concept(概念): EntityType" in out
    for name in ("DecisionProblem", "ScientificMethod", "ComputationalModel", "ValidationActivity"):
        assert f"{name}({name}): EntityType" in out


def test_composition_is_idempotent_and_does_not_mutate_inputs():
    once = module.compose(SCAFFOLD, DRAFT)
    assert module.compose(once, DRAFT) == once and once.count(module.MARKER) == 1


def test_scaffold_without_namespace_is_rejected():
    with pytest.raises(ValueError):
        module.compose("Concept(x): EntityType\n", DRAFT)


def test_draft_type_names_do_not_clash_with_kag_scaffold_names():
    scaffold_types = {"SemanticConcept", "ArtificialObject", "Astronomy", "Building", "Creature", "Concept", "Date",
                      "GeographicLocation", "Keyword", "Medicine", "NaturalScience", "Organization", "Person", "Transport",
                      "Works", "Event", "Others", "Chunk"}
    ours = {line.split("(")[0] for line in DRAFT.splitlines() if "): EntityType" in line or "): EventType" in line}
    assert ours and not (ours & scaffold_types)
