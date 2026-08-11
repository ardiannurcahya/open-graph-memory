import asyncio
from uuid import UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select
from app.config import get_settings
from app.graph_models import CanonicalEntity, RelationAssertion
from app.models import GraphAnalyticsRun, GraphAnalyticsMembership, GraphAnalyticsEntityMetric
from app.graph_helpers import supported_entity

settings = get_settings()
engine = create_async_engine(settings.database_url)

async def test():
    async with AsyncSession(engine) as db:
        pid = UUID("66ebb1d0-51b0-4aea-aee9-8e386b34e643")
        ds_id = "ds_019fefae-9745-7c1e-b544-aa1e7c0a3cff"

        latest = await db.scalar(
            select(GraphAnalyticsRun)
            .where(GraphAnalyticsRun.project_id == pid, GraphAnalyticsRun.dataset_id == ds_id)
            .order_by(GraphAnalyticsRun.created_at.desc(), GraphAnalyticsRun.id.desc())
            .limit(1)
        )
        print("Latest run:", latest.id if latest else None)

        base_entities = [
            CanonicalEntity.project_id == pid,
            CanonicalEntity.dataset_id == ds_id,
            supported_entity(),
        ]
        
        m_count = await db.scalar(
            select(GraphAnalyticsMembership).where(GraphAnalyticsMembership.run_id == latest.id).limit(5)
        )
        print("Sample membership in run:", m_count)

        rows = list(await db.execute(
            select(CanonicalEntity, GraphAnalyticsMembership.community_id, GraphAnalyticsEntityMetric)
            .join(
                GraphAnalyticsMembership,
                (GraphAnalyticsMembership.entity_id == CanonicalEntity.id)
                & (GraphAnalyticsMembership.run_id == latest.id)
                & (GraphAnalyticsMembership.level == 0),
            )
            .join(
                GraphAnalyticsEntityMetric,
                (GraphAnalyticsEntityMetric.entity_id == CanonicalEntity.id)
                & (GraphAnalyticsEntityMetric.run_id == latest.id),
            )
            .where(*base_entities)
            .limit(10)
        ))
        print("Node metric rows count:", len(rows))

asyncio.run(test())
