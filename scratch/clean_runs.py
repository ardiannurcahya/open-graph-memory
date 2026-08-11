import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import delete
from app.config import get_settings
from app.models import GraphAnalyticsRun

settings = get_settings()
engine = create_async_engine(settings.database_url)

async def test():
    async with AsyncSession(engine) as db:
        res = await db.execute(delete(GraphAnalyticsRun).where(GraphAnalyticsRun.relation_count == 0))
        await db.commit()
        print("Deleted stale runs count:", res.rowcount)

asyncio.run(test())
