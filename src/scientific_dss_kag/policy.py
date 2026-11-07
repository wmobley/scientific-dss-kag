"""Static LLM policy check: all runtime LLM traffic uses the OpenAI-compatible protocol through
one audited path against one allowlisted endpoint. Reports hosts and names, never secret values."""
from pathlib import Path
import re
from urllib.parse import urlsplit
import yaml
from .kag_config import find_base_urls
from .settings import ALLOWED_LLM_HOSTS, LOOPBACK_HOSTS

FORBIDDEN_IMPORTS = ("anthropic", "google.generativeai", "google.genai", "cohere", "mistralai", "ollama",
                     "litellm", "groq", "langchain", "together", "replicate", "openai")
FORBIDDEN_HOSTS = ("api.anthropic.com", "generativelanguage.googleapis.com", "api.cohere", "api.mistral.ai",
                   "api.groq.com", "openrouter.ai", "api.together", "bedrock-runtime", "api-inference.huggingface.co")
FORBIDDEN_ENV_NAMES = ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "COHERE_API_KEY",
                       "MISTRAL_API_KEY", "GROQ_API_KEY", "TOGETHER_API_KEY", "OPENROUTER_API_KEY")
HTTP_CLIENT = re.compile(r"(\bhttpx\.(Async)?Client\b|\bhttpx\.(get|post|put|request|stream)\(|\brequests\.(get|post|put|request|Session)\(|^\s*(import|from)\s+(requests|aiohttp|urllib\.request|http\.client)\b)", re.MULTILINE)
# Only these modules may open network connections: the LLM adapter, the LLM gateway, the (non-LLM) catalog.
HTTP_ALLOWED_MODULES = {"openai_provider.py", "gateway.py", "connectors.py"}
CONFIG_FILES = (".env.example", "compose.yaml", "compose.vector.yaml", ".env")
ENV_LINE = re.compile(r"^\s*(?:-\s*)?([A-Z][A-Z0-9_]*)\s*[=:]\s*(.*?)\s*$")


def _import_names(text):
    for line in text.splitlines():
        match = re.match(r"\s*(?:from\s+([\w.]+)\s+import|import\s+([\w., ]+))", line)
        if match:
            if match.group(1):
                yield match.group(1)
            else:
                for name in match.group(2).split(","):
                    yield name.strip().split(" as ")[0].strip()


def _forbidden_import(name):
    return any(name == bad or name.startswith(bad + ".") or name.startswith(bad + "_") for bad in FORBIDDEN_IMPORTS)


def _host_of(value):
    try:
        return urlsplit(value.strip().strip("'\"")).hostname
    except ValueError:
        return None


def check_source(root, violations):
    for path in sorted((root / "src").rglob("*.py")):
        text = path.read_text()
        rel = path.relative_to(root)
        for name in _import_names(text):
            if _forbidden_import(name):
                violations.append(f"{rel}: imports provider SDK '{name}'")
        for host in FORBIDDEN_HOSTS:
            if host in text and path.name != "policy.py":
                violations.append(f"{rel}: references non-allowed LLM host '{host}'")
        if path.name not in HTTP_ALLOWED_MODULES and path.name != "policy.py" and HTTP_CLIENT.search(text):
            violations.append(f"{rel}: opens network connections outside the audited modules")


def check_config(root, violations, warnings):
    for name in CONFIG_FILES:
        path = root / name
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            if line.lstrip().startswith("#"):
                continue
            match = ENV_LINE.match(line)
            if not match:
                continue
            key, value = match.groups()
            if key in FORBIDDEN_ENV_NAMES:
                violations.append(f"{name}: sets {key}; only the OpenAI-compatible endpoint may be configured")
            elif key in ("OPENAI_BASE_URL", "DSS_GATEWAY_URL", "DSS_UPSTREAM_BASE_URL") and value and not value.startswith("$"):
                host = _host_of(value)
                if host not in ALLOWED_LLM_HOSTS and host not in LOOPBACK_HOSTS:
                    violations.append(f"{name}: {key} host '{host}' is not allowlisted")
            elif key == "LANGSMITH_TRACING" and value.strip("'\"").lower() == "true":
                warnings.append(f"{name}: LANGSMITH_TRACING=true would send prompts to a second third party")


def _env_value(root, name):
    path = root / ".env"
    if path.is_file():
        for line in path.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip().strip("'\"")
    return ""


def check_openspg(root, violations):
    """The OpenSPG compose file and rendered KAG config must keep all LLM traffic on the gateway."""
    compose = root / "compose.openspg.yaml"
    if compose.is_file():
        services = (yaml.safe_load(compose.read_text()) or {}).get("services", {})
        for name, service in services.items():
            where = f"compose.openspg.yaml: service '{name}'"
            if "build" not in service and "@sha256:" not in service.get("image", ""):
                violations.append(f"{where}: image is not pinned by digest")
            for port in service.get("ports", []):
                if not str(port).startswith("127.0.0.1:"):
                    violations.append(f"{where}: port {port} is not bound to 127.0.0.1")
            env = service.get("environment", {})
            names = list(env) if isinstance(env, dict) else [e.split("=", 1)[0] for e in env]
            if any(n.startswith("OPENAI_") or n.endswith("_API_KEY") or n.startswith("DSS_GATEWAY") for n in names):
                violations.append(f"{where}: containers must not receive LLM settings or keys")
    config = root / "work" / "kag" / "kag_config.yaml"
    if config.is_file():
        text = config.read_text()
        for url in set(find_base_urls(yaml.safe_load(text))):
            if urlsplit(str(url)).hostname not in LOOPBACK_HOSTS:
                violations.append(f"work/kag/kag_config.yaml: base_url host '{urlsplit(str(url)).hostname}' is not the local gateway")
        upstream_key = _env_value(root, "OPENAI_API_KEY")
        if upstream_key and upstream_key in text:
            violations.append("work/kag/kag_config.yaml: contains the upstream API key; KAG must only hold the gateway token")


def check_policy(root="."):
    root = Path(root)
    violations, warnings = [], []
    check_source(root, violations)
    check_config(root, violations, warnings)
    check_openspg(root, violations)
    return {"policy": "openai-compatible-single-endpoint", "ok": not violations,
            "violations": violations, "warnings": warnings, "allowed_hosts": sorted(ALLOWED_LLM_HOSTS)}
