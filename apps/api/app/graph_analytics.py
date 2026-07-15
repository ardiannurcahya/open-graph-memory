# ruff: noqa: E501
"""PostgreSQL-authoritative deterministic community analytics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID, uuid4

import networkx as nx
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.graph_models import CanonicalEntity, GraphEvidence, RelationAssertion, ReviewState
from app.models import (
    GraphAnalyticsCommunity,
    GraphAnalyticsEntityMetric,
    GraphAnalyticsMembership,
    GraphAnalyticsRun,
)

LOUVAIN_SEED = 0
LOUVAIN_RESOLUTION = 1.0
MAX_ANALYTICS_ENTITIES = 5_000
MAX_ANALYTICS_RELATIONS = 20_000


def analytics_relation() -> ColumnElement[bool]:
    """Only reviewed-visible, cited relations enter snapshots."""
    return (RelationAssertion.review_state != ReviewState.REJECTED) & exists().where(
        GraphEvidence.relation_id == RelationAssertion.id
    )


@dataclass(frozen=True)
class AnalyticsResult:
    snapshot_hash: str
    communities: dict[str, str]
    degree: dict[str, int]
    weighted_degree: dict[str, float]
    importance: dict[str, float]
    community_sizes: dict[str, int]
    relation_count: int


def snapshot_hash(entity_ids: list[str], relations: list[tuple[str, str, float]]) -> str:
    payload = {"entities": sorted(entity_ids), "relations": sorted(relations)}
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def analyze_graph(
    entity_ids: list[str], relations: list[tuple[str, str, float]]
) -> AnalyticsResult:
    """Analyze sorted PostgreSQL rows. Neo4j is never read."""
    graph: nx.Graph[str] = nx.Graph()
    graph.add_nodes_from(sorted(entity_ids))
    for source_id, target_id, confidence in sorted(relations):
        weight = graph.get_edge_data(source_id, target_id, {}).get("weight", 0.0) + confidence
        graph.add_edge(source_id, target_id, weight=weight)
    digest = snapshot_hash(entity_ids, relations)
    groups = nx.community.louvain_communities(
        graph, weight="weight", resolution=LOUVAIN_RESOLUTION, seed=LOUVAIN_SEED
    )
    ordered_groups = sorted((sorted(group) for group in groups), key=lambda group: tuple(group))
    communities = {
        entity_id: hashlib.sha256(f"{digest}:{','.join(group)}".encode()).hexdigest()[:32]
        for group in ordered_groups
        for entity_id in group
    }
    degree = {entity_id: int(graph.degree(entity_id)) for entity_id in sorted(graph.nodes)}
    weighted_degree = {
        entity_id: float(graph.degree(entity_id, weight="weight"))
        for entity_id in sorted(graph.nodes)
    }
    total_weight = sum(weighted_degree.values())
    importance = (
        {entity_id: value / total_weight for entity_id, value in weighted_degree.items()}
        if total_weight
        else {entity_id: 1 / len(graph) for entity_id in graph}
        if graph.number_of_nodes()
        else {}
    )
    community_sizes = {
        hashlib.sha256(f"{digest}:{','.join(group)}".encode()).hexdigest()[:32]: len(group)
        for group in ordered_groups
    }
    return AnalyticsResult(
        digest, communities, degree, weighted_degree, importance, community_sizes, len(relations)
    )


async def refresh_dataset_analytics(
    db: AsyncSession, project_id: UUID, dataset_id: str
) -> GraphAnalyticsRun:
    """Bounded synchronous refresh. All source rows come from PostgreSQL."""
    entities = list(
        await db.scalars(
            select(CanonicalEntity.id)
            .where(
                CanonicalEntity.project_id == project_id, CanonicalEntity.dataset_id == dataset_id
            )
            .order_by(CanonicalEntity.id)
            .limit(MAX_ANALYTICS_ENTITIES + 1)
        )
    )
    if len(entities) > MAX_ANALYTICS_ENTITIES:
        raise ValueError("analytics entity limit exceeded")
    rows = list(
        await db.execute(
            select(
                RelationAssertion.source_entity_id,
                RelationAssertion.target_entity_id,
                RelationAssertion.confidence,
            )
            .where(
                RelationAssertion.project_id == project_id,
                RelationAssertion.dataset_id == dataset_id,
                analytics_relation(),
            )
            .order_by(RelationAssertion.id)
            .limit(MAX_ANALYTICS_RELATIONS + 1)
        )
    )
    if len(rows) > MAX_ANALYTICS_RELATIONS:
        raise ValueError("analytics relation limit exceeded")
    result = analyze_graph(
        entities, [(source, target, float(confidence)) for source, target, confidence in rows]
    )
    existing = await db.scalar(
        select(GraphAnalyticsRun).where(
            GraphAnalyticsRun.project_id == project_id,
            GraphAnalyticsRun.dataset_id == dataset_id,
            GraphAnalyticsRun.snapshot_hash == result.snapshot_hash,
        )
    )
    if existing is not None:
        return existing
    run = GraphAnalyticsRun(
        id=str(uuid4()),
        project_id=project_id,
        dataset_id=dataset_id,
        snapshot_hash=result.snapshot_hash,
        entity_count=len(entities),
        relation_count=result.relation_count,
        community_count=len(result.community_sizes),
        resolution=LOUVAIN_RESOLUTION,
        seed=LOUVAIN_SEED,
    )
    db.add(run)
    for entity_id in entities:
        db.add(
            GraphAnalyticsEntityMetric(
                run_id=run.id,
                entity_id=entity_id,
                degree=result.degree[entity_id],
                weighted_degree=result.weighted_degree[entity_id],
                importance=result.importance[entity_id],
            )
        )
        db.add(
            GraphAnalyticsMembership(
                run_id=run.id, entity_id=entity_id, community_id=result.communities[entity_id]
            )
        )
    for community_id, size in result.community_sizes.items():
        db.add(GraphAnalyticsCommunity(run_id=run.id, community_id=community_id, entity_count=size))
    await db.flush()
    return run
