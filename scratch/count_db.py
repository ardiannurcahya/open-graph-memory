import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select, func
from app.config import get_settings
from app.graph_models import CanonicalEntity, RelationAssertion

settings = get_settings()
engine = create_async_engine(settings.database_url)

async def test():
    async with AsyncSession(engine) as db:
        ec = await db.scalar(select(func.count()).select_from(CanonicalEntity))
        rc = await db.scalar(select(func.count()).select_from(RelationAssertion))
        print("Canonical Entities in DB:", ec)
        print("Relation Assertions in DB:", rc)

asyncio.run(test())
