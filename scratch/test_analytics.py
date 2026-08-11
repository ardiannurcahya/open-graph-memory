import asyncio
from uuid import UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select
from app.config import get_settings
from app.graph_models import RelationAssertion
from app.graph_analytics import analytics_relation, refresh_dataset_analytics

settings = get_settings()
engine = create_async_engine(settings.database_url)

async def test():
    async with AsyncSession(engine) as db:
        pid = UUID("e4f1167b-19c6-486c-99fa-9b68b805cb5c")
        ds_id = "ds_019fefb7-fa3d-7f40-85be-ca7ea329240c"
        rows = list(await db.execute(
            select(RelationAssertion.source_entity_id, RelationAssertion.target_entity_id, RelationAssertion.confidence)
            .where(RelationAssertion.project_id == pid, RelationAssertion.dataset_id == ds_id, analytics_relation())
        ))
        print("Filtered relations count:", len(rows))
        run = await refresh_dataset_analytics(db, pid, ds_id)
        run_id = run.id
        snap = run.snapshot_hash
        ec = run.entity_count
        rc = run.relation_count
        await db.commit()
        print("Run details:", run_id, snap, ec, rc)

asyncio.run(test())
