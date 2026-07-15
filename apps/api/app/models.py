from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
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
    EMBEDDING = "embedding"
    PERSISTING = "persisting"
    INDEXED = "indexed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE = "stale"
    DELETING = "deleting"
    DELETE_FAILED = "delete_failed"


class MemoryFactStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


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
    EMBEDDING = "embedding"
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


class QueryLog(Base):
    __tablename__ = "query_logs"
    __table_args__ = (
        Index("ix_query_logs_scope_created", "project_id", "dataset_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(40), unique=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    query: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(255))
    provider_version: Mapped[str] = mapped_column(String(100))
    retrieval_trace: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    usage: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    latency_ms: Mapped[int] = mapped_column(BigInteger)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemoryUser(Base):
    __tablename__ = "memory_users"
    __table_args__ = (
        UniqueConstraint("project_id", "external_id", name="uq_memory_users_project_external"),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MemoryAgent(Base):
    __tablename__ = "memory_agents"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_memory_agents_project_name"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MemorySession(Base):
    __tablename__ = "memory_sessions"
    __table_args__ = (Index("ix_memory_sessions_scope", "project_id", "user_id", "agent_id"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(ForeignKey("memory_users.id", ondelete="CASCADE"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("memory_agents.id", ondelete="CASCADE"))
    title: Mapped[str | None] = mapped_column(String(255))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MemoryMessage(Base):
    __tablename__ = "memory_messages"
    __table_args__ = (Index("ix_memory_messages_session_created", "session_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    session_id: Mapped[str] = mapped_column(ForeignKey("memory_sessions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemoryFact(Base):
    __tablename__ = "memory_facts"
    __table_args__ = (
        Index("ix_memory_facts_scope_status", "project_id", "scope", "status"),
        Index("ix_memory_facts_subject", "project_id", "subject", "predicate"),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("memory_users.id", ondelete="CASCADE"))
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("memory_agents.id", ondelete="CASCADE"))
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("memory_sessions.id", ondelete="CASCADE")
    )
    scope: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(255))
    predicate: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    confidence: Mapped[int] = mapped_column(default=100)
    status: Mapped[MemoryFactStatus] = mapped_column(
        Enum(MemoryFactStatus, name="memory_fact_status")
    )
    supersedes_id: Mapped[str | None] = mapped_column(
        ForeignKey("memory_facts.id", ondelete="SET NULL")
    )
    source_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("memory_messages.id", ondelete="SET NULL")
    )
    provenance: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GraphAnalyticsMembership(Base):
    __tablename__ = "graph_analytics_memberships"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("graph_analytics_runs.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_entities.id", ondelete="CASCADE"), primary_key=True
    )
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
    entity_count: Mapped[int]
