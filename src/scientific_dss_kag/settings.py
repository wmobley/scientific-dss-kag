"""Server configuration; .env is local, ignored, and never served to browsers.

LLM policy: every runtime LLM/embedding call uses the OpenAI-compatible protocol against one
configured endpoint whose host is allowlisted (the API key is sent there) or a loopback gateway.
"""
from dataclasses import dataclass, field
import os
import re
from urllib.parse import urlsplit
from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://api.openai.com/v1"
ALLOWED_LLM_HOSTS = frozenset({"api.openai.com", "ai.tejas.tacc.utexas.edu"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
MODEL_PATTERN = r"[a-zA-Z0-9_.:-]{1,100}"
# DYNAMO/MINT catalog API hosts (read-only GETs). The production host is not documented; add it when verified.
ALLOWED_CATALOG_HOSTS = frozenset({"mintdevapi.pods.portals.tapis.io"})


def catalog_url_from_env():
    """DSS_CATALOG_URL, https only, host allowlisted. There is deliberately no default."""
    load_dotenv(dotenv_path=".env", override=False)
    raw = os.environ.get("DSS_CATALOG_URL", "").strip()
    if not raw:
        raise ValueError("Set DSS_CATALOG_URL to the catalog API base (for example the dev catalog /v2.0.0 URL)")
    try:
        parts = urlsplit(raw)
        host = parts.hostname
    except ValueError:
        raise ValueError("Invalid catalog URL") from None
    if parts.scheme != "https" or host not in ALLOWED_CATALOG_HOSTS or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Catalog URL must be https, without credentials, on an allowlisted catalog host")
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"


def normalize_base_url(value, *, allow_loopback=True):
    """Return a canonical endpoint URL or raise ValueError. Never echoes the input."""
    try:
        parts = urlsplit(value.strip())
        host, _ = parts.hostname, parts.port
    except ValueError:
        raise ValueError("Invalid LLM endpoint URL") from None
    if parts.username or parts.password or parts.query or parts.fragment or not host:
        raise ValueError("Invalid LLM endpoint URL")
    if parts.scheme == "https" and host in ALLOWED_LLM_HOSTS:
        pass
    elif allow_loopback and parts.scheme == "http" and host in LOOPBACK_HOSTS:
        pass
    else:
        raise ValueError("LLM endpoint host is not allowlisted")
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/') or '/v1'}"


def _validate_key(api_key):
    if len(api_key) > 1000 or any(c.isspace() for c in api_key):
        raise ValueError("Invalid API key configuration")


def _int_env(name, default, low, high):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


@dataclass(frozen=True)
class OpenAISettings:
    enabled: bool = False
    api_key: str = field(default="", repr=False)
    response_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    base_url: str = DEFAULT_BASE_URL
    response_api: str = "chat"  # "chat" (portable) or "responses"

    def __post_init__(self):
        if self.response_api not in ("chat", "responses"):
            raise ValueError("Invalid response API selection")
        for model in (self.response_model, self.embedding_model):
            if not re.fullmatch(MODEL_PATTERN, model):
                raise ValueError("Invalid server model identifier")
        _validate_key(self.api_key)
        normalize_base_url(self.base_url)

    @property
    def endpoint(self):
        return normalize_base_url(self.base_url)

    @classmethod
    def from_env(cls):
        # Does not evaluate shell expressions and never overrides process env.
        load_dotenv(dotenv_path=".env", override=False)
        gateway = os.environ.get("DSS_GATEWAY_URL", "").strip()
        if gateway:  # route through the shared rate-limiting gateway; it holds the real key
            base_url = gateway
            api_key = os.environ.get("DSS_GATEWAY_TOKEN", "").strip()
        else:
            base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or DEFAULT_BASE_URL
            api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        return cls(enabled=os.environ.get("DSS_OPENAI_ENABLED", "false").lower() == "true",
                   api_key=api_key, base_url=base_url,
                   response_api=os.environ.get("OPENAI_RESPONSE_API", "chat"),
                   response_model=os.environ.get("OPENAI_RESPONSE_MODEL", "gpt-4.1-mini"),
                   embedding_model=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"))


@dataclass(frozen=True)
class GatewaySettings:
    """Settings for the localhost LLM gateway that owns the upstream key and the shared limits."""
    upstream_base_url: str
    upstream_api_key: str = field(repr=False)
    token: str = field(repr=False)
    rate_per_minute: int = 40
    max_calls: int | None = None
    window_seconds: float = 60.0
    max_wait_seconds: float = 120.0
    max_concurrency: int = 4

    def __post_init__(self):
        normalize_base_url(self.upstream_base_url, allow_loopback=False)  # upstream must be a real endpoint
        _validate_key(self.upstream_api_key)
        if not self.upstream_api_key:
            raise ValueError("Gateway requires an upstream API key")
        if len(self.token) < 16 or any(c.isspace() for c in self.token):
            raise ValueError("Gateway requires DSS_GATEWAY_TOKEN of at least 16 characters")
        if not 1 <= self.rate_per_minute <= 100:
            raise ValueError("rate_per_minute must be between 1 and 100")
        if self.max_calls is not None and self.max_calls < 1:
            raise ValueError("max_calls must be positive")
        if self.window_seconds <= 0 or self.max_wait_seconds <= 0 or self.max_concurrency < 1:
            raise ValueError("Invalid gateway limits")

    @property
    def upstream(self):
        return normalize_base_url(self.upstream_base_url, allow_loopback=False)

    @classmethod
    def from_env(cls):
        load_dotenv(dotenv_path=".env", override=False)
        max_calls = _int_env("DSS_LLM_MAX_CALLS", 0, 0, 100000)
        return cls(upstream_base_url=os.environ.get("OPENAI_BASE_URL", "").strip() or DEFAULT_BASE_URL,
                   upstream_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
                   token=os.environ.get("DSS_GATEWAY_TOKEN", "").strip(),
                   rate_per_minute=_int_env("DSS_LLM_RATE_PER_MINUTE", 40, 1, 100),
                   max_calls=max_calls or None)
