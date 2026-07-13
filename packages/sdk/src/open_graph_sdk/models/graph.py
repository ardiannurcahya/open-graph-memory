
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GraphCitation(BaseModel):
    dataset_id: str
    document_id: str
    chunk_id: str
    quote: str


class Entity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    dataset_id: str
    canonical_name: str
    entity_type: str
    confidence: float
    version: int
    review_state: str


class Relation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    dataset_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    confidence: float
    extractor_version: str
    review_state: str
    citations: list[GraphCitation] = Field(default_factory=list)


class Neighbor(BaseModel):
    relation: Relation
    entity: Entity


class GraphSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dataset_id: str
    entity_count: int
    relation_count: int
    nodes: list[Entity]
    relations: list[Relation]


class Evidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    run_id: str
    entity_id: str | None = None
    relation_id: str | None = None
    dataset_id: str
    document_id: str
    chunk_id: str
    quote: str
    confidence: float
    start_offset: int | None = None
    end_offset: int | None = None


class GraphRun(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    dataset_id: str
    document_id: str
    chunk_id: str
    status: str
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    ontology_version: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class GraphJob(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    dataset_id: str
    document_id: str
    status: str
    attempt: int
    max_attempts: int
    error_message: str | None = None
    provider: str
    model: str
    extractor_version: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ReviewInput(BaseModel):
    review_state: str
