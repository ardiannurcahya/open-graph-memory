"""Durable, evidence-grounded community reports."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from open_graph_contracts import PluginConfig, SecretValue
from open_graph_core.ids import new_id
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db import engine
from app.graph_models import CanonicalEntity, GraphEvidence, RelationAssertion, ReviewState
from app.ingestion import sanitized_error
from app.models import (
    Chunk,
    CommunityReport,
    CommunityReportEvidence,
    CommunityReportJob,
    CommunityReportOutbox,
    CommunityReportStatus,
    GraphAnalyticsCommunity,
    GraphAnalyticsMembership,
    GraphAnalyticsRun,
)
from app.plugin_registry import create_chat
from app.providers import ChatProvider


class ReportPayload(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1)
    key_points: list[str] = Field(default_factory=list, max_length=20)
    evidence_chunk_ids: list[str] = Field(min_length=1)


def community_report_input_hash(
    analytics_run_id: str, community_id: str, settings: Settings
) -> str:
    payload = {
        "analytics_run_id": analytics_run_id,
        "community_id": community_id,
        "max_chunks": settings.community_report_max_chunks,
        "max_members": settings.community_report_max_members,
        "max_relations": settings.community_report_max_relations,
        "model": settings.resolved_community_report_model,
        "prompt_version": settings.community_report_prompt_version,
        "provider": settings.resolved_community_report_provider,
        "report_version": settings.community_report_version,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def enqueue_community_report_jobs(
    db: AsyncSession,
    project_id: Any,
    dataset_id: str,
    analytics_run: GraphAnalyticsRun,
    settings: Settings,
) -> list[CommunityReportJob]:
    communities = list(
        await db.scalars(
            select(GraphAnalyticsCommunity.community_id)
            .where(GraphAnalyticsCommunity.run_id == analytics_run.id)
            .order_by(GraphAnalyticsCommunity.community_id)
        )
    )
    jobs = []
    for community_id in communities:
        input_hash = community_report_input_hash(analytics_run.id, community_id, settings)
        job = await db.scalar(
            select(CommunityReportJob).where(
                CommunityReportJob.analytics_run_id == analytics_run.id,
                CommunityReportJob.community_id == community_id,
                CommunityReportJob.input_hash == input_hash,
            )
        )
        if job is None:
            job = CommunityReportJob(
                id=new_id("grj"),
                project_id=project_id,
                dataset_id=dataset_id,
                analytics_run_id=analytics_run.id,
                community_id=community_id,
                status=CommunityReportStatus.QUEUED,
                max_attempts=settings.community_report_max_attempts,
                provider=settings.resolved_community_report_provider,
                model=settings.resolved_community_report_model,
                report_version=settings.community_report_version,
                prompt_version=settings.community_report_prompt_version,
                input_hash=input_hash,
            )
            db.add(job)
        if await db.get(CommunityReportOutbox, job.id) is None:
            db.add(CommunityReportOutbox(job_id=job.id))
        jobs.append(job)
    await db.flush()
    return jobs


async def _context(db: AsyncSession, job: CommunityReportJob) -> tuple[list[str], str]:
    member_ids = list(
        await db.scalars(
            select(GraphAnalyticsMembership.entity_id)
            .where(
                GraphAnalyticsMembership.run_id == job.analytics_run_id,
                GraphAnalyticsMembership.community_id == job.community_id,
            )
            .order_by(GraphAnalyticsMembership.entity_id)
            .limit(get_settings().community_report_max_members)
        )
    )
    members = (
        list(
            await db.scalars(
                select(CanonicalEntity)
                .where(CanonicalEntity.id.in_(member_ids))
                .order_by(CanonicalEntity.canonical_name)
            )
        )
        if member_ids
        else []
    )
    relations = (
        list(
            await db.scalars(
                select(RelationAssertion)
                .where(
                    RelationAssertion.project_id == job.project_id,
                    RelationAssertion.dataset_id == job.dataset_id,
                    RelationAssertion.review_state != ReviewState.REJECTED,
                    RelationAssertion.source_entity_id.in_(member_ids),
                    RelationAssertion.target_entity_id.in_(member_ids),
                )
                .order_by(RelationAssertion.id)
                .limit(get_settings().community_report_max_relations)
            )
        )
        if member_ids
        else []
    )
    relation_ids = [r.id for r in relations]
    chunks = (
        list(
            await db.scalars(
                select(Chunk)
                .join(GraphEvidence, GraphEvidence.chunk_id == Chunk.id)
                .where(
                    GraphEvidence.relation_id.in_(relation_ids),
                    GraphEvidence.project_id == job.project_id,
                    GraphEvidence.dataset_id == job.dataset_id,
                )
                .distinct()
                .order_by(Chunk.id)
                .limit(get_settings().community_report_max_chunks)
            )
        )
        if relation_ids
        else []
    )
    allowed = [chunk.id for chunk in chunks]
    body = {
        "community_id": job.community_id,
        "members": [{"id": m.id, "name": m.canonical_name, "type": m.entity_type} for m in members],
        "relations": [
            {
                "id": r.id,
                "source": r.source_entity_id,
                "type": r.relation_type,
                "target": r.target_entity_id,
            }
            for r in relations
        ],
        "evidence": [{"chunk_id": c.id, "text": c.text} for c in chunks],
    }
    instruction = (
        "Return ONLY strict JSON: {title:string,summary:string,key_points:[string],"
        "evidence_chunk_ids:[string]}. Ground every claim only in supplied evidence. "
        "evidence_chunk_ids must be nonempty IDs from evidence.\n"
    )
    prompt = instruction + json.dumps(body, sort_keys=True)
    return allowed, prompt


def _provider(job: CommunityReportJob) -> ChatProvider:
    settings = get_settings()
    return create_chat(
        settings.resolved_community_report_provider,
        PluginConfig(
            {"base_url": settings.chat_base_url, "dimensions": settings.embedding_dimensions},
            {"api_key": SecretValue(settings.openai_api_key.get_secret_value())},
        ),
    )


async def _generate(job: CommunityReportJob, prompt: str, allowed: list[str]) -> ReportPayload:
    provider = _provider(job)
    result = await provider.chat(
        [
            {"role": "system", "content": "Evidence-grounded report generator."},
            {"role": "user", "content": prompt},
        ],
        job.model,
    )
    for repair in range(2):
        try:
            payload = ReportPayload.model_validate(json.loads(result.text))
            if not set(payload.evidence_chunk_ids).issubset(allowed):
                raise ValueError("response uses unknown evidence_chunk_ids")
            return payload
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            if repair:
                raise ValueError(f"invalid report JSON: {exc}") from exc
            result = await provider.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "Repair response. Return only valid JSON. "
                            "Use only allowed evidence IDs: " + json.dumps(allowed)
                        ),
                    },
                    {"role": "user", "content": result.text},
                ],
                job.model,
            )
    raise AssertionError("unreachable")


async def execute_community_report_job(job_id: str) -> str:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as db:
        job = await db.scalar(
            select(CommunityReportJob).where(CommunityReportJob.id == job_id).with_for_update()
        )
        if job is None or job.status == CommunityReportStatus.SUCCEEDED:
            return job_id
        if (
            job.status == CommunityReportStatus.RUNNING
            and job.lease_expires_at
            and job.lease_expires_at > now
        ):
            return job_id
        if job.attempts >= job.max_attempts:
            job.status = CommunityReportStatus.FAILED
            await db.commit()
            return job_id
        job.status = CommunityReportStatus.RUNNING
        job.attempts += 1
        job.lease_expires_at = now + timedelta(
            seconds=get_settings().community_report_lease_seconds
        )
        job.error_message = None
        await db.commit()
    try:
        async with factory() as db:
            job = await db.get(CommunityReportJob, job_id)
            assert job
            allowed, prompt = await _context(db, job)
            payload = await _generate(job, prompt, allowed)
            report = await db.scalar(
                select(CommunityReport).where(CommunityReport.job_id == job.id).with_for_update()
            )
            if report is None:
                report = CommunityReport(
                    id=new_id("grr"),
                    job_id=job.id,
                    project_id=job.project_id,
                    dataset_id=job.dataset_id,
                    analytics_run_id=job.analytics_run_id,
                    community_id=job.community_id,
                    title=payload.title,
                    summary=payload.summary,
                    key_points=payload.key_points,
                    metadata_={
                        "provider": job.provider,
                        "model": job.model,
                        "prompt_version": job.prompt_version,
                    },
                )
                db.add(report)
                await db.flush()
                for rank, chunk_id in enumerate(payload.evidence_chunk_ids):
                    db.add(
                        CommunityReportEvidence(report_id=report.id, chunk_id=chunk_id, rank=rank)
                    )
            job.status = CommunityReportStatus.SUCCEEDED
            job.lease_expires_at = None
            job.error_message = None
            await db.commit()
    except Exception as exc:
        async with factory() as db:
            job = await db.get(CommunityReportJob, job_id)
            if job:
                job.error_message = sanitized_error(exc)
                job.lease_expires_at = None
                if job.attempts >= job.max_attempts:
                    job.status = CommunityReportStatus.FAILED
                else:
                    job.status = CommunityReportStatus.QUEUED
                    job.next_attempt_at = datetime.now(UTC) + timedelta(
                        seconds=min(60, 2**job.attempts)
                    )
                    outbox = await db.get(CommunityReportOutbox, job.id)
                    if outbox:
                        outbox.published_at = None
                await db.commit()
        raise
    return job_id


async def dispatch_pending_community_report_jobs(limit: int = 100) -> int:
    from app.worker import celery_app

    now = datetime.now(UTC)
    sent = 0
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        rows = list(
            await db.scalars(
                select(CommunityReportOutbox)
                .join(CommunityReportJob)
                .where(
                    CommunityReportOutbox.published_at.is_(None),
                    CommunityReportJob.status == CommunityReportStatus.QUEUED,
                    CommunityReportJob.next_attempt_at <= now,
                )
                .order_by(CommunityReportOutbox.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.attempts += 1
            try:
                celery_app.send_task("community.generate_report", args=[row.job_id])
            except Exception as exc:
                row.last_error = sanitized_error(exc)
            else:
                row.published_at = now
                row.last_error = None
                sent += 1
        await db.commit()
    return sent


async def reconcile_community_report_jobs(limit: int = 100) -> int:
    now = datetime.now(UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        jobs = list(
            await db.scalars(
                select(CommunityReportJob)
                .where(
                    CommunityReportJob.status == CommunityReportStatus.RUNNING,
                    CommunityReportJob.lease_expires_at < now,
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for job in jobs:
            job.status = CommunityReportStatus.QUEUED
            job.lease_expires_at = None
            job.next_attempt_at = now
            outbox = await db.get(CommunityReportOutbox, job.id)
            if outbox:
                outbox.published_at = None
        await db.commit()
        return len(jobs)
