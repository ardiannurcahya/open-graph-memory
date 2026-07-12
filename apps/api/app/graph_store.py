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


@dataclass(frozen=True)
class DocumentProjection:
    project_id: str
    dataset_id: str
    document_id: str
    chunk_ids: tuple[str, ...]
    entities: tuple[GraphProjection, ...]
    relations: tuple[RelationProjection, ...]
    evidence: tuple["EvidenceProjection", ...]


@dataclass(frozen=True)
class EvidenceProjection:
    project_id: str
    dataset_id: str
    evidence_id: str
    document_id: str
    chunk_id: str
    entity_id: str | None
    relation_id: str | None


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
            response = await client.post(
                self.endpoint,
                auth=self.auth,
                json={"statements": [{"statement": statement, "parameters": parameters or {}}]},
            )
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
        scope: dict[str, object] = {
            "project_id": projection.project_id,
            "dataset_id": projection.dataset_id,
            "document_id": projection.document_id,
        }
        # Remove only this document's derived topology; shared entities and relations survive.
        await self._run(
            "MATCH (e:Evidence {project_id: $project_id, dataset_id: $dataset_id, document_id: $document_id}) DETACH DELETE e",
            scope,
        )
        await self._run(
            "MATCH (c:Chunk {project_id: $project_id, dataset_id: $dataset_id, document_id: $document_id}) "
            "DETACH DELETE c",
            scope,
        )
        await self._run(
            "MATCH (d:Document {project_id: $project_id, dataset_id: $dataset_id, id: $document_id}) "
            "DETACH DELETE d",
            scope,
        )
        await self._run(
            "MATCH (r:Relation {project_id: $project_id, dataset_id: $dataset_id}) "
            "WHERE NOT (r)-[:SUPPORTED_BY]->(:Evidence) DETACH DELETE r",
            scope,
        )
        await self._run(
            "MERGE (p:Project {id: $project_id}) "
            "MERGE (d:Dataset {project_id: $project_id, id: $dataset_id}) "
            "MERGE (p)-[:HAS_DATASET]->(d) "
            "MERGE (doc:Document {project_id: $project_id, dataset_id: $dataset_id, id: $document_id}) "
            "MERGE (d)-[:HAS_DOCUMENT]->(doc)",
            scope,
        )
        await self._run(
            "UNWIND $rows AS row "
            "MATCH (doc:Document {project_id: row.project_id, dataset_id: row.dataset_id, id: row.document_id}) "
            "MERGE (c:Chunk {project_id: row.project_id, dataset_id: row.dataset_id, id: row.chunk_id}) "
            "SET c.document_id = row.document_id "
            "MERGE (doc)-[:HAS_CHUNK]->(c)",
            {"rows": [dict(scope, chunk_id=chunk_id) for chunk_id in projection.chunk_ids]},
        )
        await self._project_entities(list(projection.entities))
        await self._project_relations(list(projection.relations))
        await self._project_evidence(list(projection.evidence))

    async def _project_entities(self, entities: list[GraphProjection]) -> None:
        await self._run(
            "UNWIND $rows AS row "
            "MERGE (e:Entity {project_id: row.project_id, dataset_id: row.dataset_id, id: row.entity_id}) "
            "SET e.canonical_name = row.canonical_name, e.entity_type = row.entity_type, e.version = row.version",
            {"rows": [entity.__dict__ for entity in entities]},
        )

    async def _project_relations(self, relations: list[RelationProjection]) -> None:
        await self._run(
            "UNWIND $rows AS row "
            "MATCH (s:Entity {project_id: row.project_id, dataset_id: row.dataset_id, id: row.source_id}) "
            "MATCH (t:Entity {project_id: row.project_id, dataset_id: row.dataset_id, id: row.target_id}) "
            "MERGE (r:Relation {project_id: row.project_id, dataset_id: row.dataset_id, id: row.relation_id}) "
            "SET r.relation_type = row.relation_type, r.extractor_version = row.extractor_version, r.confidence = row.confidence, r.review_state = row.review_state "
            "MERGE (r)-[:SOURCE]->(s) MERGE (r)-[:TARGET]->(t)",
            {"rows": [relation.__dict__ for relation in relations]},
        )

    async def _project_evidence(self, evidence: list[EvidenceProjection]) -> None:
        await self._run(
            "UNWIND $rows AS row "
            "MATCH (c:Chunk {project_id: row.project_id, dataset_id: row.dataset_id, id: row.chunk_id, document_id: row.document_id}) "
            "MERGE (e:Evidence {project_id: row.project_id, dataset_id: row.dataset_id, id: row.evidence_id}) "
            "SET e.document_id = row.document_id, e.chunk_id = row.chunk_id "
            "MERGE (e)-[:FROM_CHUNK]->(c) "
            "FOREACH (_ IN CASE WHEN row.entity_id IS NULL THEN [] ELSE [1] END | "
            "MATCH (entity:Entity {project_id: row.project_id, dataset_id: row.dataset_id, id: row.entity_id}) "
            "MERGE (c)-[:MENTIONS]->(entity)) "
            "FOREACH (_ IN CASE WHEN row.relation_id IS NULL THEN [] ELSE [1] END | "
            "MATCH (relation:Relation {project_id: row.project_id, dataset_id: row.dataset_id, id: row.relation_id}) "
            "MERGE (c)-[:ASSERTS]->(relation) MERGE (relation)-[:SUPPORTED_BY]->(e))",
            {"rows": [item.__dict__ for item in evidence]},
        )

    async def reconcile_dataset(self, project_id: str, dataset_id: str) -> None:
        await self._run(
            "MATCH (n) WHERE n.project_id = $project_id AND n.dataset_id = $dataset_id DETACH DELETE n",
            {"project_id": project_id, "dataset_id": dataset_id},
        )
