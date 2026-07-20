from __future__ import annotations

import json
import os
from pathlib import Path

import httpx


def main() -> None:
    base_url = os.environ.get("OGM_BASE_URL", "http://127.0.0.1:3000/api")
    output = Path(os.environ.get("OGM_UI_PROJECT_FILE", "/opt/open-graph-memory/ui-project.json"))
    response = httpx.post(
        f"{base_url}/v1/projects",
        headers={"X-API-Key": os.environ["ADMIN_API_KEY"]},
        json={"name": "production-ui"},
        timeout=30,
    )
    response.raise_for_status()
    project = response.json()
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(project, stream)
        stream.write("\n")
    print(f"created project {project['id']} in {output}")


if __name__ == "__main__":
    main()
