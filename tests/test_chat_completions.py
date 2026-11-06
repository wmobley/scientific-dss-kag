"""Chat Completions path against an OpenAI-compatible endpoint (MockTransport; no network)."""
import json
import httpx
import pytest
from scientific_dss_kag.models import RetrievalRequest
from scientific_dss_kag.openai_provider import OpenAIProvider, ProviderError
from scientific_dss_kag.retrieval import Retriever
from scientific_dss_kag.settings import OpenAISettings

KEY = "test-key-never-a-real-credential"
HOST = "ai.tejas.tacc.utexas.edu"
GOOD = {"status": "answered", "claims": [{"text": "Background selection affects interpretation.", "evidence_ids": ["ev-maxent"]}],
        "gaps": [], "uncertainties": ["Synthetic teaching notes."]}


def chat(content=GOOD, finish="stop", **message):
    body = content if isinstance(content, str) or content is None else json.dumps(content)
    return {"id": "chatcmpl-test", "model": "gpt-oss-120b",
            "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": body, **message}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50}}


def make(response=None, calls=None):
    calls = calls if calls is not None else []

    def handler(request):
        body = json.loads(request.content)
        calls.append((request, body))
        assert request.url.host == HOST and request.headers["authorization"] == f"Bearer {KEY}"
        if request.url.path == "/v1/embeddings":
            rows = [{"index": i, "embedding": [1.0, float(i + 1), .5]} for i in range(len(body["input"]))]
            return httpx.Response(200, json={"data": rows, "model": body["model"], "usage": {"prompt_tokens": 5, "total_tokens": 5}})
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, json=response if response is not None else chat())
    settings = OpenAISettings(enabled=True, api_key=KEY, base_url=f"https://{HOST}", response_model="gpt-oss-120b",
                              embedding_model="E5-Mistral-7B-Instruct")
    return OpenAIProvider(settings, httpx.MockTransport(handler)), calls


def retrieved():
    return Retriever().retrieve(RetrievalRequest(query="MaxEnt background assumptions", mode="ontology", context=["ScientificMethod"]))


def test_chat_is_the_default_and_wire_format_is_strict_json_schema():
    p, calls = make()
    with p.operation():
        result = p.answer("q", retrieved())
    request, body = calls[0]
    assert request.url.path == "/v1/chat/completions" and body["model"] == "gpt-oss-120b"
    assert [m["role"] for m in body["messages"]] == ["system", "user"] and "store" not in body
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert "ev-maxent" in json.dumps(fmt["json_schema"]["schema"]["properties"]["claims"])
    assert result["status"] == "answered" and result["usage"]["completion_tokens"] == 30
    assert result["citations"][0]["evidence"]["id"] == "ev-maxent" and p.responses_verified


@pytest.mark.parametrize("response,code", [
    (chat(GOOD, finish="length"), "openai_incomplete"),
    (chat(None), "openai_incomplete"),
    (chat(GOOD, refusal="I can't help with that."), "openai_refusal"),
    (chat("not json"), "openai_invalid_answer"),
    (chat({**GOOD, "claims": [{"text": "x", "evidence_ids": ["invented-id"]}]}), "openai_invalid_answer"),
    (chat({"status": "answered", "claims": [{"statement": "own keys", "evidence": ["ev-maxent"]}], "gaps": [], "uncertainties": []}), "openai_invalid_answer"),
    ({"id": "x", "model": "m", "choices": []}, "openai_invalid_answer"),
])
def test_incomplete_refused_or_malformed_answers_fail_explicitly(response, code):
    p, _ = make(response)
    with p.operation(), pytest.raises(ProviderError) as info:
        p.answer("q", retrieved())
    assert info.value.code == code and not p.responses_verified


def test_reasoning_text_is_ignored_and_never_returned():
    p, _ = make(chat(GOOD, reasoning_content="SECRET-CHAIN-OF-THOUGHT"))
    with p.operation():
        result = p.answer("q", retrieved())
    assert "SECRET-CHAIN-OF-THOUGHT" not in json.dumps(result)


def test_e5_mistral_instruction_applies_to_queries_not_passages():
    p, calls = make()
    request = RetrievalRequest(query="How is habitat validated?", mode="ontology", context=["ScientificMethod"], backend="openai", k=2)
    with p.operation():
        Retriever().retrieve(request, p)
    corpus, query = calls[0][1]["input"], calls[1][1]["input"]
    assert not any(t.startswith("Instruct:") for t in corpus)
    assert query == ["Instruct: Given a scientific question, retrieve evidence passages that answer it\nQuery: How is habitat validated?"]


def test_other_embedding_models_get_raw_queries():
    p, calls = make()
    p.settings = OpenAISettings(enabled=True, api_key=KEY, base_url=f"https://{HOST}", embedding_model="text-embedding-3-small")
    assert p.query_text("raw") == "raw"


def test_unknown_response_api_is_rejected():
    with pytest.raises(ValueError):
        OpenAISettings(response_api="completions")
