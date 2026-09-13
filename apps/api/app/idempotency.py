"""Idempotency key management for duplicate prevention."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IdempotencyKey

IDEMPOTENCY_TTL_HOURS = 24


def compute_result_hash(data: dict[str, Any]) -> str:
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


async def check_idempotency(
    db: AsyncSession,
    key: str,
    project_id: str | UUID,
    operation: str,
) -> str | None:
    p_uuid = UUID(str(project_id))
    existing = await db.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.key == key,
            IdempotencyKey.project_id == p_uuid,
            IdempotencyKey.operation == operation,
        )
    )
    if existing:
        created_at = (
            existing.created_at.replace(tzinfo=UTC)
            if existing.created_at.tzinfo is None
            else existing.created_at
        )
        cutoff = datetime.now(UTC) - timedelta(hours=IDEMPOTENCY_TTL_HOURS)
        if created_at >= cutoff:
            return existing.resource_id
        await db.delete(existing)
    return None


async def store_idempotency(
    db: AsyncSession,
    key: str,
    project_id: str | UUID,
    operation: str,
    resource_id: str,
    result_data: dict[str, Any],
) -> None:
    p_uuid = UUID(str(project_id))
    result_hash = compute_result_hash(result_data)
    entry = IdempotencyKey(
        key=key,
        project_id=p_uuid,
        operation=operation,
        resource_id=resource_id,
        result_hash=result_hash,
    )
    db.add(entry)


async def cleanup_expired_keys(db: AsyncSession) -> int:
    cutoff = datetime.now(UTC) - timedelta(hours=IDEMPOTENCY_TTL_HOURS)
    result = await db.execute(delete(IdempotencyKey).where(IdempotencyKey.created_at < cutoff))
    rowcount = getattr(result, "rowcount", 0)
    return cast(int, rowcount)
