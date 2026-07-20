import asyncio
import hashlib
import re

from celery.exceptions import SoftTimeLimitExceeded
from open_graph_core.ids import new_id
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.async_runner import runner
from app.chunking import RecursiveTextChunker
from app.config import get_settings
from app.db import engine
from app.graph_gc import cleanup_document_graph
from app.models import (
    Chunk,
    Document,
    DocumentStatus,
    IndexingJob,
    IndexingOutbox,
    IndexingStage,
    IndexingStageEvent,
    JobStatus,
)
from app.parsers import LiteParsePdfParser, default_registry
from app.storage import ObjectStore, get_object_store

PIPELINE_VERSION = (
    "ingestion-v6:parser-v5-liteparse-page-segments:"
    "recursive-v5-page-aware-exact-offsets"
)
_TRANSIENT = (TimeoutError, ConnectionError, OSError)


def deterministic_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("\x1f".join(map(str, parts)).encode()).hexdigest()[:32]
    return f"{prefix}_{digest}"


def sanitized_error(exc: BaseException) -> str:
    message = re.sub(r"(?i)(password|secret|token|key)=\S+", r"\1=[redacted]", str(exc))
    return " ".join(message.split())[:1000] or type(exc).__name__


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


async def run_ingestion(
    job_id: str,
    store: ObjectStore | None = None,
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
            settings = get_settings()
            pdf_parser = None
            if settings.pdf_parser == "liteparse":
                pdf_parser = LiteParsePdfParser(
                    ocr_mode=settings.liteparse_ocr_mode,
                    dpi=settings.liteparse_dpi,
                    max_pages=settings.liteparse_max_pages,
                    ocr_workers=settings.liteparse_ocr_workers,
                )
            registry = default_registry(pdf_parser)
            parsed = await asyncio.to_thread(
                registry.parse, document.mime_type, content, document.filename
            )
            document.status = DocumentStatus.CHUNKING
            await _stage(db, job, IndexingStage.CHUNKING)
            chunker = RecursiveTextChunker()
            chunks = await asyncio.to_thread(chunker.split_document, document.id, parsed)

            document.status = DocumentStatus.PERSISTING
            await _stage(db, job, IndexingStage.PERSISTING)
            await db.execute(
                delete(Chunk).where(
                    Chunk.project_id == document.project_id,
                    Chunk.dataset_id == document.dataset_id,
                    Chunk.document_id == document.id,
                )
            )
            await db.flush()
            await cleanup_document_graph(db, document.project_id, document.dataset_id, document.id)
            for item in chunks:
                db.add(
                    Chunk(
                        id=deterministic_id(
                            "chunk",
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
                            "chunker": chunker.version,
                            **parsed.metadata,
                            **item.metadata,
                        },
                    )
                )
            job.stage = IndexingStage.COMPLETE
            db.add(
                IndexingStageEvent(
                    id=deterministic_id(
                        "stage", job.id, job.attempt, IndexingStage.COMPLETE.value
                    ),
                    job_id=job.id,
                    attempt=job.attempt,
                    stage=IndexingStage.COMPLETE,
                )
            )
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
