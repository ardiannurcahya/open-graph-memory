from __future__ import annotations

from types import TracebackType
from typing import Any, Self

import httpx

from open_graph_sdk.config import ClientConfig
from open_graph_sdk.errors import TransportError, raise_for_response
from open_graph_sdk.models import (
    AgentMemoryAttempt,
    AgentMemoryEpisode,
    AgentMemoryOutcome,
    AgentMemorySearchResponse,
    Dataset,
    DatasetCreate,
    DatasetUpdate,
    Document,
    Entity,
    Evidence,
    GraphJob,
    GraphPath,
    GraphRun,
    GraphSubgraph,
    GraphSummary,
    Neighbor,
    ProjectCreated,
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

    async def create_agent_memory_episode(
        self,
        domain: str,
        title: str,
        goal: str,
        problem_signature: str,
        *,
        scope: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        evidence: list[dict[str, Any]] | None = None,
    ) -> AgentMemoryEpisode:
        data = await self._request(
            "POST",
            "/v1/agent-memory/episodes",
            json={
                "domain": domain,
                "title": title,
                "goal": goal,
                "problem_signature": problem_signature,
                "scope": scope or {},
                "tags": tags or [],
                "metadata": metadata or {},
                "evidence": evidence or [],
            },
        )
        return AgentMemoryEpisode.model_validate(data)

    async def list_agent_memory_episodes(
        self, *, status: str | None = None, limit: int = 25
    ) -> list[AgentMemoryEpisode]:
        params: dict[str, Any] = {"limit": limit}
        if status is not None:
            params["status"] = status
        data = await self._request("GET", "/v1/agent-memory/episodes", params=params)
        return [AgentMemoryEpisode.model_validate(item) for item in data]

    async def get_agent_memory_episode(self, episode_id: str) -> AgentMemoryEpisode:
        data = await self._request("GET", f"/v1/agent-memory/episodes/{episode_id}")
        return AgentMemoryEpisode.model_validate(data)

    async def append_agent_memory_attempt(
        self,
        episode_id: str,
        hypothesis: str,
        actions: list[Any],
        result: str,
        *,
        notes: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMemoryAttempt:
        data = await self._request(
            "POST",
            f"/v1/agent-memory/episodes/{episode_id}/attempts",
            json={
                "hypothesis": hypothesis,
                "actions": actions,
                "result": result,
                "notes": notes,
                "metadata": metadata or {},
            },
        )
        return AgentMemoryAttempt.model_validate(data)

    async def record_agent_memory_outcome(
        self,
        episode_id: str,
        status: str,
        summary: str,
        *,
        lesson: str | None = None,
        verifiers: list[dict[str, Any]] | None = None,
        metrics: dict[str, Any] | None = None,
        pattern_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMemoryOutcome:
        data = await self._request(
            "POST",
            f"/v1/agent-memory/episodes/{episode_id}/outcomes",
            json={
                "status": status,
                "summary": summary,
                "lesson": lesson,
                "verifiers": verifiers or [],
                "metrics": metrics or {},
                "pattern_key": pattern_key,
                "metadata": metadata or {},
            },
        )
        return AgentMemoryOutcome.model_validate(data)

    async def search_agent_memory(
        self,
        query: str,
        *,
        problem_signature: str | None = None,
        repository: str | None = None,
        environment: str | None = None,
        include_inactive: bool = False,
        limit: int = 25,
    ) -> AgentMemorySearchResponse:
        params: dict[str, Any] = {"q": query, "include_inactive": include_inactive, "limit": limit}
        if problem_signature is not None:
            params["problem_signature"] = problem_signature
        if repository is not None:
            params["repository"] = repository
        if environment is not None:
            params["environment"] = environment
        data = await self._request("GET", "/v1/agent-memory/search", params=params)
        return AgentMemorySearchResponse.model_validate(data)

    async def feedback_agent_memory_episode(
        self, episode_id: str, score: int
    ) -> AgentMemoryEpisode:
        data = await self._request(
            "POST", f"/v1/agent-memory/episodes/{episode_id}/feedback", json={"score": score}
        )
        return AgentMemoryEpisode.model_validate(data)

    async def supersede_agent_memory_episode(
        self, episode_id: str, superseding_episode_id: str
    ) -> AgentMemoryEpisode:
        data = await self._request(
            "POST",
            f"/v1/agent-memory/episodes/{episode_id}/supersede",
            json={"superseding_episode_id": superseding_episode_id},
        )
        return AgentMemoryEpisode.model_validate(data)

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

    async def search_graph(
        self,
        dataset_id: str,
        query: str,
        *,
        entity_type: str | None = None,
        limit: int = 25,
    ) -> list[Entity]:
        params: dict[str, Any] = {"q": query, "limit": limit}
        if entity_type is not None:
            params["entity_type"] = entity_type
        data = await self._request(
            "GET",
            f"/v1/datasets/{dataset_id}/entities/search",
            params=params,
        )
        return [Entity.model_validate(item) for item in data]

    async def find_graph_path(
        self,
        dataset_id: str,
        source_entity_id: str,
        target_entity_id: str,
        *,
        max_depth: int = 3,
        relation_limit: int = 100,
    ) -> GraphPath:
        data = await self._request(
            "GET",
            f"/v1/datasets/{dataset_id}/graph/path",
            params={
                "source_entity_id": source_entity_id,
                "target_entity_id": target_entity_id,
                "max_depth": max_depth,
                "relation_limit": relation_limit,
            },
        )
        return GraphPath.model_validate(data)

    async def get_subgraph(
        self,
        dataset_id: str,
        entity_id: str,
        *,
        depth: int = 1,
        node_limit: int = 100,
        relation_limit: int = 200,
    ) -> GraphSubgraph:
        data = await self._request(
            "GET",
            f"/v1/datasets/{dataset_id}/graph/subgraph",
            params={
                "entity_id": entity_id,
                "depth": depth,
                "node_limit": node_limit,
                "relation_limit": relation_limit,
            },
        )
        return GraphSubgraph.model_validate(data)

    async def get_evidence(self, evidence_id: str) -> Evidence:
        data = await self._request("GET", f"/v1/evidence/{evidence_id}")
        return Evidence.model_validate(data)

    async def get_relation_evidence(
        self, dataset_id: str, relation_id: str, *, limit: int = 25
    ) -> list[Evidence]:
        data = await self._request(
            "GET",
            f"/v1/datasets/{dataset_id}/relations/{relation_id}/evidence",
            params={"limit": limit},
        )
        return [Evidence.model_validate(item) for item in data]

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
