import hashlib
import json
from uuid import UUID

from open_graph_core.ids import new_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import (
    CommunityReportJob,
    CommunityReportOutbox,
    CommunityReportStatus,
    GraphAnalyticsCommunity,
    GraphAnalyticsRun,
)


def community_report_input_hash(
    analytics_run_id: str,
    community_id: str,
    settings: Settings,
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
    project_id: UUID,
    dataset_id: str,
    analytics_run: GraphAnalyticsRun,
    settings: Settings,
) -> list[CommunityReportJob]:
    """Create missing community jobs and transactional outbox rows for one analytics snapshot."""
    communities = list(
        await db.scalars(
            select(GraphAnalyticsCommunity.community_id)
            .where(GraphAnalyticsCommunity.run_id == analytics_run.id)
            .order_by(GraphAnalyticsCommunity.community_id)
        )
    )
    jobs: list[CommunityReportJob] = []
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
        outbox = await db.get(CommunityReportOutbox, job.id)
        if outbox is None:
            db.add(CommunityReportOutbox(job_id=job.id))
        jobs.append(job)
    await db.flush()
    return jobs
