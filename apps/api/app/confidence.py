"""Confidence feedback system for memory management."""

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AgentMemoryEpisode,
    AgentMemoryVersion,
)

FeedbackKind = Literal["confirm", "reject", "correct", "supersede", "merge", "stale", "verified"]


CONFIDENCE_DELTAS: dict[str, float] = {
    "confirm": 0.10,
    "reject": -1.0,
    "stale": -0.20,
    "verified": 1.0,
}


def calculate_confidence(current: float, kind: str) -> float:
    if kind == "confirm":
        return min(1.0, current + 0.10)
    elif kind == "reject":
        return 0.0
    elif kind == "stale":
        return max(0.0, current - 0.20)
    elif kind == "verified":
        return 1.0
    return current


def get_status_for_feedback(kind: str) -> str | None:
    if kind == "reject":
        return "rejected"
    elif kind == "stale":
        return "degraded"
    return None


async def apply_confidence_feedback(
    db: AsyncSession,
    episode: AgentMemoryEpisode,
    kind: FeedbackKind,
    content: dict[str, Any] | None = None,
    confidence: float | None = None,
) -> AgentMemoryEpisode:
    now = datetime.now(UTC)

    if kind == "confirm":
        episode.confidence = calculate_confidence(episode.confidence, kind)
        episode.feedback_score += 1

    elif kind == "reject":
        episode.confidence = 0.0
        episode.status = "rejected"
        episode.feedback_score -= 1

    elif kind == "stale":
        episode.confidence = calculate_confidence(episode.confidence, kind)
        episode.status = "degraded"

    elif kind == "verified":
        if not content:
            raise HTTPException(400, "verified feedback requires verification evidence")
        episode.confidence = 1.0
        episode.feedback_score += 2

    elif kind == "correct":
        if not content:
            raise HTTPException(400, "correct feedback requires new content")
        new_version = AgentMemoryVersion(
            id=f"ver_{episode.id}_v{episode.version}",
            episode_id=episode.id,
            version=episode.version,
            content=episode.content or {},
            confidence=episode.confidence,
        )
        db.add(new_version)

        episode.content = content
        episode.confidence = confidence if confidence is not None else episode.confidence
        episode.version += 1

    elif kind == "merge":
        raise HTTPException(400, "merge requires target_id parameter")

    elif kind == "supersede":
        raise HTTPException(400, "supersede requires target_id parameter")

    episode.updated_at = now
    return episode


async def merge_memories(
    db: AsyncSession,
    source: AgentMemoryEpisode,
    target_id: str,
    content: dict[str, Any] | None = None,
    confidence: float | None = None,
) -> AgentMemoryEpisode:

    target = await db.get(AgentMemoryEpisode, target_id)
    if not target:
        raise HTTPException(404, "target episode not found")
    if target.project_id != source.project_id:
        raise HTTPException(400, "target must be in same project")
    if target.type != source.type:
        raise HTTPException(400, "merge inputs must have the same type")
    if target.id == source.id:
        raise HTTPException(400, "cannot merge with itself")

    now = datetime.now(UTC)

    new_version = AgentMemoryVersion(
        id=f"ver_{source.id}_v{source.version}",
        episode_id=source.id,
        version=source.version,
        content=source.content or {},
        confidence=source.confidence,
    )
    db.add(new_version)

    source.content = content or target.content
    source.confidence = (
        confidence if confidence is not None
        else max(source.confidence, target.confidence)
    )
    source.version += 1
    source.updated_at = now

    target.status = "superseded"
    target.superseded_by_id = source.id
    target.updated_at = now

    return source


async def supersede_memory(
    db: AsyncSession,
    current: AgentMemoryEpisode,
    superseding_id: str,
) -> AgentMemoryEpisode:
    superseding = await db.get(AgentMemoryEpisode, superseding_id)
    if not superseding:
        raise HTTPException(404, "superseding episode not found")
    if superseding.project_id != current.project_id:
        raise HTTPException(400, "superseding episode must be in same project")
    if superseding.id == current.id:
        raise HTTPException(400, "cannot supersede itself")

    now = datetime.now(UTC)

    current.status = "superseded"
    current.superseded_by_id = superseding_id
    current.updated_at = now

    return current


async def get_version_history(
    db: AsyncSession, episode_id: str
) -> list[AgentMemoryVersion]:
    result = await db.scalars(
        select(AgentMemoryVersion)
        .where(AgentMemoryVersion.episode_id == episode_id)
        .order_by(AgentMemoryVersion.version)
    )
    return list(result)
