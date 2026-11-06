"""Static LLM policy check: all runtime LLM traffic uses the OpenAI-compatible protocol through
one audited path against one allowlisted endpoint. Reports hosts and names, never secret values."""
from pathlib import Path
import re
from urllib.parse import urlsplit
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


def check_policy(root="."):
    root = Path(root)
    violations, warnings = [], []
    check_source(root, violations)
    check_config(root, violations, warnings)
    return {"policy": "openai-compatible-single-endpoint", "ok": not violations,
            "violations": violations, "warnings": warnings, "allowed_hosts": sorted(ALLOWED_LLM_HOSTS)}
