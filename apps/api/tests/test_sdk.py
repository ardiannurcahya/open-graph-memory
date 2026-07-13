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
async def test_sdk_upload_query_and_graph() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/documents") and request.method == "POST":
            return httpx.Response(201, json=_document())
        if request.url.path == "/v1/query":
            return httpx.Response(
                200,
                json={
                    "answer": "Answer",
                    "citations": [
                        {
                            "index": 1,
                            "chunk_id": "c1",
                            "document_id": "doc1",
                            "score": 1.0,
                            "text": "quote",
                        }
                    ],
                    "retrieval_trace": {"trace_id": "tr1", "mode": "hybrid", "latency_ms": 12.0},
                    "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
                },
            )
        if request.url.path == "/v1/datasets/ds1/graph":
            return httpx.Response(
                200,
                json={
                    "dataset_id": "ds1",
                    "entity_count": 0,
                    "relation_count": 0,
                    "nodes": [],
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
    result = await client.query(dataset_id="ds1", query="What?", mode="hybrid", top_k=3)
    assert result.answer == "Answer"
    assert result.citations[0].chunk_id == "c1"
    assert (await client.get_graph("ds1")).dataset_id == "ds1"
    await client.aclose()


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
