"""Domain selection. A domain is a directory under domains/ with a domain.json manifest plus corpus,
pathway, catalog and crosswalk files. Domains are discovered, not listed in code.

The domain is chosen once at server start (DSS_DOMAIN) or via the CLI, never from request input.
"""
import os
import re
from .resources import read_json, resource_dir

DEFAULT_DOMAIN = "vector-borne-disease"
REQUIRED_FILES = ("domain.json", "corpus.json", "catalog.json", "pathway.json", "crosswalk.json")


def available_domains():
    base = resource_dir("domains")
    return sorted(d.name for d in base.iterdir()
                  if d.is_dir() and all(d.joinpath(f).is_file() for f in REQUIRED_FILES))


def domain_name(value=None):
    name = (value or os.environ.get("DSS_DOMAIN", "") or DEFAULT_DOMAIN).strip()
    # The pattern check stops path tricks before the name is used to build a resource path.
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,59}", name) or name not in available_domains():
        raise ValueError(f"Unknown domain; choose one of {available_domains()}")
    return name


def load(domain, filename):
    return read_json(f"domains/{domain_name(domain)}/{filename}")


def benchmark_cases(domain):
    return read_json(f"benchmarks/{load(domain, 'domain.json')['benchmark']}.json")["cases"]
