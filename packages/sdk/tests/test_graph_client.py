from __future__ import annotations

import httpx
import pytest
from open_graph_sdk import AsyncOGMClient, ClientConfig


def _entity(entity_id: str) -> dict[str, object]:
    return {
        "id": entity_id,
        "dataset_id": "dataset-1",
        "canonical_name": entity_id,
        "entity_type": "concept",
        "confidence": 1.0,
        "version": 1,
        "review_state": "unreviewed",
    }


@pytest.mark.asyncio
async def test_structured_graph_methods() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/entities/search"):
            return httpx.Response(
                200,
                json=[_entity("alpha")],
            )
        if request.url.path.endswith("/path"):
            return httpx.Response(
                200,
                json={
                    "dataset_id": "dataset-1",
                    "source_entity_id": "alpha",
                    "target_entity_id": "beta",
                    "found": True,
                    "hops": 0,
                    "nodes": [_entity("alpha"), _entity("beta")],
                    "relations": [],
                },
            )
        if request.url.path.endswith("/relations/relation-1/evidence"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "evidence-1",
                        "run_id": "run-1",
                        "relation_id": "relation-1",
                        "dataset_id": "dataset-1",
                        "document_id": "document-1",
                        "chunk_id": "chunk-1",
                        "quote": "alpha relates to beta",
                        "confidence": 1.0,
                    }
                ],
            )
        return httpx.Response(
            200,
            json={
                "dataset_id": "dataset-1",
                "root_entity_id": "alpha",
                "depth": 2,
                "nodes": [_entity("alpha")],
                "relations": [],
            },
        )

    client = AsyncOGMClient(
        ClientConfig("http://test", "key", "project-1"),
        transport=httpx.MockTransport(handler),
    )
    search = await client.search_graph("dataset-1", "alpha", limit=3)
    path = await client.find_graph_path(
        "dataset-1", "alpha", "beta", max_depth=2, relation_limit=20
    )
    subgraph = await client.get_subgraph(
        "dataset-1", "alpha", depth=2, node_limit=20, relation_limit=30
    )
    evidence = await client.get_relation_evidence("dataset-1", "relation-1", limit=5)
    await client.aclose()

    assert search[0].id == "alpha"
    assert path.found
    assert subgraph.nodes[0].id == "alpha"
    assert evidence[0].relation_id == "relation-1"
    assert [request.url.path for request in requests] == [
        "/v1/datasets/dataset-1/entities/search",
        "/v1/datasets/dataset-1/graph/path",
        "/v1/datasets/dataset-1/graph/subgraph",
        "/v1/datasets/dataset-1/relations/relation-1/evidence",
    ]
    assert [dict(request.url.params) for request in requests] == [
        {"q": "alpha", "limit": "3"},
        {
            "source_entity_id": "alpha",
            "target_entity_id": "beta",
            "max_depth": "2",
            "relation_limit": "20",
        },
        {"entity_id": "alpha", "depth": "2", "node_limit": "20", "relation_limit": "30"},
        {"limit": "5"},
    ]
