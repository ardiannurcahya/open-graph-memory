"""Scoring, view assembly, and ownership lookup for agent memory."""

import re
from typing import Literal, cast

from fastapi import HTTPException
from open_graph_core.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ProjectContext
from app.memory.schemas import (
    AttemptView,
    Domain,
    EpisodeStatus,
    EpisodeView,
    PatternView,
    VerifierInput,
)
from app.models import AgentMemoryAttempt, AgentMemoryEpisode, AgentMemoryPattern


def normalize_pattern_key(signature: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", signature.lower()).strip("-")
    return normalized[:255] or "unspecified"


def memory_id() -> str:
    return f"mem_{uuid7()}"


def verifier_weight(verifiers: list[VerifierInput]) -> float:
    weights = {
        "ci": 1.0,
        "runtime": 1.0,
        "test": 0.6,
        "build": 0.6,
        "self_report": 0.2,
        "custom": 0.2,
    }
    passing = [
        weights[item.kind]
        for item in verifiers
        if item.status.lower() in {"passed", "success", "verified"}
    ]
    return max(passing, default=0.0)


def bayesian_confidence(successes: float, total: float) -> float:
    # Feedback and legacy rows can be inconsistent; confidence remains a probability.
    bounded_total = max(0.0, total)
    bounded_successes = min(bounded_total, max(0.0, successes))
    return (bounded_successes + 1.0) / (bounded_total + 2.0)


def is_promoted(verified_outcomes: int, confidence: float) -> bool:
    return verified_outcomes >= 3 and confidence >= 0.7


def episode_view(
    item: AgentMemoryEpisode, attempts: list[AgentMemoryAttempt] | None = None
) -> EpisodeView:
    return EpisodeView(
        id=item.id,
        project_id=str(item.project_id),
        domain=cast(Domain, item.domain),
        type=item.type,
        title=item.title,
        goal=item.goal,
        problem_signature=item.problem_signature,
        scope=item.scope,
        tags=item.tags,
        metadata=item.metadata_,
        content=item.content,
        confidence=item.confidence,
        version=item.version,
        root_id=item.root_id,
        status=cast(EpisodeStatus, item.status),
        feedback_score=item.feedback_score,
        superseded_by_id=item.superseded_by_id,
        attempts=[
            AttemptView(
                id=a.id,
                sequence=a.sequence,
                hypothesis=a.hypothesis,
                actions=a.actions,
                result=cast(Literal["success", "failed", "partial"], a.result),
                notes=a.notes,
                metadata=a.metadata_,
            )
            for a in attempts or []
        ],
    )


def pattern_view(item: AgentMemoryPattern) -> PatternView:
    return PatternView(
        pattern_key=item.pattern_key,
        verified_outcomes=item.verified_outcomes,
        weighted_successes=item.weighted_successes,
        weighted_total=item.weighted_total,
        confidence=item.confidence,
        promoted=item.promoted,
    )


async def owned_episode(
    db: AsyncSession, project: ProjectContext, episode_id: str, lock: bool = False
) -> AgentMemoryEpisode:
    statement = select(AgentMemoryEpisode).where(
        AgentMemoryEpisode.id == episode_id, AgentMemoryEpisode.project_id == project.project_id
    )
    item = await db.scalar(statement.with_for_update() if lock else statement)
    if item is None:
        raise HTTPException(404, "agent memory episode not found")
    return item
