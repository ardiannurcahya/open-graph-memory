"""Idempotent, tenant-scoped Neo4j projection."""

# Cypher clauses remain intact so queries are directly usable in Neo4j tooling.
# ruff: noqa: E501

from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class GraphProjection:
    project_id: str
    dataset_id: str
    entity_id: str
    canonical_name: str
    entity_type: str
    version: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RelationProjection:
    project_id: str
    dataset_id: str
    relation_id: str
    source_id: str
    target_id: str
    relation_type: str
    extractor_version: str
    confidence: float
    review_state: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ChunkProjection:
    project_id: str
    dataset_id: str
    document_id: str
    chunk_id: str
    pipeline_version: str
    created_at: str


@dataclass(frozen=True)
class EvidenceProjection:
    project_id: str
    dataset_id: str
    evidence_id: str
    document_id: str
    chunk_id: str
    entity_id: str | None
    relation_id: str | None
    run_id: str
    quote: str
    confidence: float
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DocumentProjection:
    project_id: str
    dataset_id: str
    document_id: str
    document_created_at: str
    document_updated_at: str
    chunks: tuple[ChunkProjection, ...]
    entities: tuple[GraphProjection, ...]
    relations: tuple[RelationProjection, ...]
    evidence: tuple[EvidenceProjection, ...]


class GraphStore(Protocol):
    async def bootstrap(self) -> None: ...
    async def project_document(self, projection: DocumentProjection) -> None: ...
    async def reconcile_dataset(self, project_id: str, dataset_id: str) -> None: ...


