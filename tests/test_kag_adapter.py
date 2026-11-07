"""KAG adapter tests. They use the real KAG trace recorded on 2026-11-07 and fake runners: no KAG process, no model calls."""
import copy
import json
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from scientific_dss_kag.api import create_app
from scientific_dss_kag.kag_adapter import KagAdapter, KagSettings, KagUnavailable
from scientific_dss_kag.kag_citations import CitationError, answer_tags, normalize, resolve_citations
from scientific_dss_kag.models import RetrievalRequest
from scientific_dss_kag.retrieval import Retriever
from scientific_dss_kag.settings import OpenAISettings

TRACE = json.loads((Path(__file__).parent / "fixtures/kag/groundwater-trace.json").read_text())
ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "groundwater-subsidence"
REQUEST = RetrievalRequest(query="How can pumping cause permanent subsidence?", mode="kag", k=3)


@pytest.fixture(scope="module")
def retriever():
    return Retriever(domain=DOMAIN)


def evidence(retriever):
    return {e.id: e for e in retriever.evidence if e.review_status == "reviewed"}


def settings(tmp_path):
    (tmp_path / "kag_config.yaml").write_text("x: 1\n")
    python = tmp_path / "python"
    python.write_text("")
    script = tmp_path / "q.py"
    script.write_text("")
    return KagSettings(project_dir=tmp_path, python=python, script=script)


def adapter(tmp_path, result=None, runner=None, healthy=True):
    def default_runner(query, out_path):
        out_path.write_text(json.dumps(result if result is not None else TRACE))
    instance = KagAdapter(settings(tmp_path), runner=runner or default_runner)
    if healthy is None:  # simulate the OpenSPG server being down, whatever is really running on this machine
        def down():
            raise KagUnavailable("kag_server_unavailable", "The local OpenSPG server is not responding.")
        instance._check_server = down
    elif healthy:
        instance._check_server = lambda: None
    return instance


def test_recorded_trace_resolves_to_canonical_evidence(retriever):
    ranked = resolve_citations(TRACE, evidence(retriever), retriever.sources)
    assert [e.id for _, e in ranked] == ["ev-gw-drawdown", "ev-gw-decision", "ev-gw-modflow", "ev-gw-observations"]  # best score per ID; the 0.5 tie breaks by ID
    assert [s for s, _ in ranked] == sorted([s for s, _ in ranked], reverse=True) and ranked[0][0] == 1.0  # best score per ID, duplicates merged
    drawdown = ranked[0][1]
    assert drawdown.source_hash and drawdown.end > drawdown.start  # hash and offsets come from our record, not KAG


def test_normalisation_makes_kags_rewritten_text_equal_to_ours(retriever):
    ev = evidence(retriever)["ev-gw-drawdown"]
    kag_text = next(r["content"] for r in TRACE["reference"] if r["chunk_id"] == ev.id)
    assert kag_text != ev.passage and "\\n" in kag_text and kag_text.startswith('"')  # literal backslash-n, as recorded
    assert normalize(kag_text) == normalize(retriever.sources[ev.source_id]["title"]) + " " + normalize(ev.passage)


def mutated(retriever, edit):
    trace = copy.deepcopy(TRACE)
    edit(trace)
    return resolve_citations(trace, evidence(retriever), retriever.sources)


@pytest.mark.parametrize("edit,why", [
    (lambda t: t["reference"][0].update(content='"Drawdown, compaction and subsidence\nTampered text."'), "differs"),
    (lambda t: t["reference"][0].update(chunk_id="ev-gw-candidate"), "not reviewed evidence"),   # candidates never become citations
    (lambda t: t["reference"][0].update(chunk_id="ev-invented"), "not reviewed evidence"),
    (lambda t: t["reference"][0].pop("chunk_id"), "malformed"),
    (lambda t: t["reference"][0].update(content=5), "malformed"),
    (lambda t: t["reference"][0].update(score="high"), "non-numeric"),
    (lambda t: t.pop("reference"), "no reference list"),
    (lambda t: t.update(reference="nope"), "no reference list"),
])
def test_any_bad_reference_rejects_the_whole_result(retriever, edit, why):
    with pytest.raises(CitationError, match=why):
        mutated(retriever, edit)


def test_answer_tags_are_reported_but_not_trusted():
    assert answer_tags(TRACE["answer"]) == ["chunk:0_0"] and answer_tags("") == [] and answer_tags(None) == []


def test_retrieve_returns_resolved_results_and_honest_attribution(tmp_path, retriever):
    out = adapter(tmp_path).retrieve(REQUEST, retriever)
    assert out["mode"] == "kag" and [r["evidence"]["id"] for r in out["results"]] == ["ev-gw-drawdown", "ev-gw-decision", "ev-gw-modflow"]  # k=3
    assert out["answer_reference_tags"] == ["chunk:0_0"] and "not independently verified" in out["attribution"]
    assert out["results"][0]["source"]["id"] == "gw-drawdown" and out["corpus_hash"] == retriever.corpus_hash


