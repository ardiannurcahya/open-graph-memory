"""Shared Pytest Async Fixtures for apps/api tests."""

import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from app.dependencies import get_session
from app.main import app
from app.models import ApiKey, Base, Project
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(TSVECTOR, "sqlite")
def compile_tsvector_sqlite(type_, compiler, **kw):
    return "TEXT"


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def register_sqlite_functions(dbapi_connection, connection_record):
        dbapi_connection.create_function(
            "to_tsvector", 2, lambda lang, text: text or "", deterministic=True
        )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:

        async def _override_get_session():
            async with session_factory() as req_session:
                yield req_session

        app.dependency_overrides[get_session] = _override_get_session
        yield session
        app.dependency_overrides.clear()

    await engine.dispose()


@pytest_asyncio.fixture
async def project(session: AsyncSession) -> Project:
    item = Project(id=uuid.uuid4(), name="Test Project")
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@pytest_asyncio.fixture
async def api_key(session: AsyncSession, project: Project) -> ApiKey:
    import hashlib

    key_prefix = "test_key_prefix_"
    full_key = key_prefix + "test"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    item = ApiKey(
        id=uuid.uuid4(),
        project_id=project.id,
        name="Test API Key",
        key_prefix=key_prefix,
        key_hash=key_hash,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item
