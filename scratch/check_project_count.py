import asyncio
from uuid import UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select, func
from app.config import get_settings
from app.graph_models import CanonicalEntity, RelationAssertion

settings = get_settings()
engine = create_async_engine(settings.database_url)

async def test():
    async with AsyncSession(engine) as db:
        pid = UUID("e4f1167b-19c6-486c-99fa-9b68b805cb5c")
        ec = await db.scalar(select(func.count()).where(CanonicalEntity.project_id == pid))
        rc = await db.scalar(select(func.count()).where(RelationAssertion.project_id == pid))
        print("Canonical Entities in project:", ec)
        print("Relation Assertions in project:", rc)

asyncio.run(test())
