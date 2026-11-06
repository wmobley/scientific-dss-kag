"""DYNAMO catalog contract tests against responses recorded from the dev catalog on 2026-11-06
(trimmed; author fields removed). No network."""
import copy
import json
from pathlib import Path
import httpx
import pytest
from scientific_dss_kag.connectors import CatalogClient, SVO_PREFIX, flatten, first_text, normalize_record
from scientific_dss_kag.crosswalk import aligned, validate_crosswalk
from scientific_dss_kag.domain import available_domains, load
from scientific_dss_kag.settings import catalog_url_from_env

FIX = Path(__file__).parent / "fixtures" / "dynamo"
VARS = json.loads((FIX / "standardvariables.json").read_text())
MODELS = json.loads((FIX / "models.json").read_text())
BASE = "https://mintdevapi.pods.portals.tapis.io/v2.0.0"


def paged(data, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(request)
        assert request.method == "GET" and "authorization" not in request.headers
        page, per = int(request.url.params["page"]), int(request.url.params["per_page"])
        return httpx.Response(200, json=data[(page - 1) * per: page * per])
    return httpx.MockTransport(handler)


def index():
    out = {}
    for kind, data in (("standardvariables", VARS), ("models", MODELS)):
        with CatalogClient(BASE, transport=paged(data)) as c:
            out[kind] = c.list_all(kind, per_page=2)["normalized"]
    return out


CatalogClient.__enter__ = lambda self: self
CatalogClient.__exit__ = lambda self, *a: self.close()


def test_recorded_shapes_normalize_list_valued_fields():
    record = normalize_record(VARS[0], "standardvariables")
    assert isinstance(record["label"], str) and record["label"]
    assert all(u.startswith(SVO_PREFIX) for u in record["svo_uris"])
    assert first_text(["a", "b"]) == "a" and first_text([]) == "" and first_text(None) == ""
    assert list(flatten([["x", ["y"]], "z", 3])) == ["x", "y", "z"]
    unmapped = next(r for r in VARS if not r.get("sameAs"))
    assert normalize_record(unmapped, "standardvariables")["svo_uris"] == []
    other = normalize_record({"id": "i", "label": ["l"], "sameAs": [["http://example.org/x"]]}, "standardvariables")
    assert other["svo_uris"] == [] and other["other_same_as"] == ["http://example.org/x"]


def test_list_all_pages_with_get_only_and_no_credentials():
    calls = []
    with CatalogClient(BASE, transport=paged(VARS, calls)) as c:
        result = c.list_all("standardvariables", per_page=2)
    assert [r["id"] for r in result["records"]] == [v["id"] for v in VARS]
    # Full pages are followed by one more request (empty or short page) to detect the end.
    assert len(calls) == len(VARS) // 2 + 1
    assert {r.url.path for r in calls} == {"/v2.0.0/standardvariables"}


def test_paging_that_does_not_advance_fails_loudly():
    always_first = httpx.MockTransport(lambda r: httpx.Response(200, json=VARS[:2]))
    with CatalogClient(BASE, transport=always_first) as c, pytest.raises(ValueError, match="did not advance"):
        c.list_all("standardvariables", per_page=2)


def test_bounds_and_bad_shapes_fail_loudly():
    many = httpx.MockTransport(lambda r: httpx.Response(200, json=[{"id": f"{r.url.params['page']}-{i}"} for i in range(2)]))
    with CatalogClient(BASE, transport=many) as c:
        with pytest.raises(ValueError, match="page bound"):
            c.list_all("models", per_page=2, max_pages=3)
        with pytest.raises(ValueError, match="record bound"):
            c.list_all("models", per_page=2, max_records=3)
        with pytest.raises(ValueError):
            c.list_all("executions")
    with CatalogClient(BASE, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"items": []}))) as c, pytest.raises(ValueError):
        c.list_all("models")
    with CatalogClient(BASE, transport=httpx.MockTransport(lambda r: httpx.Response(500))) as c, pytest.raises(httpx.HTTPStatusError):
        c.list_all("models")