def test_failures_are_explicit_and_never_leak_stderr(tmp_path, retriever):
    def boom(query, out_path):
        raise KagUnavailable("kag_failed", "KAG exited with an error; check the gateway call cap and rate limit and the OpenSPG logs.")
    for build, code in ((lambda: adapter(tmp_path, runner=boom), "kag_failed"),
                        (lambda: adapter(tmp_path, runner=None, healthy=None), "kag_server_unavailable"),
                        (lambda: adapter(tmp_path, runner=lambda q, o: None), "kag_invalid_result"),
                        (lambda: adapter(tmp_path, runner=lambda q, o: o.write_text("not json")), "kag_invalid_result"),
                        (lambda: adapter(tmp_path, result={"answer": 5}), "kag_invalid_result"),
                        (lambda: adapter(tmp_path, result={"answer": "x", "reference": [{"chunk_id": "ev-invented", "content": "x"}]}), "kag_invalid_result")):
        with pytest.raises(KagUnavailable) as info:
            build().retrieve(REQUEST, retriever)
        assert info.value.code == code, code


def test_unreachable_server_is_reported(tmp_path, retriever):
    instance = KagAdapter(settings(tmp_path), runner=lambda q, o: pytest.fail("must not run KAG when the server is down"))
    import scientific_dss_kag.kag_adapter as module
    original = module.httpx.Client
    module.httpx.Client = lambda **kw: original(transport=httpx.MockTransport(lambda r: httpx.Response(500)), **kw)
    try:
        with pytest.raises(KagUnavailable) as info:
            instance.retrieve(REQUEST, retriever)
    finally:
        module.httpx.Client = original
    assert info.value.code == "kag_server_unavailable"


def test_domain_mismatch_not_installed_and_busy(tmp_path):
    other = Retriever(domain="vector-borne-disease")
    with pytest.raises(KagUnavailable) as info:
        adapter(tmp_path).retrieve(REQUEST, other)
    assert info.value.code == "kag_domain_mismatch"
    absent = KagAdapter(KagSettings(project_dir=tmp_path / "none", python=tmp_path / "none", script=tmp_path / "none"))
    with pytest.raises(KagUnavailable) as info:
        absent.retrieve(REQUEST, Retriever(domain=DOMAIN))
    assert info.value.code == "kag_not_installed"
    busy = adapter(tmp_path)
    busy._lock.acquire()
    with pytest.raises(KagUnavailable) as info:
        busy.retrieve(REQUEST, Retriever(domain=DOMAIN))
    assert (info.value.code, info.value.status) == ("kag_busy", 429)


@pytest.mark.parametrize("bad", ["http://example.com:8887", "https://127.0.0.1:8887", "http://user:pw@127.0.0.1:8887"])
def test_server_must_be_loopback_http(bad):
    with pytest.raises(ValueError):
        KagSettings(server=bad)


def test_the_kag_process_receives_no_secrets(tmp_path, monkeypatch):
    import scientific_dss_kag.kag_adapter as module
    monkeypatch.setenv("OPENAI_API_KEY", "upstream-key-must-not-leak")
    monkeypatch.setenv("DSS_GATEWAY_TOKEN", "gateway-token-must-not-leak")
    seen = {}

    def fake_run(args, **kwargs):
        seen.update(kwargs)
        class Done: returncode = 0
        return Done()
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    KagAdapter(settings(tmp_path))._run_subprocess("q", tmp_path / "out.json")
    assert "OPENAI_API_KEY" not in seen["env"] and "DSS_GATEWAY_TOKEN" not in seen["env"] and "PATH" in seen["env"]
    assert seen["cwd"] == tmp_path and seen["timeout"] == 300


def test_api_serves_kag_results_and_protects_the_paid_route(tmp_path):
    instance = adapter(tmp_path)
    with TestClient(create_app(settings=OpenAISettings(), domain=DOMAIN, kag=instance), base_url="http://127.0.0.1") as client:
        body = client.post("/retrieve", json={"query": "pumping and subsidence", "mode": "kag", "k": 2}).json()
        assert [r["evidence"]["id"] for r in body["results"]] == ["ev-gw-drawdown", "ev-gw-decision"]
        assert client.post("/retrieve", json={"query": "x", "mode": "kag"}, headers={"Origin": "http://evil.example"}).status_code == 403
    with TestClient(create_app(settings=OpenAISettings(), domain=DOMAIN, kag=instance)) as client:  # Host 'testserver' is not localhost
        assert client.post("/retrieve", json={"query": "x", "mode": "kag"}).status_code == 403
    with TestClient(create_app(settings=OpenAISettings(), domain="vector-borne-disease", kag=instance), base_url="http://127.0.0.1") as client:
        response = client.post("/retrieve", json={"query": "x", "mode": "kag"})
        assert response.status_code == 503 and response.json()["detail"]["code"] == "kag_domain_mismatch"


def test_relative_settings_become_absolute_paths_without_following_the_venv_symlink(tmp_path, monkeypatch):
    import scientific_dss_kag.kag_adapter as module
    real = tmp_path / "real-python"
    real.write_text("")
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to(real)
    (tmp_path / "project").mkdir()
    (tmp_path / "project" / "kag_config.yaml").write_text("x: 1\n")
    (tmp_path / "q.py").write_text("")
    monkeypatch.chdir(tmp_path)
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"], seen["cwd"] = args, kwargs["cwd"]
        class Done: returncode = 0
        return Done()
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    relative = KagSettings(project_dir=Path("project"), python=Path("venv/bin/python"), script=Path("q.py"))
    KagAdapter(relative)._run_subprocess("q", tmp_path / "out.json")
    assert seen["args"][0] == str(tmp_path / "venv/bin/python") and Path(seen["args"][0]).is_symlink()  # the venv path, not the base interpreter
    assert seen["args"][1] == str(tmp_path / "q.py") and seen["cwd"] == tmp_path / "project"
