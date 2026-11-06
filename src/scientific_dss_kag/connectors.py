"""Fixture discovery plus an explicitly configured read-only catalog client.

No production URL or token is supplied by the application. The SVO workflow
adapter is not treated as a general ontology lookup service.
"""
from urllib.parse import urlparse
import httpx
from .resources import read_json


def fixture_catalog():
    return read_json("domains/vector-borne-disease/catalog.json")


def integration_status():
    return {"catalog": {"state": "fixture_only", "live_verified": False},
            "svo": {"state": "fixture_alignment_only", "live_verified": False},
            "kag": {"state": "mapping_draft", "live_verified": False},
            "pgvector": {"state": "compose_scaffold_unused", "live_verified": False}}


class CatalogClient:
    """Operator-only Python interface, never exposed to request URL inputs."""
    def __init__(self, base_url: str, token: str | None = None, transport=None):
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("catalog base URL must be HTTPS without credentials/query/fragment")
        self.client = httpx.Client(base_url=base_url.rstrip("/")+"/", timeout=10,
                                   follow_redirects=False, transport=transport,
                                   headers={"Authorization": f"Bearer {token}"} if token else {})

    def list_resources(self, kind: str, label: str = ""):
        if kind not in {"models", "standardvariables"}:
            raise ValueError("unsupported read-only resource kind")
        if len(label) > 200:
            raise ValueError("label too long")
        response = self.client.get(kind, params={"label": label, "page": 1, "per_page": 100})
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list) or any(not isinstance(v, dict) or not isinstance(v.get("id"), str) for v in data):
            raise ValueError("catalog response must be an array of objects with string IDs")
        return {"origin": "configured_catalog", "records": data, "live_verified": False,
                "note": "Successful read does not establish scientific applicability or full integration verification."}

    def close(self):
        self.client.close()
