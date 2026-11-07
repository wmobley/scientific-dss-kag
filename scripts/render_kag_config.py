#!/usr/bin/env python3
"""Write work/kag/kag_config.yaml and work/kag/evidence.csv for a domain (files are mode 0600).

Run from the repository root:  uv run python scripts/render_kag_config.py --domain groundwater-subsidence
Needs DSS_GATEWAY_TOKEN (see .env.openspg) and the pinned KAG checkout in work/kag/KAG.
"""
import argparse
import os
import sys
from pathlib import Path
import yaml
from dotenv import load_dotenv
from scientific_dss_kag.domain import domain_name, load
from scientific_dss_kag.kag_config import dump_config, evidence_rows, render_kag_config, write_evidence_csv

parser = argparse.ArgumentParser()
parser.add_argument("--domain", default=None)
parser.add_argument("--namespace", default="GwSubsidence")
parser.add_argument("--openie-model", default="Qwen3-235B-A22B-Instruct-2507")
parser.add_argument("--chat-model", default="gpt-oss-120b")
parser.add_argument("--gateway-url", default="http://127.0.0.1:8092/v1")
parser.add_argument("--vector-dimensions", type=int, default=4096)
parser.add_argument("--out-dir", default="work/kag")
args = parser.parse_args()

load_dotenv(".env.openspg", override=False)
load_dotenv(".env", override=False)
token = os.environ.get("DSS_GATEWAY_TOKEN", "")
template_path = Path("work/kag/KAG/kag/examples/example_config.yaml")
if not template_path.is_file():
    sys.exit(f"Missing {template_path}; clone OpenSPG/KAG at tag v0.8.0 into work/kag/KAG first.")
domain = domain_name(args.domain)
config = render_kag_config(yaml.safe_load(template_path.read_text()), gateway_url=args.gateway_url, gateway_token=token,
                           openie_model=args.openie_model, chat_model=args.chat_model,
                           embedding_model=os.environ.get("OPENAI_EMBEDDING_MODEL", "E5-Mistral-7B-Instruct"),
                           vector_dimensions=args.vector_dimensions, namespace=args.namespace)
out = Path(args.out_dir)
out.mkdir(parents=True, exist_ok=True)
for name, writer in (("kag_config.yaml", lambda h: h.write(dump_config(config))),
                     ("evidence.csv", lambda h: write_evidence_csv(evidence_rows(load(domain, "corpus.json")), h))):
    descriptor = os.open(out / name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", newline="") as handle:
        writer(handle)
print(f"Wrote {out/'kag_config.yaml'} and {out/'evidence.csv'} for domain {domain} (secrets not shown).")
