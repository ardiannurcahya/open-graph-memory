import asyncio
import hashlib
from uuid import uuid4
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.config import get_settings
from app.graph_models import CanonicalEntity, ReviewState
from app.models import Project, Dataset, DatasetStatus

settings = get_settings()
engine = create_async_engine(settings.database_url)

async def test():
    async with AsyncSession(engine) as db:
        pid = uuid4()
        ds_id = f"ds_debug_{uuid4().hex[:6]}"
        db.add(Project(id=pid, name="Debug Proj"))
        await db.flush()
        db.add(Dataset(id=ds_id, project_id=pid, name="Debug DS", status=DatasetStatus.ACTIVE))
        await db.flush()

        raw_id = "code_python_str_a8092ce08102"
        eid = "ce_" + hashlib.sha256(raw_id.encode()).hexdigest()[:32]
        now = datetime.now(UTC)
        stmt = pg_insert(CanonicalEntity).values(
            id=eid,
            project_id=pid,
            dataset_id=ds_id,
            canonical_name=raw_id,
            normalized_name="ref::" + raw_id.lower()[:500],
            entity_type="code.symbol",
            confidence=1.0,
            review_state=ReviewState.APPROVED,
            created_at=now,
            updated_at=now,
        ).on_conflict_do_nothing()
        await db.execute(stmt)
        await db.commit()
        print("Successfully inserted stub canonical entity:", eid)

asyncio.run(test())
