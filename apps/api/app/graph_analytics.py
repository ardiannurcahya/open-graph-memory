# ruff: noqa: E501, E701, E702
"""PostgreSQL-authoritative deterministic hierarchical community analytics.

Level 0 is finest; level 2 is broadest. Each higher level partitions previous
communities, never entities, so every child has exactly one parent.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID, uuid4

import networkx as nx
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.community_reports import enqueue_community_report_jobs
from app.config import get_settings
from app.graph_models import CanonicalEntity, GraphEvidence, RelationAssertion, ReviewState
from app.models import (
    GraphAnalyticsCommunity,
    GraphAnalyticsEntityMetric,
    GraphAnalyticsMembership,
    GraphAnalyticsRun,
)

LOUVAIN_SEED = 0
LOUVAIN_RESOLUTION = 1.0
# Fixed, versioned. Larger resolution normally yields finer partitions.
HIERARCHY_RESOLUTIONS = (1.0, 0.5, 0.25)
HIERARCHY_ALGORITHM_VERSION = "hierarchical-louvain-v1"
MAX_ANALYTICS_ENTITIES = 5_000
MAX_ANALYTICS_RELATIONS = 20_000


def analytics_relation() -> ColumnElement[bool]:
    return (RelationAssertion.review_state != ReviewState.REJECTED) & exists().where(GraphEvidence.relation_id == RelationAssertion.id)


@dataclass(frozen=True)
class CommunityStats:
    members: tuple[str, ...]
    parent_id: str | None
    internal_edges: int
    external_edges: int
    density: float
    importance: float


@dataclass(frozen=True)
class AnalyticsResult:
    snapshot_hash: str
    memberships: dict[int, dict[str, str]]
    community_stats: dict[int, dict[str, CommunityStats]]

    @property
    def communities(self) -> dict[str, str]:
        """Backward-compatible level-0 membership map."""
        return self.memberships[0]
    degree: dict[str, int]
    weighted_degree: dict[str, float]
    importance: dict[str, float]
    relation_count: int

    @property
    def community_sizes(self) -> dict[str, int]:
        return {key: len(value.members) for key, value in self.community_stats[0].items()}


def snapshot_hash(entity_ids: list[str], relations: list[tuple[str, str, float]]) -> str:
    return hashlib.sha256(json.dumps({"entities": sorted(entity_ids), "relations": sorted(relations)}, separators=(",", ":")).encode()).hexdigest()


def _id(snapshot: str, level: int, members: tuple[str, ...]) -> str:
    value = f"{snapshot}:{HIERARCHY_ALGORITHM_VERSION}:{level}:{','.join(members)}"
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def _groups(graph: nx.Graph[str], resolution: float) -> list[tuple[str, ...]]:
    if not graph:
        return []
    return sorted((tuple(sorted(group)) for group in nx.community.louvain_communities(graph, weight="weight", resolution=resolution, seed=LOUVAIN_SEED)), key=lambda group: group)


def analyze_graph(entity_ids: list[str], relations: list[tuple[str, str, float]]) -> AnalyticsResult:
    """Build deterministic three-level containment hierarchy from PostgreSQL rows."""
    graph: nx.Graph[str] = nx.Graph()
    graph.add_nodes_from(sorted(entity_ids))
    for source, target, confidence in sorted(relations):
        graph.add_edge(source, target, weight=graph.get_edge_data(source, target, {}).get("weight", 0.0) + confidence)
    digest = snapshot_hash(entity_ids, relations)
    level_groups: list[list[tuple[str, ...]]] = [_groups(graph, HIERARCHY_RESOLUTIONS[0])]
    # Quotient partitions prevent independent Louvain partitions crossing children.
    for resolution in HIERARCHY_RESOLUTIONS[1:]:
        children = level_groups[-1]
        quotient: nx.Graph[int] = nx.Graph()
        quotient.add_nodes_from(range(len(children)))
        entity_child = {entity: index for index, group in enumerate(children) for entity in group}
        for source, target, data in graph.edges(data=True):
            left, right = entity_child[source], entity_child[target]
            if left != right:
                quotient.add_edge(left, right, weight=quotient.get_edge_data(left, right, {}).get("weight", 0.0) + float(data["weight"]))
        parent_indexes = _groups(nx.relabel_nodes(quotient, {index: str(index) for index in quotient.nodes}), resolution)
        level_groups.append([tuple(sorted(entity for index in group for entity in children[int(index)])) for group in parent_indexes])
    memberships: dict[int, dict[str, str]] = {}
    stats: dict[int, dict[str, CommunityStats]] = {}
    ids_by_members = [{group: _id(digest, level, group) for group in groups} for level, groups in enumerate(level_groups)]
    for level, groups in enumerate(level_groups):
        memberships[level] = {
            entity: ids_by_members[level][group] for group in groups for entity in group
        }
    total_weight = sum(float(data["weight"]) for _, _, data in graph.edges(data=True))
    for level, groups in enumerate(level_groups):
        stats[level] = {}
        for group in groups:
            members = set(group)
            internal = sum(1 for source, target in graph.edges if source in members and target in members)
            external = sum(1 for source, target in graph.edges if (source in members) != (target in members))
            weight = sum(float(data["weight"]) for source, target, data in graph.edges(data=True) if source in members or target in members)
            parent = None if level == 2 else memberships[level + 1][group[0]]
            stats[level][ids_by_members[level][group]] = CommunityStats(group, parent, internal, external, 0.0 if len(group) < 2 else 2 * internal / (len(group) * (len(group) - 1)), 0.0 if not total_weight else weight / (2 * total_weight))
    degree = {entity: int(graph.degree(entity)) for entity in graph.nodes}
    weighted_degree = {entity: float(graph.degree(entity, weight="weight")) for entity in graph.nodes}
    total = sum(weighted_degree.values())
    importance = {entity: value / total for entity, value in weighted_degree.items()} if total else ({entity: 1 / len(graph) for entity in graph} if graph else {})
    return AnalyticsResult(digest, memberships, stats, degree, weighted_degree, importance, len(relations))


async def refresh_dataset_analytics(db: AsyncSession, project_id: UUID, dataset_id: str) -> GraphAnalyticsRun:
    entities = list(await db.scalars(select(CanonicalEntity.id).where(CanonicalEntity.project_id == project_id, CanonicalEntity.dataset_id == dataset_id).order_by(CanonicalEntity.id).limit(MAX_ANALYTICS_ENTITIES + 1)))
    if len(entities) > MAX_ANALYTICS_ENTITIES: raise ValueError("analytics entity limit exceeded")
    rows = list(await db.execute(select(RelationAssertion.source_entity_id, RelationAssertion.target_entity_id, RelationAssertion.confidence).where(RelationAssertion.project_id == project_id, RelationAssertion.dataset_id == dataset_id, analytics_relation()).order_by(RelationAssertion.id).limit(MAX_ANALYTICS_RELATIONS + 1)))
    if len(rows) > MAX_ANALYTICS_RELATIONS: raise ValueError("analytics relation limit exceeded")
    result = analyze_graph(entities, [(source, target, float(confidence)) for source, target, confidence in rows])
    existing = await db.scalar(select(GraphAnalyticsRun).where(GraphAnalyticsRun.project_id == project_id, GraphAnalyticsRun.dataset_id == dataset_id, GraphAnalyticsRun.snapshot_hash == result.snapshot_hash))
    if existing:
        await enqueue_community_report_jobs(db, project_id, dataset_id, existing, get_settings()); return existing
    run = GraphAnalyticsRun(id=str(uuid4()), project_id=project_id, dataset_id=dataset_id, snapshot_hash=result.snapshot_hash, entity_count=len(entities), relation_count=result.relation_count, community_count=len(result.community_stats[0]), resolution=LOUVAIN_RESOLUTION, seed=LOUVAIN_SEED, levels=3, algorithm_version=HIERARCHY_ALGORITHM_VERSION, config={"resolutions": list(HIERARCHY_RESOLUTIONS)})
    db.add(run)
    for entity in entities:
        db.add(GraphAnalyticsEntityMetric(run_id=run.id, entity_id=entity, degree=result.degree[entity], weighted_degree=result.weighted_degree[entity], importance=result.importance[entity]))
        for level in range(3): db.add(GraphAnalyticsMembership(run_id=run.id, entity_id=entity, level=level, community_id=result.memberships[level][entity]))
    for level, communities in result.community_stats.items():
        for community_id, value in communities.items(): db.add(GraphAnalyticsCommunity(run_id=run.id, community_id=community_id, level=level, parent_community_id=value.parent_id, entity_count=len(value.members), internal_edges=value.internal_edges, external_edges=value.external_edges, density=value.density, importance=value.importance))
    await db.flush(); await enqueue_community_report_jobs(db, project_id, dataset_id, run, get_settings()); return run
