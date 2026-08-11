import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select
from app.config import get_settings
from app.graph_models import CanonicalEntity

settings = get_settings()
engine = create_async_engine(settings.database_url)

async def test():
    async with AsyncSession(engine) as db:
        ent = await db.scalar(select(CanonicalEntity).where(CanonicalEntity.dataset_id == 'ds_019fefae-9745-7c1e-b544-aa1e7c0a3cff').limit(1))
        print("Project ID:", ent.project_id)

asyncio.run(test())
