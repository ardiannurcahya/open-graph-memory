from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from open_graph_sdk import AsyncOGMClient, ClientConfig
from open_graph_sdk.errors import AuthenticationError, ConflictError, NotFoundError


def _dataset() -> dict[str, Any]:
    return {
        "id": "ds1",
        "project_id": "proj1",
        "name": "research",
        "description": None,
        "metadata": {},
        "status": "active",
        "error_message": None,
    }


def _document() -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "id": "doc1",
        "project_id": "proj1",
        "dataset_id": "ds1",
        "filename": "note.txt",
        "mime_type": "text/plain",
        "size_bytes": 5,
        "content_hash": "hash",
        "object_key": "objects/doc1",
        "status": "indexed",
        "error_message": None,
        "duplicate": False,
        "created_at": now,
        "updated_at": now,
    }


@pytest.mark.asyncio
async def test_sdk_dataset_crud_headers() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.headers["X-API-Key"] == "ogm_test"
        assert request.headers["X-Project-Id"] == "proj1"
        if request.method == "POST":
            return httpx.Response(201, json=_dataset())
        if request.method == "GET" and request.url.path == "/v1/datasets":
            return httpx.Response(200, json=[_dataset()])
        if request.method == "GET":
            return httpx.Response(200, json=_dataset())
        if request.method == "PATCH":
            return httpx.Response(200, json={**_dataset(), "name": "renamed"})
        if request.method == "DELETE":
            return httpx.Response(204)
        raise AssertionError(request)

    client = AsyncOGMClient(
        ClientConfig("http://test", "ogm_test", "proj1"),
        transport=httpx.MockTransport(handler),
    )
    assert (await client.create_dataset("research")).id == "ds1"
    assert len(await client.list_datasets()) == 1
    assert (await client.get_dataset("ds1")).name == "research"
    assert (await client.update_dataset("ds1", name="renamed")).name == "renamed"
    await client.delete_dataset("ds1")
    await client.aclose()
    assert [req.method for req in seen] == ["POST", "GET", "GET", "PATCH", "DELETE"]


