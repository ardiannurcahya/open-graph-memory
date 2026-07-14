import asyncio
import hashlib
import re

from celery.exceptions import SoftTimeLimitExceeded
from open_graph_contracts import PluginConfig, SecretValue
from open_graph_core.ids import new_id
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.async_runner import runner
from app.chunking import RecursiveTextChunker
from app.config import get_settings
from app.db import engine
from app.models import (
    Chunk,
    Document,
    DocumentStatus,
    IndexingArtifact,
    IndexingJob,
    IndexingOutbox,
    IndexingStage,
    IndexingStageEvent,
    JobStatus,
)
from app.parsers import default_registry
from app.plugin_registry import create_embedding, create_vector_store
from app.providers import EmbeddingProvider
from app.storage import ObjectStore, get_object_store
from app.vector_store import VectorPoint, VectorStore

PIPELINE_VERSION = "ingestion-v1:parser-v1:recursive-v1:embedding-v1"
EMBEDDING_BATCH_SIZE = 64
_TRANSIENT = (TimeoutError, ConnectionError, OSError)


def deterministic_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("\x1f".join(map(str, parts)).encode()).hexdigest()[:32]
    return f"{prefix}_{digest}"


def deterministic_point_id(*parts: object) -> str:
    """Return a Qdrant-compatible UUID derived from stable pipeline inputs."""
    digest = hashlib.sha256("\x1f".join(map(str, parts)).encode()).hexdigest()[:32]
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:]}"


def sanitized_error(exc: BaseException) -> str:
    message = re.sub(r"(?i)(password|secret|token|key)=\S+", r"\1=[redacted]", str(exc))
    return " ".join(message.split())[:1000] or type(exc).__name__


