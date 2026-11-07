import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("kag_create_project", Path(__file__).resolve().parents[1] / "scripts/kag_create_project.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_loopback_urls_are_swapped_only_in_the_copy():
    config = {"chat_llm": {"base_url": "http://127.0.0.1:8092/v1", "model": "m"},
              "nested": {"list": [{"base_url": "http://localhost:8092/v1/"}]}, "project": {"host_addr": "http://127.0.0.1:8887"}}
    view = module.server_view(config)
    assert view["chat_llm"]["base_url"] == "http://host.docker.internal:8092/v1"
    assert view["nested"]["list"][0]["base_url"] == "http://host.docker.internal:8092/v1/"
    assert view["project"]["host_addr"] == "http://127.0.0.1:8887"  # only model endpoints change
    assert config["chat_llm"]["base_url"] == "http://127.0.0.1:8092/v1"  # the original is untouched


@pytest.mark.parametrize("bad", ["https://api.openai.com/v1", "https://ai.tejas.tacc.utexas.edu/v1", "http://evil.example.com/v1",
                                 "http://127.0.0.1.evil.com:8092/v1"])
def test_non_gateway_endpoints_are_refused(bad):
    with pytest.raises(ValueError):
        module.server_view({"chat_llm": {"base_url": bad}})


def test_shared_yaml_alias_objects_are_handled_once():
    shared = {"base_url": "http://127.0.0.1:8092/v1", "model": "m"}
    config = {"chat_llm": shared, "planner": {"llm": shared}, "executors": [{"llm": shared}]}
    view = module.server_view(config)
    assert {view["chat_llm"]["base_url"], view["planner"]["llm"]["base_url"], view["executors"][0]["llm"]["base_url"]} == {"http://host.docker.internal:8092/v1"}
    assert shared["base_url"] == "http://127.0.0.1:8092/v1"
    assert module.server_view(view) == view  # idempotent