@pytest.mark.asyncio
async def test_sdk_upload_and_structured_graph() -> None:
    seen: list[httpx.Request] = []

    def entity(entity_id: str) -> dict[str, object]:
        return {
            "id": entity_id,
            "dataset_id": "ds1",
            "canonical_name": entity_id,
            "entity_type": "concept",
            "confidence": 1.0,
            "version": 1,
            "review_state": "unreviewed",
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/documents") and request.method == "POST":
            return httpx.Response(201, json=_document())
        if request.url.path.endswith("/entities/search"):
            return httpx.Response(200, json=[entity("alpha")])
        if request.url.path.endswith("/path"):
            return httpx.Response(
                200,
                json={
                    "dataset_id": "ds1",
                    "source_entity_id": "alpha",
                    "target_entity_id": "beta",
                    "found": True,
                    "hops": 1,
                    "nodes": [entity("alpha"), entity("beta")],
                    "relations": [],
                },
            )
        if request.url.path.endswith("/subgraph"):
            return httpx.Response(
                200,
                json={
                    "dataset_id": "ds1",
                    "root_entity_id": "alpha",
                    "depth": 2,
                    "nodes": [entity("alpha")],
                    "relations": [],
                },
            )
        raise AssertionError(request.url.path)

    client = AsyncOGMClient(
        ClientConfig("http://test", "ogm_test", "proj1"),
        transport=httpx.MockTransport(handler),
    )
    document = await client.upload_document(
        "ds1",
        filename="note.txt",
        content=b"hello",
        content_type="text/plain",
    )
    assert document.id == "doc1"
    search = await client.search_graph("ds1", "alpha", entity_type="concept", limit=3)
    path = await client.find_graph_path("ds1", "alpha", "beta", max_depth=2, relation_limit=20)
    subgraph = await client.get_subgraph("ds1", "alpha", depth=2, node_limit=20, relation_limit=30)
    await client.aclose()

    assert search[0].id == "alpha"
    assert path.found
    assert path.hops == 1
    assert subgraph.root_entity_id == "alpha"
    assert [request.url.path for request in seen] == [
        "/v1/datasets/ds1/documents",
        "/v1/datasets/ds1/entities/search",
        "/v1/datasets/ds1/graph/path",
        "/v1/datasets/ds1/graph/subgraph",
    ]
    assert [dict(request.url.params) for request in seen[1:]] == [
        {"q": "alpha", "limit": "3", "entity_type": "concept"},
        {
            "source_entity_id": "alpha",
            "target_entity_id": "beta",
            "max_depth": "2",
            "relation_limit": "20",
        },
        {"entity_id": "alpha", "depth": "2", "node_limit": "20", "relation_limit": "30"},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "exc"),
    [(401, AuthenticationError), (404, NotFoundError), (409, ConflictError)],
)
async def test_sdk_maps_http_errors(status: int, exc: type[Exception]) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "boom"})

    client = AsyncOGMClient(
        ClientConfig("http://test", "bad", "proj1"),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(exc):
        await client.list_datasets()
    await client.aclose()


@pytest.mark.asyncio
async def test_sdk_project_admin_header() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-API-Key"] == "admin-secret"
        assert "X-Project-Id" not in request.headers
        return httpx.Response(201, json={"id": "proj1", "name": "demo", "api_key": "ogm_created"})

    client = AsyncOGMClient(
        ClientConfig("http://test", "project-key", "proj1", admin_key="admin-secret"),
        transport=httpx.MockTransport(handler),
    )
    project = await client.create_project("demo")
    assert project.api_key == "ogm_created"
    await client.aclose()


@pytest.mark.asyncio
async def test_sdk_agent_memory_methods() -> None:
    seen: list[httpx.Request] = []
    episode = {
        "id": "ame1",
        "project_id": "proj1",
        "domain": "engineering",
        "title": "Remember",
        "goal": "ship",
        "problem_signature": "deploy failure",
        "scope": {},
        "tags": [],
        "metadata": {},
        "status": "active",
        "feedback_score": 0,
        "superseded_by_id": None,
        "attempts": [],
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/outcomes"):
            return httpx.Response(
                201,
                json={
                    "id": "amo1",
                    "status": "success",
                    "pattern": {
                        "pattern_key": "retry",
                        "verified_outcomes": 3,
                        "weighted_successes": 3.0,
                        "weighted_total": 3.0,
                        "confidence": 1.0,
                        "promoted": True,
                    },
                },
            )
        if request.url.path.endswith("/attempts"):
            return httpx.Response(
                201,
                json={
                    "id": "ama1",
                    "sequence": 1,
                    "hypothesis": "try",
                    "actions": [],
                    "result": "success",
                    "notes": None,
                    "metadata": {},
                },
            )
        if request.url.path.endswith("/search") or request.method == "GET":
            return httpx.Response(200, json={"query": "remember", "results": []})
        return httpx.Response(201 if request.method == "POST" else 200, json=episode)

    client = AsyncOGMClient(
        ClientConfig("http://test", "ogm_test", "proj1"), transport=httpx.MockTransport(handler)
    )
    assert (
        await client.create_agent_memory_episode(
            "engineering", "Remember", "ship", "deploy failure"
        )
    ).id == "ame1"
    assert (await client.append_agent_memory_attempt("ame1", "try", [], "success")).sequence == 1
    assert (
        await client.record_agent_memory_outcome(
            "ame1", "success", "done", verifiers=[{"kind": "ci", "name": "ci", "status": "passed"}]
        )
    ).pattern.promoted
    assert (await client.search_agent_memory("remember")).query == "remember"
    assert [request.url.path for request in seen] == [
        "/v1/agent-memory/episodes",
        "/v1/agent-memory/episodes/ame1/attempts",
        "/v1/agent-memory/episodes/ame1/outcomes",
        "/v1/agent-memory/search",
    ]
    await client.aclose()
