import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
import pytest
from scientific_dss_kag.crosswalk import aligned, apply_review
from scientific_dss_kag.domain import load

DOMAIN = "groundwater-subsidence"
ROOT = Path(__file__).resolve().parents[1]


def crosswalk():
    return copy.deepcopy(load(DOMAIN, "crosswalk.json"))


def entry(cw, fixture_id):
    return next(e for e in cw["entries"] if e["fixture_id"] == fixture_id)


def test_accepting_records_the_decision_and_makes_the_entry_aligned_without_touching_the_input():
    original = crosswalk()
    updated = apply_review(original, "urn:example:variable:groundwater-head", "accepted", "Dr Reviewer", "2026-11-08")
    review = entry(updated, "urn:example:variable:groundwater-head")["review"]
    assert review["status"] == "accepted" and review["reviewer"] == "Dr Reviewer" and review["date"] == "2026-11-08"
    assert review["accepted_catalog_id"] == entry(original, "urn:example:variable:groundwater-head")["candidates"][0]["catalog_id"]
    assert list(aligned(updated)) == ["urn:example:variable:groundwater-head"] and aligned(original) == {}
    assert original == crosswalk()  # the input is not mutated


@pytest.mark.parametrize("kwargs", [dict(reviewer=None, date="2026-11-08"), dict(reviewer="  ", date="2026-11-08"), dict(reviewer="R", date=None),
                                    dict(reviewer="R", date="8 Nov 2026"), dict(reviewer="R", date="2026-11-08", catalog_id="https://example.org/not-a-candidate")])
def test_accepting_needs_a_reviewer_a_date_and_one_of_the_entrys_own_candidates(kwargs):
    with pytest.raises(ValueError):
        apply_review(crosswalk(), "urn:example:variable:groundwater-head", "accepted", **kwargs)


def test_several_candidates_force_an_explicit_choice():
    cw = load("vector-borne-disease", "crosswalk.json")
    fixture_id = "urn:example:variable:temperature"
    with pytest.raises(ValueError, match="candidate catalog IDs"):
        apply_review(cw, fixture_id, "accepted", "R", "2026-11-08")
    chosen = cw["entries"][0]["candidates"][1]["catalog_id"]
    assert aligned(apply_review(cw, fixture_id, "accepted", "R", "2026-11-08", chosen))[fixture_id]["catalog_id"] == chosen


def test_reject_unreview_and_unknown_entries():
    updated = apply_review(crosswalk(), "urn:example:variable:drawdown", "rejected", "R", "2026-11-08")
    assert entry(updated, "urn:example:variable:drawdown")["review"]["status"] == "rejected" and aligned(updated) == {}
    back = apply_review(updated, "urn:example:variable:drawdown", "unreviewed")
    assert entry(back, "urn:example:variable:drawdown")["review"] == {"status": "unreviewed", "reviewer": None, "date": None, "accepted_catalog_id": None}
    for bad in ("urn:example:variable:nope", ""):
        with pytest.raises(ValueError):
            apply_review(crosswalk(), bad, "unreviewed")
    with pytest.raises(ValueError):
        apply_review(crosswalk(), "urn:example:variable:drawdown", "approved")


def test_command_lists_and_records_in_a_copy_of_the_repository_data(tmp_path):
    shutil.copytree(ROOT / "domains", tmp_path / "domains")
    run = lambda *args: subprocess.run([sys.executable, "-m", "scientific_dss_kag.cli", "crosswalk-review", "--domain", DOMAIN, *args],
                                       cwd=tmp_path, capture_output=True, text=True)
    listing = run("--list")
    assert listing.returncode == 0 and listing.stdout.count("unreviewed") == 7 and "groundwater__head (SVO, high)" in listing.stdout
    refused = run("--fixture-id", "urn:example:variable:groundwater-head", "--status", "accepted")
    assert refused.returncode != 0 and "reviewer" in refused.stderr
    done = run("--fixture-id", "urn:example:variable:groundwater-head", "--status", "accepted", "--reviewer", "Dr Reviewer", "--date", "2026-11-08")
    assert done.returncode == 0, done.stderr
    saved = json.loads((tmp_path / "domains" / DOMAIN / "crosswalk.json").read_text())
    assert entry(saved, "urn:example:variable:groundwater-head")["review"]["reviewer"] == "Dr Reviewer"
    assert json.loads((ROOT / "domains" / DOMAIN / "crosswalk.json").read_text()) == crosswalk()  # the real file is untouched by the test
