from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import httpx


async def main() -> None:
    credential_path = Path(
        os.environ.get("OGM_UI_PROJECT_FILE", "/opt/open-graph-memory/ui-project.json")
    )
    credentials = json.loads(credential_path.read_text(encoding="utf-8"))
    headers = {
        "X-API-Key": credentials["api_key"],
        "X-Project-Id": credentials["id"],
    }
    base_url = os.environ.get("OGM_BASE_URL", "http://127.0.0.1:3000/api")
    async with httpx.AsyncClient(base_url=base_url, timeout=120) as client:
        health = await client.get("/health")
        health.raise_for_status()
        if health.json()["status"] != "ok":
            raise RuntimeError("health check did not return ok")
        ready = await client.get("/ready")
        ready.raise_for_status()

        response = await client.post(
            "/v1/datasets",
            headers=headers,
            json={"name": "deployment-smoke", "description": None, "metadata": {}},
        )
        response.raise_for_status()
        dataset = response.json()
        try:
            response = await client.post(
                f"/v1/datasets/{dataset['id']}/documents",
                headers=headers,
                files={
                    "file": (
                        "knowledge.txt",
                        b"OpenGraphMemory stores authoritative graph records in PostgreSQL. "
                        b"OpenGraphMemory projects graph traversal data into Neo4j. "
                        b"Celery workers process documents from Tencent COS.",
                        "text/plain",
                    )
                },
            )
            response.raise_for_status()
            document = response.json()

            document_state: dict[str, object] = {}
            for _ in range(120):
                await asyncio.sleep(5)
                response = await client.get(
                    f"/v1/datasets/{dataset['id']}/documents/{document['id']}",
                    headers=headers,
                )
                response.raise_for_status()
                document_state = response.json()
                if (
                    document_state["status"] == "indexed"
                    and document_state["graph_stage"] == "complete"
                ):
                    break
                if (
                    document_state["status"] == "failed"
                    or document_state["graph_stage"] == "failed"
                ):
                    raise RuntimeError(
                        f"document failed: status={document_state['status']}, "
                        f"error={document_state['error_message']}"
                    )
            else:
                raise TimeoutError(
                    f"document timeout: status={document_state['status']}, "
                    f"graph_stage={document_state['graph_stage']}"
                )

            response = await client.get(
                f"/v1/datasets/{dataset['id']}/graph",
                headers=headers,
                params={"limit": 100, "depth": 1},
            )
            response.raise_for_status()
            graph = response.json()
            if graph["entity_count"] <= 0:
                raise RuntimeError("extraction produced no entities")
            if graph["relation_count"] <= 0:
                raise RuntimeError("extraction produced no relations")
            if not any(relation["citations"] for relation in graph["relations"]):
                raise RuntimeError("extraction produced no relation citations")
            print(
                "e2e passed",
                f"project={credentials['id']}",
                f"dataset={dataset['id']}",
                f"document={document['id']}",
                f"entities={graph['entity_count']}",
                f"relations={graph['relation_count']}",
            )
        finally:
            response = await client.delete(f"/v1/datasets/{dataset['id']}", headers=headers)
            response.raise_for_status()


if __name__ == "__main__":
    asyncio.run(main())
