"""Render a KAG client config from KAG's own example template plus our settings.

All LLM and embedding traffic is pointed at the local rate-limiting gateway with a throwaway token,
so the KAG process never holds the upstream key. The template comes from the pinned KAG checkout,
so nothing about KAG's large solver configuration is copied into this repository.
"""
import copy
import csv
import re
from urllib.parse import urlsplit
import yaml
from .settings import LOOPBACK_HOSTS, MODEL_PATTERN, normalize_base_url

NAMESPACE = re.compile(r"[A-Z][A-Za-z0-9]{0,15}")  # KAG requires this for project namespaces
CSV_COLUMNS = ("idx", "title", "text")


def render_kag_config(template, *, gateway_url, gateway_token, openie_model, chat_model, embedding_model,
                      vector_dimensions, namespace, host_addr="http://127.0.0.1:8887"):
    """Return a new config dict. Raises ValueError for anything that could bypass the gateway."""
    endpoint = normalize_base_url(gateway_url)
    if urlsplit(endpoint).hostname not in LOOPBACK_HOSTS:
        raise ValueError("KAG must talk to the loopback gateway, not an upstream endpoint")
    if len(gateway_token) < 16 or any(c.isspace() for c in gateway_token):
        raise ValueError("A gateway token of at least 16 characters is required")
    for model in (openie_model, chat_model, embedding_model):
        if not re.fullmatch(MODEL_PATTERN, model):
            raise ValueError("Invalid model identifier")
    if not NAMESPACE.fullmatch(namespace):
        raise ValueError("KAG namespace must match [A-Z][A-Za-z0-9]{0,15}")
    if not 1 <= int(vector_dimensions) <= 4096:
        raise ValueError("vector_dimensions must be between 1 and 4096 (the Neo4j vector index limit)")
    if urlsplit(host_addr).hostname not in LOOPBACK_HOSTS:
        raise ValueError("The OpenSPG server address must be loopback")
    config = copy.deepcopy(template)
    for name, model in (("openie_llm", openie_model), ("chat_llm", chat_model)):
        config[name].clear()
        config[name].update(type="maas", base_url=endpoint, api_key=gateway_token, model=model, enable_check=False)
    config["vectorize_model"].clear()
    config["vectorize_model"].update(type="openai", base_url=endpoint, api_key=gateway_token, model=embedding_model,
                                     vector_dimensions=int(vector_dimensions), enable_check=False)
    config["project"].update(namespace=namespace, host_addr=host_addr, language="en", biz_scene="default")
    pipeline = config["kag_builder_pipeline"]
    pipeline["scanner"] = {"type": "csv_scanner"}
    pipeline["chain"]["reader"] = {"type": "dict_reader", "id_col": "idx", "name_col": "title", "content_col": "text"}
    pipeline["num_chains"] = 1  # concurrency stays low: the shared endpoint allows 100 calls/minute in total
    pipeline["num_threads_per_chain"] = 1
    return config


def dump_config(config):
    return yaml.safe_dump(config, sort_keys=False, default_flow_style=False, allow_unicode=True)


def evidence_rows(corpus):
    """Reviewed evidence only: candidate assertions never enter the knowledge graph."""
    sources = {s["id"]: s for s in corpus["sources"]}
    return [{"idx": e["id"], "title": sources[e["source_id"]]["title"], "text": e["passage"]}
            for e in corpus["evidence"] if e["review_status"] == "reviewed"]


def write_evidence_csv(rows, handle):
    writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)


def find_base_urls(node):
    """Every base_url value anywhere in a config tree (the template has many nested model blocks)."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "base_url":
                yield value
            else:
                yield from find_base_urls(value)
    elif isinstance(node, list):
        for item in node:
            yield from find_base_urls(item)
