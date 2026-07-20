from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DatasetStatus(StrEnum):
    ACTIVE = "active"
    DELETING = "deleting"
    DELETE_FAILED = "delete_failed"


class DocumentStatus(StrEnum):
    PENDING_UPLOAD = "pending_upload"
    UPLOADED = "uploaded"
    STORAGE_FAILED = "storage_failed"
    QUEUED = "queued"
    PARSING = "parsing"
    CHUNKING = "chunking"
    PERSISTING = "persisting"
    INDEXED = "indexed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE = "stale"
    DELETING = "deleting"
    DELETE_FAILED = "delete_failed"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class IndexingStage(StrEnum):
    QUEUED = "queued"
    READING = "reading"
    PARSING = "parsing"
    CHUNKING = "chunking"
    PERSISTING = "persisting"
    COMPLETE = "complete"


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    key_prefix: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_datasets_project_name"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[DatasetStatus] = mapped_column(Enum(DatasetStatus, name="dataset_status"))
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "dataset_id", "content_hash", name="uq_documents_project_dataset_hash"
        ),
        Index("ix_documents_project_dataset", "project_id", "dataset_id"),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(32), default="upload")
    object_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus, name="document_status"))
    error_message: Mapped[str | None] = mapped_column(Text)
    graph_stage: Mapped[str | None] = mapped_column(String(32))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "pipeline_version", "chunk_index"),
        Index("ix_chunks_scope", "project_id", "dataset_id"),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    pipeline_version: Mapped[str] = mapped_column(String(100))
    chunk_index: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int]
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IndexingJob(Base):
    __tablename__ = "indexing_jobs"
    __table_args__ = (UniqueConstraint("document_id", "pipeline_version"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="indexing_job_status"))
    stage: Mapped[IndexingStage] = mapped_column(Enum(IndexingStage, name="indexing_stage"))
    attempt: Mapped[int] = mapped_column(default=0)
    pipeline_version: Mapped[str] = mapped_column(String(100))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IndexingOutbox(Base):
    __tablename__ = "indexing_outbox"
    job_id: Mapped[str] = mapped_column(
        ForeignKey("indexing_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IndexingArtifact(Base):
    __tablename__ = "indexing_artifacts"
    __table_args__ = (UniqueConstraint("job_id", "kind", "version", name="uq_artifact_version"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("indexing_jobs.id", ondelete="CASCADE"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    version: Mapped[str] = mapped_column(String(100))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IndexingStageEvent(Base):
    __tablename__ = "indexing_stage_events"
    __table_args__ = (UniqueConstraint("job_id", "attempt", "stage", name="uq_job_attempt_stage"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("indexing_jobs.id", ondelete="CASCADE"))
    attempt: Mapped[int]
    stage: Mapped[IndexingStage] = mapped_column(Enum(IndexingStage, name="indexing_stage"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GraphAnalyticsRun(Base):
    __tablename__ = "graph_analytics_runs"
    __table_args__ = (
        UniqueConstraint("project_id", "dataset_id", "snapshot_hash", name="uq_analytics_snapshot"),
        Index("ix_analytics_runs_latest", "project_id", "dataset_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    entity_count: Mapped[int]
    relation_count: Mapped[int]
    community_count: Mapped[int]
    resolution: Mapped[float]
    seed: Mapped[int]
    levels: Mapped[int] = mapped_column(default=1)
    algorithm_version: Mapped[str] = mapped_column(String(100), default="louvain-v1")
    config: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GraphAnalyticsMembership(Base):
    __tablename__ = "graph_analytics_memberships"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("graph_analytics_runs.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_entities.id", ondelete="CASCADE"), primary_key=True
    )
    level: Mapped[int] = mapped_column(primary_key=True, default=0)
    community_id: Mapped[str] = mapped_column(String(32))


class GraphAnalyticsEntityMetric(Base):
    __tablename__ = "graph_analytics_entity_metrics"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("graph_analytics_runs.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_entities.id", ondelete="CASCADE"), primary_key=True
    )
    degree: Mapped[int]
    weighted_degree: Mapped[float]
    importance: Mapped[float]


class GraphAnalyticsCommunity(Base):
    __tablename__ = "graph_analytics_communities"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("graph_analytics_runs.id", ondelete="CASCADE"), primary_key=True
    )
    community_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    level: Mapped[int] = mapped_column(primary_key=True, default=0)
    parent_community_id: Mapped[str | None] = mapped_column(String(32))
    entity_count: Mapped[int]
    internal_edges: Mapped[int] = mapped_column(default=0)
    external_edges: Mapped[int] = mapped_column(default=0)
    density: Mapped[float] = mapped_column(default=0.0)
    importance: Mapped[float] = mapped_column(default=0.0)


class AgentMemoryEpisode(Base):
    __tablename__ = "agent_memory_episodes"
    __table_args__ = (
        CheckConstraint(
            "domain IN ('engineering', 'trading', 'research', 'operations', 'custom')",
            name="ck_agent_memory_episode_domain",
        ),
        CheckConstraint(
            "status IN ('open', 'active', 'degraded', 'superseded', 'rejected')",
            name="ck_agent_memory_episode_status",
        ),
        Index("ix_agent_memory_episodes_scope_created", "project_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    domain: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    goal: Mapped[str] = mapped_column(Text)
    problem_signature: Mapped[str] = mapped_column(String(512))
    scope: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="open")
    feedback_score: Mapped[int] = mapped_column(default=0)
    superseded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_memory_episodes.id", ondelete="SET NULL")
    )
    search_vector: Mapped[object] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', title || ' ' || goal || ' ' || problem_signature)",
            persisted=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentMemoryAttempt(Base):
    __tablename__ = "agent_memory_attempts"
    __table_args__ = (
        UniqueConstraint("episode_id", "sequence", name="uq_agent_memory_attempt_sequence"),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    episode_id: Mapped[str] = mapped_column(
        ForeignKey("agent_memory_episodes.id", ondelete="CASCADE")
    )
    sequence: Mapped[int]
    hypothesis: Mapped[str] = mapped_column(Text)
    actions: Mapped[list[object]] = mapped_column(JSONB, default=list)
    result: Mapped[str] = mapped_column(String(16))
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentMemoryOutcome(Base):
    __tablename__ = "agent_memory_outcomes"
    __table_args__ = (
        UniqueConstraint("episode_id", name="uq_agent_memory_final_outcome_episode"),
        CheckConstraint(
            "status IN ('success', 'failed', 'partial', 'cancelled')",
            name="ck_agent_memory_outcome_status",
        ),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    episode_id: Mapped[str] = mapped_column(
        ForeignKey("agent_memory_episodes.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(16))
    summary: Mapped[str] = mapped_column(Text)
    lesson: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    pattern_key: Mapped[str] = mapped_column(String(255))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentMemoryPattern(Base):
    __tablename__ = "agent_memory_patterns"
    __table_args__ = (
        UniqueConstraint("project_id", "pattern_key", name="uq_agent_memory_pattern_key"),
        Index("ix_agent_memory_patterns_search", "project_id", "promoted", "confidence"),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    pattern_key: Mapped[str] = mapped_column(String(255))
    verified_outcomes: Mapped[int] = mapped_column(default=0)
    weighted_successes: Mapped[float] = mapped_column(default=0.0)
    weighted_total: Mapped[float] = mapped_column(default=0.0)
    confidence: Mapped[float] = mapped_column(default=0.0)
    promoted: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentMemoryVerifier(Base):
    __tablename__ = "agent_memory_verifiers"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('ci', 'runtime', 'test', 'build', 'self_report', 'custom')",
            name="ck_agent_memory_verifier_kind",
        ),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    outcome_id: Mapped[str] = mapped_column(
        ForeignKey("agent_memory_outcomes.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32))
    command: Mapped[str | None] = mapped_column(Text)
    artifact_uri: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)


class AgentMemoryEvidence(Base):
    __tablename__ = "agent_memory_evidence"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    episode_id: Mapped[str] = mapped_column(
        ForeignKey("agent_memory_episodes.id", ondelete="CASCADE")
    )
    reference: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)


class AgentMemoryPatternMember(Base):
    __tablename__ = "agent_memory_pattern_members"
    pattern_id: Mapped[str] = mapped_column(
        ForeignKey("agent_memory_patterns.id", ondelete="CASCADE"), primary_key=True
    )
    outcome_id: Mapped[str] = mapped_column(
        ForeignKey("agent_memory_outcomes.id", ondelete="CASCADE"), primary_key=True
    )


class AgentMemoryRetrievalAudit(Base):
    __tablename__ = "agent_memory_retrieval_audit"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    query: Mapped[str] = mapped_column(Text)
    results: Mapped[list[object]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
