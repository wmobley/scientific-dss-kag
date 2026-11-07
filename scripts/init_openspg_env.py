#!/usr/bin/env python3
"""Create .env.openspg with random local passwords (mode 0600). Never overwrites an existing file."""
import os
import secrets
import sys
from pathlib import Path

path = Path(".env.openspg")
if path.exists():
    sys.exit(f"{path} already exists; leaving it unchanged.")
names = ("OPENSPG_MYSQL_PASSWORD", "OPENSPG_NEO4J_PASSWORD", "OPENSPG_JASYPT_PASSWORD", "DSS_GATEWAY_TOKEN")
lines = ["# Generated local passwords for compose.openspg.yaml. Git-ignored. Never commit.",
         *(f"{name}={secrets.token_hex(16)}" for name in names)]
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w") as handle:
    handle.write("\n".join(lines) + "\n")
print(f"Wrote {path} (values not shown).")
