from __future__ import annotations

from types import TracebackType
from typing import Any, Self

import httpx

from open_graph_sdk.config import ClientConfig
from open_graph_sdk.errors import TransportError, raise_for_response
from open_graph_sdk.models import (
    Dataset,
    DatasetCreate,
    DatasetUpdate,
    Document,
    Entity,
    Evidence,
    GraphJob,
    GraphRun,
    GraphSummary,
    MemoryAgent,
    MemoryFact,
    MemoryMessageBatch,
    MemorySearchHit,
    MemorySession,
    MemoryUser,
    Neighbor,
    ProjectCreated,
    QueryRequest,
    QueryResponse,
    Relation,
)


class AsyncOGMClient:
    def __init__(
        self,
        config: ClientConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self._client = httpx.AsyncClient(
            base_url=config.base_url.rstrip("/"),
            timeout=config.timeout,
            transport=transport,
        )

    @classmethod
    def from_env(cls) -> AsyncOGMClient:
        return cls(ClientConfig.from_env())

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self, *, admin: bool = False) -> dict[str, str]:
        api_key = self.config.admin_key if admin and self.config.admin_key else self.config.api_key
        headers = {"X-API-Key": api_key}
        if not admin:
            if self.config.project_id is None:
                raise ValueError("project_id is required for project-scoped calls")
            headers["X-Project-Id"] = self.config.project_id
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        admin: bool = False,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> Any:
        try:
            response = await self._client.request(
                method,
                path,
                headers=self._headers(admin=admin),
                json=json,
                params=params,
                files=files,
            )
        except httpx.HTTPError as exc:
            raise TransportError(str(exc)) from exc
        raise_for_response(response)
        if response.status_code == 204:
            return None
        return response.json()

    async def health(self) -> dict[str, Any]:
        response = await self._client.get("/health")
        raise_for_response(response)
        return dict(response.json())

    async def ready(self) -> dict[str, Any]:
        response = await self._client.get("/ready")
        raise_for_response(response)
        return dict(response.json())

    async def create_project(self, name: str) -> ProjectCreated:
        data = await self._request("POST", "/v1/projects", admin=True, json={"name": name})
        return ProjectCreated.model_validate(data)

    async def create_dataset(
        self,
        name: str,
        *,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Dataset:
        body = DatasetCreate(
            name=name,
            description=description,
            metadata=metadata or {},
        ).model_dump(mode="json")
        data = await self._request("POST", "/v1/datasets", json=body)
        return Dataset.model_validate(data)

    async def list_datasets(self) -> list[Dataset]:
        data = await self._request("GET", "/v1/datasets")
        return [Dataset.model_validate(item) for item in data]

    async def get_dataset(self, dataset_id: str) -> Dataset:
        data = await self._request("GET", f"/v1/datasets/{dataset_id}")
        return Dataset.model_validate(data)

    async def update_dataset(
        self,
        dataset_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Dataset:
        body = DatasetUpdate(name=name, description=description, metadata=metadata).model_dump(
            mode="json", exclude_none=True
        )
        data = await self._request("PATCH", f"/v1/datasets/{dataset_id}", json=body)
        return Dataset.model_validate(data)

    async def delete_dataset(self, dataset_id: str) -> None:
        await self._request("DELETE", f"/v1/datasets/{dataset_id}")

    async def upload_document(
        self,
        dataset_id: str,
        *,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> Document:
        data = await self._request(
            "POST",
            f"/v1/datasets/{dataset_id}/documents",
            files={"file": (filename, content, content_type)},
        )
        return Document.model_validate(data)

    async def list_documents(self, dataset_id: str) -> list[Document]:
        data = await self._request("GET", f"/v1/datasets/{dataset_id}/documents")
        return [Document.model_validate(item) for item in data]

    async def get_document(self, dataset_id: str, document_id: str) -> Document:
        data = await self._request("GET", f"/v1/datasets/{dataset_id}/documents/{document_id}")
        return Document.model_validate(data)

    async def get_document_by_id(self, document_id: str) -> Document:
        data = await self._request("GET", f"/v1/documents/{document_id}")
        return Document.model_validate(data)

    async def delete_document(self, document_id: str) -> None:
        await self._request("DELETE", f"/v1/documents/{document_id}")

    async def query(
        self,
        *,
        dataset_id: str,
        query: str,
        mode: str = "vector_only",
        top_k: int = 5,
        graph_depth: int | None = None,
        graph_fanout: int | None = None,
        graph_timeout_ms: int | None = None,
        fusion: str | None = None,
        memory_user_id: str | None = None,
        memory_agent_id: str | None = None,
        memory_session_id: str | None = None,
        memory_top_k: int = 0,
    ) -> QueryResponse:
        body = QueryRequest(
            dataset_id=dataset_id,
            query=query,
            mode=mode,  # type: ignore[arg-type]
            top_k=top_k,
            graph_depth=graph_depth,
            graph_fanout=graph_fanout,
            graph_timeout_ms=graph_timeout_ms,
            fusion=fusion,  # type: ignore[arg-type]
            memory_user_id=memory_user_id,
            memory_agent_id=memory_agent_id,
            memory_session_id=memory_session_id,
            memory_top_k=memory_top_k,
        ).model_dump(mode="json", exclude_none=True)
        data = await self._request("POST", "/v1/query", json=body)
        return QueryResponse.model_validate(data)

    async def create_memory_user(
        self,
        external_id: str,
        *,
        display_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryUser:
        data = await self._request(
            "POST",
            "/v1/memory/users",
            json={
                "external_id": external_id,
                "display_name": display_name,
                "metadata": metadata or {},
            },
        )
        return MemoryUser.model_validate(data)

    async def create_memory_agent(
        self,
        name: str,
        *,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryAgent:
        data = await self._request(
            "POST",
            "/v1/memory/agents",
            json={"name": name, "description": description, "metadata": metadata or {}},
        )
        return MemoryAgent.model_validate(data)

    async def create_memory_session(
        self,
        *,
        user_id: str,
        agent_id: str,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemorySession:
        data = await self._request(
            "POST",
            "/v1/memory/sessions",
            json={
                "user_id": user_id,
                "agent_id": agent_id,
                "title": title,
                "metadata": metadata or {},
            },
        )
        return MemorySession.model_validate(data)

    async def add_memory_messages(
        self,
        session_id: str,
        *,
        messages: list[dict[str, Any]],
        facts: list[dict[str, Any]] | None = None,
    ) -> MemoryMessageBatch:
        data = await self._request(
            "POST",
            f"/v1/memory/sessions/{session_id}/messages",
            json={"messages": messages, "facts": facts or []},
        )
        return MemoryMessageBatch.model_validate(data)

    async def get_session_memory(self, session_id: str) -> list[MemoryFact]:
        data = await self._request("GET", f"/v1/memory/sessions/{session_id}/memory")
        return [MemoryFact.model_validate(item) for item in data]

    async def get_user_memory_context(self, user_id: str, *, limit: int = 20) -> list[MemoryFact]:
        data = await self._request(
            "GET", f"/v1/memory/users/{user_id}/context", params={"limit": limit}
        )
        return [MemoryFact.model_validate(item) for item in data]

    async def search_memory(
        self,
        query: str,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        scopes: list[str] | None = None,
        limit: int = 10,
        include_superseded: bool = False,
    ) -> list[MemorySearchHit]:
        data = await self._request(
            "POST",
            "/v1/memory/search",
            json={
                "query": query,
                "user_id": user_id,
                "agent_id": agent_id,
                "session_id": session_id,
                "scopes": scopes or ["user", "agent", "session"],
                "limit": limit,
                "include_superseded": include_superseded,
            },
        )
        return [MemorySearchHit.model_validate(item) for item in data]

    async def delete_memory(self, memory_id: str) -> None:
        await self._request("DELETE", f"/v1/memory/{memory_id}")

    async def get_entity(self, entity_id: str) -> Entity:
        data = await self._request("GET", f"/v1/entities/{entity_id}")
        return Entity.model_validate(data)

    async def get_neighbors(self, entity_id: str, *, limit: int = 25) -> list[Neighbor]:
        data = await self._request(
            "GET",
            f"/v1/entities/{entity_id}/neighbors",
            params={"limit": limit},
        )
        return [Neighbor.model_validate(item) for item in data]

    async def get_graph(self, dataset_id: str, *, limit: int = 100, depth: int = 1) -> GraphSummary:
        data = await self._request(
            "GET", f"/v1/datasets/{dataset_id}/graph", params={"limit": limit, "depth": depth}
        )
        return GraphSummary.model_validate(data)

    async def get_evidence(self, evidence_id: str) -> Evidence:
        data = await self._request("GET", f"/v1/evidence/{evidence_id}")
        return Evidence.model_validate(data)

    async def get_graph_run(self, run_id: str) -> GraphRun:
        data = await self._request("GET", f"/v1/graph-runs/{run_id}")
        return GraphRun.model_validate(data)

    async def get_graph_job(self, job_id: str) -> GraphJob:
        data = await self._request("GET", f"/v1/graph-jobs/{job_id}")
        return GraphJob.model_validate(data)

    async def review_relation(self, relation_id: str, review_state: str) -> Relation:
        data = await self._request(
            "PATCH", f"/v1/relations/{relation_id}/review", json={"review_state": review_state}
        )
        return Relation.model_validate(data)
