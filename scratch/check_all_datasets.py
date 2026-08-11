import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select, func
from app.config import get_settings
from app.graph_models import CanonicalEntity, RelationAssertion

settings = get_settings()
engine = create_async_engine(settings.database_url)

async def test():
    async with AsyncSession(engine) as db:
        rows = list(await db.execute(select(CanonicalEntity.dataset_id, func.count()).group_by(CanonicalEntity.dataset_id)))
        print("Entities by dataset:", rows)
        rel_rows = list(await db.execute(select(RelationAssertion.dataset_id, func.count()).group_by(RelationAssertion.dataset_id)))
        print("Relations by dataset:", rel_rows)

asyncio.run(test())
