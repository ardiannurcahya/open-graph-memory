from dataclasses import dataclass
from typing import Protocol

from qdrant_client import AsyncQdrantClient, models


@dataclass(frozen=True)
class VectorPoint:
    id: str
    vector: list[float]
    project_id: str
    dataset_id: str
    document_id: str
    text: str
    pipeline_version: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class VectorHit:
    id: str
    score: float
    payload: dict[str, object]


class VectorStore(Protocol):
    async def upsert(self, points: list[VectorPoint]) -> None: ...
    async def search(
        self, vector: list[float], project_id: str, dataset_id: str, limit: int
    ) -> list[VectorHit]: ...


class QdrantVectorStore:
    def __init__(self, client: AsyncQdrantClient, collection: str, dimensions: int) -> None:
        self.client, self.collection, self.dimensions = client, collection, dimensions

    async def setup(self) -> None:
        if not await self.client.collection_exists(self.collection):
            await self.client.create_collection(
                self.collection,
                vectors_config=models.VectorParams(
                    size=self.dimensions, distance=models.Distance.COSINE
                ),
            )

    async def upsert(self, points: list[VectorPoint]) -> None:
        await self.setup()
        await self.client.upsert(
            self.collection,
            points=[
                models.PointStruct(
                    id=p.id,
                    vector=p.vector,
                    payload={
                        "project_id": p.project_id,
                        "dataset_id": p.dataset_id,
                        "document_id": p.document_id,
                        "text": p.text,
                        "pipeline_version": p.pipeline_version,
                        **p.metadata,
                    },
                )
                for p in points
            ],
            wait=True,
        )

    async def search(
        self, vector: list[float], project_id: str, dataset_id: str, limit: int
    ) -> list[VectorHit]:
        await self.setup()
        scope = models.Filter(
            must=[
                models.FieldCondition(key="project_id", match=models.MatchValue(value=project_id)),
                models.FieldCondition(key="dataset_id", match=models.MatchValue(value=dataset_id)),
            ]
        )
        result = await self.client.query_points(
            self.collection, query=vector, query_filter=scope, limit=limit, with_payload=True
        )
        return [
            VectorHit(str(point.id), point.score, dict(point.payload or {}))
            for point in result.points
        ]
