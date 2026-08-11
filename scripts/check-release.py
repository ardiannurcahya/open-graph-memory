#!/usr/bin/env python3
"""Validate release versions and first-party image tag policy."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.2.0"
TAG = f"v{VERSION}"

errors: list[str] = []

for relative in (
    "pyproject.toml",
    "packages/contracts/pyproject.toml",
    "packages/sdk/pyproject.toml",
):
    data = tomllib.loads((ROOT / relative).read_text(encoding="utf-8"))
    actual = data["project"]["version"]
    if actual != VERSION:
        errors.append(f"{relative}: expected {VERSION}, found {actual}")

package = json.loads((ROOT / "apps/web/package.json").read_text(encoding="utf-8"))
lock = json.loads((ROOT / "apps/web/package-lock.json").read_text(encoding="utf-8"))
if package["version"] != VERSION:
    errors.append(f"apps/web/package.json: expected {VERSION}, found {package['version']}")
if lock["version"] != VERSION or lock["packages"][""]["version"] != VERSION:
    errors.append("apps/web/package-lock.json: root version does not match release")

for relative in (
    ".env.example",
    "deployments/docker-compose.ghcr-external.yml",
    "deployments/docker-compose.yml",
    "deployments/docker-compose.prod.yml",
):
    text = (ROOT / relative).read_text(encoding="utf-8")
    if re.search(r"(?:open-graph-memory|opengraphrag)-(?:api|worker|web):latest", text):
        errors.append(f"{relative}: mutable first-party latest image is forbidden")

external = (ROOT / "deployments/docker-compose.ghcr-external.yml").read_text(encoding="utf-8")
if f"${{IMAGE_TAG:-{TAG}}}" not in external:
    errors.append(f"external compose must default IMAGE_TAG to {TAG}")
if f"IMAGE_TAG={TAG}" not in (ROOT / ".env.example").read_text(encoding="utf-8"):
    errors.append(f".env.example must default IMAGE_TAG to {TAG}")

workflow = (ROOT / ".github/workflows/ghcr.yml").read_text(encoding="utf-8")
for forbidden in ("branches: [main]", "type=ref,event=branch", "value=latest"):
    if forbidden in workflow:
        errors.append(f"GHCR workflow contains forbidden mutable release rule: {forbidden}")
if 'tags: ["v*"]' not in workflow or "type=ref,event=tag" not in workflow:
    errors.append("GHCR workflow must publish v* tags")

readme = (ROOT / "README.md").read_text(encoding="utf-8")
if '"ogm-mcp-skills==0.1.8"' not in readme and '"ogm-agent-bridge==0.1.7"' not in readme:
    errors.append("README must pin the compatible bridge release")

if errors:
    print("\n".join(f"ERROR: {item}" for item in errors), file=sys.stderr)
    raise SystemExit(1)
print(f"release metadata ok: {TAG}, versioned first-party images, bridge 0.1.8")
