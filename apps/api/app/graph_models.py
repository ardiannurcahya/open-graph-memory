from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ReviewState(StrEnum):
    UNREVIEWED = "unreviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class GraphJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class GraphExtractionJob(Base):
    __tablename__ = "graph_extraction_jobs"
    __table_args__ = (
        UniqueConstraint("document_id", "extractor_version", name="uq_graph_job_document_version"),
        Index("ix_graph_jobs_scope", "project_id", "dataset_id", "document_id"),
        Index("ix_graph_jobs_dispatch", "status", "next_attempt_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    status: Mapped[GraphJobStatus] = mapped_column(Enum(GraphJobStatus, name="graph_job_status"))
    attempt: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=5)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(255))
    extractor_version: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(100))
    ontology_version: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GraphExtractionOutbox(Base):
    __tablename__ = "graph_extraction_outbox"
    job_id: Mapped[str] = mapped_column(
        ForeignKey("graph_extraction_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ScopeMixin:
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))


class GraphExtractionRun(ScopeMixin, Base):
    __tablename__ = "graph_extraction_runs"
    __table_args__ = (
        UniqueConstraint("chunk_id", "extractor_version", "input_hash", name="uq_graph_run_input"),
        Index("ix_graph_runs_scope", "project_id", "dataset_id", "document_id"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"))
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus, name="graph_run_status"))
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(255))
    extractor_version: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(100))
    ontology_version: Mapped[str | None] = mapped_column(String(100))
    input_hash: Mapped[str] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CanonicalEntity(ScopeMixin, Base):
    __tablename__ = "canonical_entities"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "normalized_name", "entity_type", name="uq_entity_candidate"
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(500))
    normalized_name: Mapped[str] = mapped_column(String(500))
    entity_type: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Float)
    version: Mapped[int] = mapped_column(default=1)
    review_state: Mapped[ReviewState] = mapped_column(Enum(ReviewState, name="graph_review_state"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EntityAlias(ScopeMixin, Base):
    __tablename__ = "entity_aliases"
    __table_args__ = (
        UniqueConstraint("dataset_id", "normalized_alias", "entity_type"),
        CheckConstraint("confidence BETWEEN 0 AND 1"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("canonical_entities.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(500))
    normalized_alias: Mapped[str] = mapped_column(String(500))
    entity_type: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Float)


class RelationAssertion(ScopeMixin, Base):
    __tablename__ = "relation_assertions"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "source_entity_id",
            "relation_type",
            "target_entity_id",
            "extractor_version",
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1"),
        CheckConstraint("source_entity_id <> target_entity_id"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_entity_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_entities.id", ondelete="RESTRICT")
    )
    target_entity_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_entities.id", ondelete="RESTRICT")
    )
    relation_type: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Float)
    extractor_version: Mapped[str] = mapped_column(String(100))
    review_state: Mapped[ReviewState] = mapped_column(Enum(ReviewState, name="graph_review_state"))


class GraphEvidence(ScopeMixin, Base):
    __tablename__ = "graph_evidence"
    __table_args__ = (
        CheckConstraint("(entity_id IS NULL) <> (relation_id IS NULL)", name="ck_evidence_subject"),
        CheckConstraint("confidence BETWEEN 0 AND 1"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"))
    run_id: Mapped[str] = mapped_column(ForeignKey("graph_extraction_runs.id", ondelete="CASCADE"))
    entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("canonical_entities.id", ondelete="CASCADE")
    )
    relation_id: Mapped[str | None] = mapped_column(
        ForeignKey("relation_assertions.id", ondelete="CASCADE")
    )
    quote: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int | None]
    end_offset: Mapped[int | None]
    confidence: Mapped[float] = mapped_column(Float)


class EntityMergeHistory(ScopeMixin, Base):
    __tablename__ = "entity_merge_history"
    __table_args__ = (CheckConstraint("source_entity_id <> target_entity_id"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_entity_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_entities.id", ondelete="RESTRICT")
    )
    target_entity_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_entities.id", ondelete="RESTRICT")
    )
    reason: Mapped[str] = mapped_column(Text)
    review_state: Mapped[ReviewState] = mapped_column(Enum(ReviewState, name="graph_review_state"))
    reviewer: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
