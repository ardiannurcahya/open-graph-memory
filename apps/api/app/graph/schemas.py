"""Request and response schemas for the structured graph API."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.graph.models import ReviewState


class Citation(BaseModel):
    dataset_id: str
    document_id: str
    chunk_id: str
    quote: str
    source_location: dict[str, int] | None = None


class EntityView(BaseModel):
    id: str
    dataset_id: str
    canonical_name: str
    entity_type: str
    confidence: float
    version: int
    review_state: ReviewState
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    superseded_by: str | None = None


class RelationView(BaseModel):
    id: str
    dataset_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    confidence: float
    extractor_version: str
    review_state: ReviewState
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    superseded_by: str | None = None
    citations: list[Citation] = Field(default_factory=list)


class NeighborView(BaseModel):
    relation: RelationView
    entity: EntityView


class GraphSummary(BaseModel):
    dataset_id: str
    entity_count: int
    relation_count: int
    nodes: list[EntityView]
    relations: list[RelationView]


class PathView(BaseModel):
    dataset_id: str
    source_entity_id: str
    target_entity_id: str
    found: bool
    hops: int
    nodes: list[EntityView]
    relations: list[RelationView]


class SubgraphView(BaseModel):
    dataset_id: str
    root_entity_id: str
    depth: int
    nodes: list[EntityView]
    relations: list[RelationView]


class EvidenceView(Citation):
    id: str
    run_id: str
    entity_id: str | None
    relation_id: str | None
    confidence: float
    start_offset: int | None
    end_offset: int | None


class RunView(BaseModel):
    id: str
    dataset_id: str
    document_id: str
    chunk_id: str
    status: str
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    ontology_version: str | None
    error_message: str | None
    created_at: datetime | None
    completed_at: datetime | None


class JobView(BaseModel):
    id: str
    dataset_id: str
    document_id: str
    status: str
    attempt: int
    max_attempts: int
    error_message: str | None
    provider: str
    model: str
    extractor_version: str
    created_at: datetime | None
    updated_at: datetime | None


class ReviewInput(BaseModel):
    review_state: ReviewState


class AnalyticsRunView(BaseModel):
    id: str
    dataset_id: str
    snapshot_hash: str
    entity_count: int
    relation_count: int
    community_count: int
    levels: int
    algorithm_version: str


class ExplorerAnalyticsView(AnalyticsRunView):
    created_at: datetime | None
    stale: bool


class ExplorerStats(BaseModel):
    entity_count: int
    relation_count: int
    density: float


class ExplorerNode(BaseModel):
    id: str
    canonical_name: str
    entity_type: str
    community_id: str | None
    degree: int
    weighted_degree: float
    importance: float


class ExplorerRelation(BaseModel):
    id: str
    source: str
    target: str
    type: str
    weight: float
    confidence: float


class ExplorerCommunity(BaseModel):
    id: str
    entity_count: int
    parent_id: str | None = None
    child_ids: list[str] = Field(default_factory=list)
    internal_edges: int = 0
    external_edges: int = 0
    density: float = 0.0
    importance: float = 0.0


class ExplorerView(BaseModel):
    dataset_id: str
    community_level: int = 0
    available_levels: list[int] = Field(default_factory=list)
    analytics: ExplorerAnalyticsView | None
    refresh_required: bool
    stats: ExplorerStats
    nodes: list[ExplorerNode]
    relations: list[ExplorerRelation]
    communities: list[ExplorerCommunity]


class ExplorerNodePage(BaseModel):
    nodes: list[ExplorerNode]
    next_cursor: str | None = None


class ExplorerRelationPage(BaseModel):
    relations: list[ExplorerRelation]
    next_cursor: str | None = None
