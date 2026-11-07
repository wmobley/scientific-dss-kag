import csv
import io
from pathlib import Path
import pytest
import yaml
from scientific_dss_kag.domain import load
from scientific_dss_kag.kag_config import dump_config, evidence_rows, find_base_urls, render_kag_config, write_evidence_csv

GATEWAY = "http://127.0.0.1:8092/v1"
TOKEN = "gateway-token-0123456789abcdef"
UPSTREAM = "https://ai.tejas.tacc.utexas.edu/v1"
REAL_TEMPLATE = Path(__file__).resolve().parents[1] / "work/kag/KAG/kag/examples/example_config.yaml"

TEMPLATE = yaml.safe_load("""
openie_llm: &openie_llm {type: maas, base_url: https://dashscope.example/v1, api_key: key, model: a, enable_check: false}
chat_llm: &chat_llm {type: maas, base_url: https://dashscope.example/v1, api_key: key, model: b, enable_check: false}
vectorize_model: &vec {type: openai, base_url: https://siliconflow.example/v1, api_key: key, model: c, vector_dimensions: 1024}
vectorizer: *vec
project: {biz_scene: x, host_addr: 'http://example.com', id: '1', language: zh, namespace: Old}
kag_builder_pipeline:
  chain: {type: unstructured_builder_chain, extractor: {llm: *openie_llm}, reader: {type: dict_reader}}
  num_chains: 16
  num_threads_per_chain: 4
  scanner: {type: hotpotqa_dataset_scanner}
kag_solver_pipeline: {planner: {llm: *chat_llm}, retriever: {vectorize_model: *vec}}
""")


def render(**overrides):
    values = dict(gateway_url=GATEWAY, gateway_token=TOKEN, openie_model="Qwen3-235B-A22B-Instruct-2507",
                  chat_model="gpt-oss-120b", embedding_model="E5-Mistral-7B-Instruct", vector_dimensions=4096,
                  namespace="GwSubsidence")
    values.update(overrides)
    return render_kag_config(TEMPLATE, **values)


def test_every_model_block_points_at_the_gateway_with_the_throwaway_token():
    config = render()
    assert set(find_base_urls(config)) == {GATEWAY}
    for name, model in (("openie_llm", "Qwen3-235B-A22B-Instruct-2507"), ("chat_llm", "gpt-oss-120b"), ("vectorize_model", "E5-Mistral-7B-Instruct")):
        assert config[name]["base_url"] == GATEWAY and config[name]["api_key"] == TOKEN and config[name]["model"] == model
        assert config[name]["enable_check"] is False  # no surprise live calls at project creation
    assert config["vectorize_model"]["vector_dimensions"] == 4096
    # the aliased copies used by the extractor and solver follow the same blocks
    assert config["kag_builder_pipeline"]["chain"]["extractor"]["llm"]["base_url"] == GATEWAY
    assert config["kag_solver_pipeline"]["retriever"]["vectorize_model"]["model"] == "E5-Mistral-7B-Instruct"
    assert "dashscope" not in dump_config(config) and "siliconflow" not in dump_config(config)


def test_template_is_not_mutated_and_dump_round_trips():
    before = dump_config(TEMPLATE)
    config = render()
    assert dump_config(TEMPLATE) == before
    assert yaml.safe_load(dump_config(config)) == config


def test_builder_uses_csv_columns_and_low_concurrency():
    pipeline = render()["kag_builder_pipeline"]
    assert pipeline["scanner"] == {"type": "csv_scanner"}
    assert pipeline["chain"]["reader"] == {"type": "dict_reader", "id_col": "idx", "name_col": "title", "content_col": "text"}
    assert (pipeline["num_chains"], pipeline["num_threads_per_chain"]) == (1, 1)
    assert render()["project"]["namespace"] == "GwSubsidence" and render()["project"]["language"] == "en"


@pytest.mark.parametrize("bad", [
    dict(gateway_url=UPSTREAM),                        # upstream endpoint bypasses the gateway
    dict(gateway_url="https://api.openai.com/v1"),
    dict(gateway_url="http://evil.example.com/v1"),
    dict(gateway_token="short"), dict(gateway_token=""), dict(gateway_token="has space in the token 123456"),
    dict(namespace="lowercase"), dict(namespace="Has_Underscore"), dict(namespace="A" * 17), dict(namespace=""),
    dict(vector_dimensions=0), dict(vector_dimensions=4097),
    dict(host_addr="http://example.com:8887"),
    dict(chat_model="bad model!"), dict(openie_model=""),
])
def test_unsafe_inputs_are_rejected(bad):
    with pytest.raises(ValueError):
        render(**bad)


def test_only_reviewed_evidence_is_exported_and_csv_round_trips_awkward_text():
    rows = evidence_rows(load("groundwater-subsidence", "corpus.json"))
    ids = [r["idx"] for r in rows]
    assert "ev-gw-candidate" not in ids and {"ev-gw-drawdown", "ev-gw-modflow", "ev-gw-observations", "ev-gw-decision"} == set(ids)
    awkward = [{"idx": "ev-x", "title": 'Quote " and, comma', "text": "line one\nline two, with \"quotes\""}]
    buffer = io.StringIO()
    write_evidence_csv(awkward, buffer)
    assert list(csv.DictReader(io.StringIO(buffer.getvalue()))) == awkward


@pytest.mark.skipif(not REAL_TEMPLATE.is_file(), reason="pinned KAG checkout not present")
def test_real_kag_template_has_no_remaining_foreign_endpoint():
    config = render_kag_config(yaml.safe_load(REAL_TEMPLATE.read_text()), gateway_url=GATEWAY, gateway_token=TOKEN,
                               openie_model="a", chat_model="b", embedding_model="c", vector_dimensions=4096, namespace="GwSubsidence")
    urls = set(find_base_urls(config))
    assert urls == {GATEWAY}, urls
    text = dump_config(config)
    assert "dashscope" not in text and "siliconflow" not in text and "aliyun" not in text.lower()