class Neo4jGraphStore:
    """Neo4j transactional HTTP adapter; all values are Cypher parameters."""

    def __init__(self, url: str, auth: str, database: str = "neo4j", timeout: float = 10) -> None:
        user, separator, password = auth.partition("/")
        if not separator:
            raise ValueError("Neo4j auth must be user/password")
        self.endpoint = f"{url.rstrip('/')}/db/{database}/tx/commit"
        self.auth = (user, password)
        self.timeout = timeout

    async def _run(self, statement: str, parameters: dict[str, object] | None = None) -> None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.endpoint, auth=self.auth, json={"statements": [{"statement": statement, "parameters": parameters or {}}]})
        response.raise_for_status()
        errors = response.json().get("errors", [])
        if errors:
            raise RuntimeError(str(errors[0].get("message", "Neo4j query failed")))

    async def bootstrap(self) -> None:
        for statement in (
            "CREATE CONSTRAINT project_id IF NOT EXISTS FOR (p:Project) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT dataset_scope_id IF NOT EXISTS FOR (d:Dataset) REQUIRE (d.project_id, d.id) IS UNIQUE",
            "CREATE CONSTRAINT document_scope_id IF NOT EXISTS FOR (d:Document) REQUIRE (d.project_id, d.dataset_id, d.id) IS UNIQUE",
            "CREATE CONSTRAINT chunk_scope_id IF NOT EXISTS FOR (c:Chunk) REQUIRE (c.project_id, c.dataset_id, c.id) IS UNIQUE",
            "CREATE CONSTRAINT entity_scope_id IF NOT EXISTS FOR (e:Entity) REQUIRE (e.project_id, e.dataset_id, e.id) IS UNIQUE",
            "CREATE CONSTRAINT relation_scope_id IF NOT EXISTS FOR (r:Relation) REQUIRE (r.project_id, r.dataset_id, r.id) IS UNIQUE",
            "CREATE CONSTRAINT evidence_scope_id IF NOT EXISTS FOR (e:Evidence) REQUIRE (e.project_id, e.dataset_id, e.id) IS UNIQUE",
        ):
            await self._run(statement)

    async def project_document(self, projection: DocumentProjection) -> None:
        scope: dict[str, object] = {"project_id": projection.project_id, "dataset_id": projection.dataset_id, "document_id": projection.document_id, "document_created_at": projection.document_created_at, "document_updated_at": projection.document_updated_at}
        await self._run("MATCH (e:Evidence {project_id: $project_id, dataset_id: $dataset_id, document_id: $document_id}) DETACH DELETE e", scope)
        await self._run("MATCH (c:Chunk {project_id: $project_id, dataset_id: $dataset_id, document_id: $document_id}) DETACH DELETE c", scope)
        await self._run("MATCH (d:Document {project_id: $project_id, dataset_id: $dataset_id, id: $document_id}) DETACH DELETE d", scope)
        await self._run("MATCH (r:Relation {project_id: $project_id, dataset_id: $dataset_id}) WHERE NOT (r)-[:SUPPORTED_BY]->(:Evidence) DETACH DELETE r", scope)
        await self._run(
            "MERGE (p:Project {id: $project_id}) MERGE (d:Dataset {project_id: $project_id, id: $dataset_id}) MERGE (p)-[:HAS_DATASET]->(d) "
            "MERGE (doc:Document {project_id: $project_id, dataset_id: $dataset_id, id: $document_id}) "
            "SET doc.created_at = $document_created_at, doc.updated_at = $document_updated_at "
            "MERGE (d)-[edge:HAS_DOCUMENT]->(doc) SET edge.project_id = $project_id, edge.dataset_id = $dataset_id, edge.document_id = $document_id, edge.created_at = $document_created_at, edge.updated_at = $document_updated_at",
            scope,
        )
        await self._run(
            "UNWIND $rows AS row MATCH (doc:Document {project_id: row.project_id, dataset_id: row.dataset_id, id: row.document_id}) "
            "MERGE (c:Chunk {project_id: row.project_id, dataset_id: row.dataset_id, id: row.chunk_id}) "
            "SET c.document_id = row.document_id, c.pipeline_version = row.pipeline_version, c.created_at = row.created_at "
            "MERGE (doc)-[edge:HAS_CHUNK]->(c) SET edge.project_id = row.project_id, edge.dataset_id = row.dataset_id, edge.document_id = row.document_id, edge.chunk_id = row.chunk_id, edge.created_at = row.created_at, edge.updated_at = row.created_at",
            {"rows": [chunk.__dict__ for chunk in projection.chunks]},
        )
        await self._project_entities(list(projection.entities))
        await self._project_relations(list(projection.relations))
        await self._project_evidence(list(projection.evidence))

    async def _project_entities(self, entities: list[GraphProjection]) -> None:
        await self._run("UNWIND $rows AS row MERGE (e:Entity {project_id: row.project_id, dataset_id: row.dataset_id, id: row.entity_id}) SET e.canonical_name = row.canonical_name, e.entity_type = row.entity_type, e.version = row.version, e.created_at = row.created_at, e.updated_at = row.updated_at", {"rows": [entity.__dict__ for entity in entities]})

    async def _project_relations(self, relations: list[RelationProjection]) -> None:
        await self._run(
            "UNWIND $rows AS row MATCH (s:Entity {project_id: row.project_id, dataset_id: row.dataset_id, id: row.source_id}) MATCH (t:Entity {project_id: row.project_id, dataset_id: row.dataset_id, id: row.target_id}) "
            "MERGE (r:Relation {project_id: row.project_id, dataset_id: row.dataset_id, id: row.relation_id}) SET r.relation_type = row.relation_type, r.extractor_version = row.extractor_version, r.confidence = row.confidence, r.review_state = row.review_state, r.created_at = row.created_at, r.updated_at = row.updated_at "
            "MERGE (r)-[source:SOURCE]->(s) SET source.project_id = row.project_id, source.dataset_id = row.dataset_id, source.relation_id = row.relation_id, source.created_at = row.created_at, source.updated_at = row.updated_at "
            "MERGE (r)-[target:TARGET]->(t) SET target.project_id = row.project_id, target.dataset_id = row.dataset_id, target.relation_id = row.relation_id, target.created_at = row.created_at, target.updated_at = row.updated_at",
            {"rows": [relation.__dict__ for relation in relations]},
        )

    async def _project_evidence(self, evidence: list[EvidenceProjection]) -> None:
        rows = [item.__dict__ for item in evidence]
        await self._run("UNWIND $rows AS row MATCH (c:Chunk {project_id: row.project_id, dataset_id: row.dataset_id, id: row.chunk_id, document_id: row.document_id}) MERGE (e:Evidence {project_id: row.project_id, dataset_id: row.dataset_id, id: row.evidence_id}) SET e.document_id = row.document_id, e.chunk_id = row.chunk_id, e.run_id = row.run_id, e.quote = row.quote, e.confidence = row.confidence, e.provider = row.provider, e.model = row.model, e.extractor_version = row.extractor_version, e.prompt_version = row.prompt_version, e.created_at = row.created_at, e.updated_at = row.updated_at MERGE (e)-[edge:FROM_CHUNK]->(c) SET edge.project_id = row.project_id, edge.dataset_id = row.dataset_id, edge.document_id = row.document_id, edge.chunk_id = row.chunk_id, edge.evidence_id = row.evidence_id, edge.created_at = row.created_at, edge.updated_at = row.updated_at", {"rows": rows})
        await self._run("UNWIND $rows AS row MATCH (c:Chunk {project_id: row.project_id, dataset_id: row.dataset_id, id: row.chunk_id, document_id: row.document_id}) MATCH (entity:Entity {project_id: row.project_id, dataset_id: row.dataset_id, id: row.entity_id}) MERGE (c)-[edge:MENTIONS]->(entity) SET edge.project_id = row.project_id, edge.dataset_id = row.dataset_id, edge.document_id = row.document_id, edge.chunk_id = row.chunk_id, edge.evidence_id = row.evidence_id, edge.created_at = row.created_at, edge.updated_at = row.updated_at", {"rows": [row for row in rows if row["entity_id"] is not None]})
        await self._run("UNWIND $rows AS row MATCH (c:Chunk {project_id: row.project_id, dataset_id: row.dataset_id, id: row.chunk_id, document_id: row.document_id}) MATCH (e:Evidence {project_id: row.project_id, dataset_id: row.dataset_id, id: row.evidence_id}) MATCH (relation:Relation {project_id: row.project_id, dataset_id: row.dataset_id, id: row.relation_id}) MERGE (c)-[assertion:ASSERTS]->(relation) SET assertion.project_id = row.project_id, assertion.dataset_id = row.dataset_id, assertion.document_id = row.document_id, assertion.chunk_id = row.chunk_id, assertion.evidence_id = row.evidence_id, assertion.created_at = row.created_at, assertion.updated_at = row.updated_at MERGE (relation)-[support:SUPPORTED_BY]->(e) SET support.project_id = row.project_id, support.dataset_id = row.dataset_id, support.document_id = row.document_id, support.chunk_id = row.chunk_id, support.evidence_id = row.evidence_id, support.created_at = row.created_at, support.updated_at = row.updated_at", {"rows": [row for row in rows if row["relation_id"] is not None]})

    async def reconcile_dataset(self, project_id: str, dataset_id: str) -> None:
        await self._run("MATCH (n) WHERE n.project_id = $project_id AND n.dataset_id = $dataset_id DETACH DELETE n", {"project_id": project_id, "dataset_id": dataset_id})