async def embed_in_batches(
    embeddings: EmbeddingProvider,
    texts: list[str],
    model: str,
    batch_size: int = EMBEDDING_BATCH_SIZE,
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        vectors.extend(await embeddings.embed(texts[start : start + batch_size], model))
    return vectors


async def enqueue_document(db: AsyncSession, document: Document) -> IndexingJob:
    job_id = deterministic_id("job", document.id, document.content_hash, PIPELINE_VERSION)
    job = await db.get(IndexingJob, job_id)
    if job is None:
        job = IndexingJob(
            id=job_id,
            project_id=document.project_id,
            dataset_id=document.dataset_id,
            document_id=document.id,
            status=JobStatus.QUEUED,
            stage=IndexingStage.QUEUED,
            attempt=0,
            pipeline_version=PIPELINE_VERSION,
            trace_id=new_id("qry"),
        )
        db.add(job)
    elif job.status == JobStatus.FAILED:
        job.status = JobStatus.QUEUED
        job.stage = IndexingStage.QUEUED
    outbox = await db.get(IndexingOutbox, job_id)
    if outbox is None:
        db.add(IndexingOutbox(job_id=job_id, attempts=0))
    elif job.status != JobStatus.SUCCEEDED:
        outbox.dispatched_at = None
        outbox.last_error = None
    document.status = DocumentStatus.QUEUED
    document.error_message = None
    await db.flush()
    return job


async def _stage(db: AsyncSession, job: IndexingJob, stage: IndexingStage) -> None:
    job.stage = stage
    db.add(
        IndexingStageEvent(
            id=deterministic_id("stage", job.id, job.attempt, stage.value),
            job_id=job.id,
            attempt=job.attempt,
            stage=stage,
        )
    )
    await db.commit()


def _runtime() -> tuple[EmbeddingProvider, VectorStore, str]:
    settings = get_settings()
    provider = create_embedding(
        settings.embedding_provider,
        PluginConfig(
            {"base_url": settings.embedding_base_url, "dimensions": settings.embedding_dimensions},
            {"api_key": SecretValue(settings.openai_api_key.get_secret_value())},
        ),
    )
    vectors = create_vector_store(
        PluginConfig(
            {
                "url": settings.qdrant_url,
                "collection": settings.qdrant_collection,
                "dimensions": settings.embedding_dimensions,
            }
        )
    )
    return provider, vectors, settings.embedding_model


async def run_ingestion(
    job_id: str,
    store: ObjectStore | None = None,
    embeddings: EmbeddingProvider | None = None,
    vectors: VectorStore | None = None,
    embedding_model: str | None = None,
) -> str:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        # Hold the row lock only while claiming the job, never during storage/model calls.
        job = await db.scalar(select(IndexingJob).where(IndexingJob.id == job_id).with_for_update())
        if job is None:
            raise ValueError("indexing job not found")
        if job.status == JobStatus.SUCCEEDED:
            return job.document_id
        if job.status == JobStatus.RUNNING:
            return job.document_id
        job.status, job.attempt = JobStatus.RUNNING, job.attempt + 1
        job.error_code = job.error_message = None
        document = await db.get(Document, job.document_id)
        if document is None:
            raise ValueError("document not found")
        await db.commit()

        try:
            await _stage(db, job, IndexingStage.READING)
            content = await (store or get_object_store()).download(document.object_key)
            document.status = DocumentStatus.PARSING
            await _stage(db, job, IndexingStage.PARSING)
            parsed = await asyncio.to_thread(
                default_registry().parse, document.mime_type, content, document.filename
            )
            document.status = DocumentStatus.CHUNKING
            await _stage(db, job, IndexingStage.CHUNKING)
            chunker = RecursiveTextChunker()
            chunks = await asyncio.to_thread(chunker.split, document.id, parsed.text)

            runtime_model = embedding_model
            if embeddings is None or vectors is None or runtime_model is None:
                default_embeddings, default_vectors, default_model = _runtime()
                embeddings = embeddings or default_embeddings
                vectors = vectors or default_vectors
                runtime_model = runtime_model or default_model
            document.status = DocumentStatus.EMBEDDING
            await _stage(db, job, IndexingStage.EMBEDDING)
            embedded = await embed_in_batches(
                embeddings, [item.text for item in chunks], runtime_model
            )
            if len(embedded) != len(chunks):
                raise ValueError("embedding response count mismatch")

            document.status = DocumentStatus.PERSISTING
            await _stage(db, job, IndexingStage.PERSISTING)
            points = [
                VectorPoint(
                    id=deterministic_point_id(
                        document.id, document.content_hash, PIPELINE_VERSION, item.index
                    ),
                    vector=vector,
                    project_id=str(document.project_id),
                    dataset_id=document.dataset_id,
                    document_id=document.id,
                    text=item.text,
                    pipeline_version=PIPELINE_VERSION,
                )
                for item, vector in zip(chunks, embedded, strict=True)
            ]
            await vectors.upsert(points)

            await db.execute(
                delete(Chunk).where(
                    Chunk.document_id == document.id, Chunk.pipeline_version == PIPELINE_VERSION
                )
            )
            for item in chunks:
                db.add(
                    Chunk(
                        # PostgreSQL and Qdrant share the same stable evidence identifier.
                        id=deterministic_point_id(
                            document.id, document.content_hash, PIPELINE_VERSION, item.index
                        ),
                        project_id=document.project_id,
                        dataset_id=document.dataset_id,
                        document_id=document.id,
                        pipeline_version=PIPELINE_VERSION,
                        chunk_index=item.index,
                        text=item.text,
                        token_count=item.token_count,
                        metadata_={
                            "start_char": item.start_char,
                            "end_char": item.end_char,
                            "parser": "parser-v1",
                            **parsed.metadata,
                        },
                    )
                )
            artifact = await db.get(
                IndexingArtifact,
                deterministic_id("artifact", job.id, "vectors", PIPELINE_VERSION),
            )
            if artifact is None:
                db.add(
                    IndexingArtifact(
                        id=deterministic_id("artifact", job.id, "vectors", PIPELINE_VERSION),
                        job_id=job.id,
                        document_id=document.id,
                        kind="vectors",
                        version=PIPELINE_VERSION,
                        metadata_={
                            "count": len(chunks),
                            "source_hash": document.content_hash,
                            "chunker": chunker.version,
                            "embedding_provider": embeddings.name,
                            "embedding_model": runtime_model,
                        },
                    )
                )
            await db.commit()
            await _stage(db, job, IndexingStage.COMPLETE)
            job.status, document.status = JobStatus.SUCCEEDED, DocumentStatus.PERSISTING
            document.error_message = None
            # Persist graph work in this transaction; the dispatcher publishes only committed rows.
            from app.graph_dispatch import enqueue_graph_extraction

            await enqueue_graph_extraction(db, document)
            await db.commit()
            return document.id
        except BaseException as exc:
            await db.rollback()
            job = await db.get(IndexingJob, job_id)
            document = await db.get(Document, job.document_id) if job else None
            error = sanitized_error(exc)
            if job:
                job.status, job.error_code, job.error_message = (
                    JobStatus.FAILED,
                    type(exc).__name__,
                    error,
                )
            if document:
                document.status, document.error_message = DocumentStatus.FAILED, error
            await db.commit()
            raise


def execute(job_id: str, store: ObjectStore | None = None) -> str:
    return runner.run(run_ingestion(job_id, store))


def is_transient(exc: BaseException) -> bool:
    return isinstance(exc, (*_TRANSIENT, SoftTimeLimitExceeded))
