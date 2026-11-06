"""Canonical RDF/SHACL checks; these do not test a live OpenSPG server."""
import json
from pathlib import Path

import pytest
from pyshacl import validate
from rdflib import Graph, Literal, Namespace, RDF, OWL, URIRef

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "ontology"
DP = Namespace("https://example.org/scientific-dss/decision-pathways#")
CLASSES = {"DecisionProblem", "Stakeholder", "Objective", "Alternative", "Uncertainty", "InformationNeed", "ScientificMethod", "ComputationalModel", "Dataset", "Evidence", "ScientificClaim", "ScientificVariable", "Assumption", "ValidationActivity", "DecisionPathway"}


def conforms(graph):
    return validate(graph, shacl_graph=Graph().parse(ONTOLOGY / "shapes.ttl"), inference="none", do_owl_imports=False)[0]


def valid_graph():
    return Graph().parse(ONTOLOGY / "examples/valid.ttl")


def test_canonical_classes_and_mapping_coverage():
    graph = Graph().parse(ONTOLOGY / "decision-pathways.ttl")
    assert set(graph.subjects(RDF.type, OWL.Class)) == {DP[name] for name in CLASSES}
    assert not list(graph.triples((None, OWL.imports, None)))
    mapping = json.loads((ONTOLOGY / "mappings/openspg/mapping.json").read_text())
    assert set(mapping["classes"]) == {str(DP[name]) for name in CLASSES}
    assert mapping["status"] == "draft-unverified"
    schema = (ONTOLOGY / "mappings/openspg/decision-pathways.schema").read_text()
    for name in CLASSES:
        assert f"{name}({name}): EntityType" in schema
    for relation in mapping["relations"]:
        assert (DP[relation["rdf_property"].split("#")[-1]], RDF.type, OWL.ObjectProperty) in graph
        assert f'{relation["spg_relation"]}({relation["spg_relation"]}): {relation["target"]}' in schema


def test_shacl_examples():
    assert conforms(valid_graph())
    assert not conforms(Graph().parse(ONTOLOGY / "examples/invalid.ttl"))


@pytest.mark.parametrize("field", ["sourceId", "sourceHash", "passage", "start", "end", "reviewStatus"])
def test_each_evidence_field_required(field):
    graph = valid_graph()
    graph.remove((DP.exampleEvidence, DP[field], None))
    assert not conforms(graph)


@pytest.mark.parametrize("field", ["objective", "informationNeed", "alternative", "uncertainty"])
def test_each_pathway_field_required(field):
    graph = valid_graph()
    graph.remove((DP.examplePathway, DP[field], None))
    assert not conforms(graph)


@pytest.mark.parametrize("field,value", [
    ("sourceHash", Literal("not-a-sha256")),
    ("reviewStatus", Literal("approved-by-ai")),
    ("start", Literal(-1)),
    ("end", Literal(0)),
    ("start", Literal(1000)),
    ("passage", Literal("")),
    ("start", Literal("zero", datatype=URIRef("http://www.w3.org/2001/XMLSchema#string"))),
])
def test_invalid_provenance_constraints(field, value):
    graph = valid_graph()
    graph.set((DP.exampleEvidence, DP[field], value))
    assert not conforms(graph)


def test_duplicate_scalar_rejected():
    graph = valid_graph()
    graph.add((DP.exampleEvidence, DP.sourceId, Literal("another-source")))
    assert not conforms(graph)
