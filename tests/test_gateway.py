"""Gateway tests use MockTransport only: no network, no real credentials."""
import json
import time
import httpx
import pytest
from fastapi.testclient import TestClient
from scientific_dss_kag.gateway import create_gateway_app
from scientific_dss_kag.settings import GatewaySettings, OpenAISettings

UPSTREAM_KEY = "upstream-key-not-real-0123456789"
TOKEN = "local-gateway-token-0123456789"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
UPSTREAM = "https://ai.tejas.tacc.utexas.edu"


def settings(**overrides):
    values = dict(upstream_base_url=UPSTREAM, upstream_api_key=UPSTREAM_KEY, token=TOKEN)
    values.update(overrides)
    return GatewaySettings(**values)


def make(calls, status=200, body=None, headers=None, **overrides):
    def handler(request):
        calls.append(request)
        assert request.url.host == "ai.tejas.tacc.utexas.edu"
        assert request.headers["authorization"] == f"Bearer {UPSTREAM_KEY}"
        return httpx.Response(status, json=body if body is not None else {"ok": True}, headers=headers)
    return TestClient(create_gateway_app(settings(**overrides), transport=httpx.MockTransport(handler)))


def post(client, path="/v1/embeddings", **kw):
    return client.post(path, json={"model": "m", "input": ["x"]}, headers=AUTH, **kw)


def test_requires_local_token_and_never_calls_upstream_without_it():
    calls = []
    with make(calls) as client:
        assert client.post("/v1/embeddings", json={}).status_code == 401
        assert client.post("/v1/embeddings", json={}, headers={"Authorization": f"Bearer {UPSTREAM_KEY}"}).status_code == 401
        assert client.get("/status").status_code == 401
    assert not calls


def test_forwards_with_upstream_key_not_local_token():
    calls = []
    with make(calls) as client:
        response = post(client)
    assert response.status_code == 200 and response.json() == {"ok": True}
    assert len(calls) == 1 and calls[0].url.path == "/v1/embeddings"
    assert TOKEN not in str(calls[0].headers)


def test_only_llm_routes_are_forwarded():
    calls = []
    with make(calls) as client:
        assert post(client, "/v1/files").status_code == 404
        assert client.delete("/v1/models", headers=AUTH).status_code == 405
        assert client.get("/v1/models", headers=AUTH).status_code == 200
    assert len(calls) == 1


def test_rate_limit_queues_instead_of_failing():
    calls = []
    with make(calls, rate_per_minute=2, window_seconds=0.4) as client:
        start = time.monotonic()
        assert [post(client).status_code for _ in range(3)] == [200, 200, 200]
        elapsed = time.monotonic() - start
    assert elapsed >= 0.35, "third call must wait for the window"
    assert len(calls) == 3


def test_queue_wait_is_bounded_and_does_not_reach_upstream():
    calls = []
    with make(calls, rate_per_minute=1, window_seconds=30, max_wait_seconds=0.1) as client:
        assert post(client).status_code == 200
        blocked = post(client)
    assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "gateway_rate_limited"
    assert len(calls) == 1


def test_call_cap_is_enforced():
    calls = []
    with make(calls, max_calls=1) as client:
        assert post(client).status_code == 200
        capped = post(client)
        assert capped.status_code == 429 and capped.json()["error"]["code"] == "gateway_call_cap"
        status = client.get("/status", headers=AUTH).json()
    assert len(calls) == 1 and status["calls_total"] == 1 and status["call_cap"] == 1


def test_upstream_429_pauses_everyone_and_is_never_resent():
    calls = []
    with make(calls, status=429, headers={"Retry-After": "2"}, max_wait_seconds=0.1) as client:
        first = post(client)
        second = post(client)
        status = client.get("/status", headers=AUTH).json()
    assert first.status_code == 429 and first.json()["error"]["code"] == "upstream_rate_limited"
    assert first.headers["retry-after"] == "2"
    assert second.json()["error"]["code"] == "gateway_rate_limited"
    assert len(calls) == 1 and status["paused_seconds"] > 0 and status["last_429_seconds_ago"] is not None


def test_upstream_errors_do_not_leak_provider_bodies():
    calls = []
    with make(calls, status=500, body={"detail": "SECRET-INTERNAL-TRACE"}) as client:
        response = post(client)
    assert response.status_code == 502 and "SECRET-INTERNAL-TRACE" not in response.text
    assert response.json()["error"]["code"] == "upstream_error"


def test_status_exposes_no_credentials():
    with make([]) as client:
        text = client.get("/status", headers=AUTH).text
    assert UPSTREAM_KEY not in text and TOKEN not in text and "tejas" in text


def test_oversized_requests_are_rejected_before_upstream():
    calls = []
    with make(calls) as client:
        response = client.post("/v1/embeddings", content=b"x" * (1024 * 1024 + 1), headers=AUTH)
    assert response.status_code == 413 and not calls


@pytest.mark.parametrize("bad", [
    dict(upstream_base_url="http://127.0.0.1:9999/v1"),       # upstream cannot be loopback (no gateway loops)
    dict(upstream_base_url="https://evil.example.com/v1"),    # not allowlisted
    dict(upstream_base_url="https://api.openai.com.evil.com/v1"),
    dict(upstream_base_url="https://user:pw@api.openai.com/v1"),
    dict(token="short"), dict(upstream_api_key=""), dict(rate_per_minute=0), dict(rate_per_minute=101),
])
def test_gateway_settings_reject_unsafe_values(bad):
    with pytest.raises(ValueError):
        settings(**bad)


def test_openai_settings_endpoint_allowlist_and_normalization():
    assert OpenAISettings(base_url="https://ai.tejas.tacc.utexas.edu").endpoint == "https://ai.tejas.tacc.utexas.edu/v1"
    assert OpenAISettings(base_url="https://api.openai.com/v1/").endpoint == "https://api.openai.com/v1"
    assert OpenAISettings(base_url="http://127.0.0.1:8092/v1").endpoint == "http://127.0.0.1:8092/v1"
    for bad in ("http://evil.example.com/v1", "http://api.openai.com/v1", "https://api.openai.com.evil.com/v1",
                "https://user:pw@api.openai.com/v1", "https://api.openai.com/v1?x=1", "ftp://api.openai.com"):
        with pytest.raises(ValueError):
            OpenAISettings(base_url=bad)


def test_app_uses_gateway_and_token_when_configured(monkeypatch):
    monkeypatch.chdir("/")  # no .env
    monkeypatch.setenv("DSS_GATEWAY_URL", "http://127.0.0.1:8092/v1")
    monkeypatch.setenv("DSS_GATEWAY_TOKEN", TOKEN)
    monkeypatch.setenv("OPENAI_API_KEY", UPSTREAM_KEY)
    loaded = OpenAISettings.from_env()
    assert loaded.endpoint == "http://127.0.0.1:8092/v1" and loaded.api_key == TOKEN
