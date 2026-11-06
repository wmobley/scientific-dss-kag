"""Policy: all runtime LLM traffic uses the OpenAI-compatible protocol via one audited path."""
from pathlib import Path
from scientific_dss_kag.policy import check_policy

ROOT = Path(__file__).resolve().parents[1]


def tree(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def test_repository_complies_with_policy():
    result = check_policy(ROOT)
    assert result["ok"], result["violations"]


def test_clean_tree_passes(tmp_path):
    assert check_policy(tree(tmp_path, {"src/pkg/a.py": "import json\n", ".env.example": "DSS_OPENAI_ENABLED=false\n"}))["ok"]


def test_detects_provider_sdk_imports(tmp_path):
    root = tree(tmp_path, {"src/pkg/a.py": "import anthropic\nfrom cohere import Client\nimport langchain_openai\nfrom openai import OpenAI\n"})
    result = check_policy(root)
    assert not result["ok"] and len(result["violations"]) == 4


def test_detects_unaudited_network_clients_and_hosts(tmp_path):
    root = tree(tmp_path, {"src/pkg/rogue.py": "import httpx\nc = httpx.Client()\nURL='https://api.anthropic.com/v1'\n",
                           "src/pkg/gateway.py": "import httpx\nc = httpx.AsyncClient()\n"})
    violations = check_policy(root)["violations"]
    assert any("rogue.py" in v and "network" in v for v in violations)
    assert any("api.anthropic.com" in v for v in violations)
    assert not any("gateway.py" in v for v in violations)


def test_prose_mentioning_requests_is_not_a_network_client(tmp_path):
    root = tree(tmp_path, {"src/pkg/a.py": "# never accept paths from API requests.\nrequests_total = 1\n"})
    assert check_policy(root)["ok"]
    for code in ("import requests\n", "import aiohttp\n", "x = requests.get('u')\n", "import urllib.request\n"):
        assert not check_policy(tree(tmp_path / code[:6].strip(), {"src/pkg/a.py": code}))["ok"]


def test_detects_other_provider_config_and_bad_endpoints(tmp_path):
    root = tree(tmp_path, {".env.example": "ANTHROPIC_API_KEY=\nOPENAI_BASE_URL=https://evil.example.com/v1\n",
                           "compose.yaml": "    environment:\n      GROQ_API_KEY: ${GROQ_API_KEY:-}\n"})
    violations = check_policy(root)["violations"]
    assert any("ANTHROPIC_API_KEY" in v for v in violations)
    assert any("evil.example.com" in v for v in violations)
    assert any("GROQ_API_KEY" in v for v in violations)


def test_allows_configured_endpoints_and_warns_on_langsmith_without_leaking_values(tmp_path):
    root = tree(tmp_path, {".env": "OPENAI_BASE_URL=https://ai.tejas.tacc.utexas.edu\nOPENAI_API_KEY=super-secret-value\nLANGSMITH_TRACING=true\n"})
    result = check_policy(root)
    assert result["ok"] and any("LANGSMITH" in w for w in result["warnings"])
    assert "super-secret-value" not in str(result)