@pytest.mark.parametrize("domain", ["vector-borne-disease", "groundwater-subsidence"])
def test_every_domain_crosswalk_validates_against_recorded_catalog(domain):
    report = validate_crosswalk(load(domain, "crosswalk.json"), index(), load(domain, "catalog.json"))
    assert report["ok"], report["problems"]
    assert report["review_counts"]["accepted"] == 0, "no entry may be accepted without human review"
    assert aligned(load(domain, "crosswalk.json")) == {}


def test_groundwater_domain_reports_missing_svo_mapping_honestly():
    report = validate_crosswalk(load("groundwater-subsidence", "crosswalk.json"), index(), load("groundwater-subsidence", "catalog.json"))
    assert report["variable_candidates_without_svo"] >= 1 and report["variable_candidates_with_svo"] >= 4


def test_sdm_domain_documents_catalog_gaps():
    gaps = load("vector-borne-disease", "crosswalk.json")["gaps"]
    assert any("habitat" in g["concept"] for g in gaps) and all(g["reason"] for g in gaps)


def mutated(domain, edit):
    cw = copy.deepcopy(load(domain, "crosswalk.json"))
    edit(cw)
    return validate_crosswalk(cw, index(), load(domain, "catalog.json"))


GW = "groundwater-subsidence"


@pytest.mark.parametrize("edit,expect", [
    (lambda cw: cw["entries"][0]["candidates"][0].update(catalog_id="https://example.org/missing"), "not found"),
    (lambda cw: cw["entries"][0]["candidates"][0].update(svo_uri=SVO_PREFIX + "invented"), "not one of"),
    (lambda cw: cw["entries"][0]["candidates"][0].update(svo_uri=None), "has none"),
    (lambda cw: cw["entries"][0]["candidates"][0].update(label="renamed"), "differs"),
    (lambda cw: cw["entries"][0].update(fixture_id="urn:example:variable:nope"), "does not exist"),
    (lambda cw: cw["entries"][0].update(kind="dataset"), "unknown kind"),
    (lambda cw: cw["entries"][0]["review"].update(status="approved"), "invalid review status"),
    (lambda cw: cw["entries"][0]["review"].update(status="accepted"), "accepted entries need"),
    (lambda cw: cw["entries"][0]["review"].update(accepted_catalog_id="x"), "only accepted"),
    (lambda cw: cw["gaps"].append({"concept": "x"}), "gap entries"),
])
def test_crosswalk_validation_rejects_bad_entries(edit, expect):
    report = mutated(GW, edit)
    assert not report["ok"] and any(expect in p for p in report["problems"]), report["problems"]


def test_accepted_entries_become_aligned_only_with_full_review():
    def accept(cw):
        entry = cw["entries"][0]
        entry["review"] = {"status": "accepted", "reviewer": "reviewer-name", "date": "2026-11-07",
                           "accepted_catalog_id": entry["candidates"][0]["catalog_id"]}
    cw = copy.deepcopy(load(GW, "crosswalk.json"))
    accept(cw)
    assert validate_crosswalk(cw, index(), load(GW, "catalog.json"))["ok"]
    result = aligned(cw)
    assert list(result) == [cw["entries"][0]["fixture_id"]] and result[cw["entries"][0]["fixture_id"]]["svo_uri"].startswith(SVO_PREFIX)


@pytest.mark.parametrize("url", ["http://mintdevapi.pods.portals.tapis.io/v2.0.0", "https://evil.example.com/v2.0.0",
                                 "https://mintdevui.pods.portals.tapis.io/", "https://user:pw@mintdevapi.pods.portals.tapis.io/v2.0.0",
                                 "https://mintdevapi.pods.portals.tapis.io/v2.0.0?x=1", "", "https://mintdevapi.pods.portals.tapis.io.evil.com/"])
def test_catalog_url_must_be_allowlisted_https(monkeypatch, url):
    monkeypatch.chdir("/")
    monkeypatch.setenv("DSS_CATALOG_URL", url)
    with pytest.raises(ValueError):
        catalog_url_from_env()


def test_catalog_url_accepts_dev_api_and_trims_slash(monkeypatch):
    monkeypatch.chdir("/")
    monkeypatch.setenv("DSS_CATALOG_URL", BASE + "/")
    assert catalog_url_from_env() == BASE
