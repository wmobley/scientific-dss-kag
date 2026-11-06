"""Fixture discovery plus an explicitly configured read-only catalog client.

No production URL or token is supplied by the application. The SVO workflow
adapter is not treated as a general ontology lookup service.
"""
from urllib.parse import urlparse
import httpx
from .domain import DEFAULT_DOMAIN, domain_name, load
SVO_PREFIX = "http://www.geoscienceontology.org/svo/svl/variable#"
CATALOG_KINDS = {"models", "standardvariables"}


def first_text(value):
    """The catalog returns most text fields as lists; take the first string."""
    if isinstance(value, list):
        value = value[0] if value else ""
    return value if isinstance(value, str) else ""


def flatten(value):
    if isinstance(value, list):
        for item in value:
            yield from flatten(item)
    elif isinstance(value, str):
        yield value


def normalize_record(record, kind):
    """Reduce a raw catalog record to stable fields. Variables keep SVO sameAs URIs separately."""
    out = {"id": record["id"], "label": first_text(record.get("label")), "description": first_text(record.get("description"))}
    if kind == "standardvariables":
        same_as = list(flatten(record.get("sameAs", [])))
        out["svo_uris"] = [u for u in same_as if u.startswith(SVO_PREFIX)]
        out["other_same_as"] = [u for u in same_as if not u.startswith(SVO_PREFIX)]
    return out


def fixture_catalog(domain=DEFAULT_DOMAIN):
    return load(domain_name(domain), "catalog.json")


def integration_status():
    return {"catalog": {"state": "dev_catalog_read_contract_verified", "live_verified": True, "verified_on": "2026-11-06",
                        "scope": "anonymous GET /models and /standardvariables on the dev catalog; production host, auth and writes are not verified"},
            "svo": {"state": "crosswalk_candidates_unreviewed", "live_verified": False,
                    "note": "SVO URIs come from the catalog's sameAs links; nothing is aligned until a human accepts a crosswalk entry"},
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

    def list_all(self, kind: str, per_page: int = 100, max_pages: int = 20, max_records: int = 5000):
        """Read every page with GET only. Fails loudly if paging does not advance or bounds are exceeded."""
        if kind not in CATALOG_KINDS:
            raise ValueError("unsupported read-only resource kind")
        records, seen = [], set()
        for page in range(1, max_pages + 1):
            response = self.client.get(kind, params={"page": page, "per_page": per_page})
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list) or any(not isinstance(v, dict) or not isinstance(v.get("id"), str) for v in data):
                raise ValueError("catalog response must be an array of objects with string IDs")
            if not data:
                break
            fresh = [v for v in data if v["id"] not in seen]
            if not fresh:
                raise ValueError("catalog paging did not advance")
            seen.update(v["id"] for v in fresh)
            records.extend(fresh)
            if len(records) > max_records:
                raise ValueError("catalog exceeds the configured record bound")
            if len(data) < per_page:
                break
        else:
            raise ValueError("catalog exceeds the configured page bound")
        return {"origin": "configured_catalog", "kind": kind, "records": records,
                "normalized": {r["id"]: normalize_record(r, kind) for r in records}}

    def close(self):
        self.client.close()
