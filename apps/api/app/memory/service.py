"""Scoring, view assembly, and ownership lookup for agent memory."""

import re
from typing import Literal, cast

from fastapi import HTTPException
from open_graph_core.ids import uuid7
from sqlalchemy import case, desc, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.auth import ProjectContext
from app.memory.schemas import (
    AttemptView,
    Domain,
    EpisodeStatus,
    EpisodeView,
    MemoryGraphEdge,
    MemoryGraphNode,
    MemoryGraphView,
    PatternView,
    SearchResult,
    VerifierInput,
)
from app.models import (
    AgentMemoryAttempt,
    AgentMemoryEpisode,
    AgentMemoryEvidence,
    AgentMemoryOutcome,
    AgentMemoryPattern,
    AgentMemoryVerifier,
)


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


async def fetch_search_results(
    db: AsyncSession,
    project: ProjectContext,
    q: str,
    problem_signature: str | None,
    repository: str | None,
    environment: str | None,
    include_inactive: bool,
    limit: int,
) -> list[SearchResult]:
    query = func.plainto_tsquery("simple", q)
    rank = func.ts_rank_cd(AgentMemoryEpisode.search_vector, query)
    signature_bonus = case(
        (AgentMemoryEpisode.problem_signature == (problem_signature or q), 2.0), else_=0.0
    )
    promoted_bonus = case((AgentMemoryPattern.promoted.is_(True), 0.5), else_=0.0)
    scope_bonus: ColumnElement[float] = literal(0.0)
    if repository:
        scope_bonus += case(
            (
                AgentMemoryEpisode.scope["repository"].astext == repository,
                0.25,
            ),
            else_=0.0,
        )
    if environment:
        scope_bonus += case(
            (
                AgentMemoryEpisode.scope["environment"].astext == environment,
                0.25,
            ),
            else_=0.0,
        )
    statement = (
        select(AgentMemoryEpisode, AgentMemoryPattern)
        .outerjoin(AgentMemoryOutcome, AgentMemoryOutcome.episode_id == AgentMemoryEpisode.id)
        .outerjoin(
            AgentMemoryPattern,
            (AgentMemoryPattern.project_id == AgentMemoryEpisode.project_id)
            & (AgentMemoryPattern.pattern_key == AgentMemoryOutcome.pattern_key),
        )
        .where(
            AgentMemoryEpisode.project_id == project.project_id,
            AgentMemoryEpisode.search_vector.op("@@")(query),
        )
    )
    if not include_inactive:
        statement = statement.where(AgentMemoryEpisode.status.not_in(["superseded", "rejected"]))
    if problem_signature:
        statement = statement.where(AgentMemoryEpisode.problem_signature == problem_signature)
    if repository:
        statement = statement.where(AgentMemoryEpisode.scope["repository"].astext == repository)
    if environment:
        statement = statement.where(AgentMemoryEpisode.scope["environment"].astext == environment)
    rows = list(
        (
            await db.execute(
                statement.order_by(
                    desc(
                        rank
                        + signature_bonus
                        + scope_bonus
                        + promoted_bonus
                        + func.coalesce(AgentMemoryPattern.confidence, 0)
                    ),
                    desc(AgentMemoryEpisode.created_at),
                ).limit(limit)
            )
        ).all()
    )

    # Fallback to fuzzy substring / ILIKE if strict tsquery returned no results
    if not rows:
        from sqlalchemy import or_

        keywords = [w.strip() for w in q.split() if len(w.strip()) > 1]
        if keywords:
            ilike_clauses = [
                or_(
                    AgentMemoryEpisode.title.ilike(f"%{kw}%"),
                    AgentMemoryEpisode.goal.ilike(f"%{kw}%"),
                    AgentMemoryEpisode.problem_signature.ilike(f"%{kw}%"),
                )
                for kw in keywords[:5]
            ]
            fallback_stmt = (
                select(AgentMemoryEpisode, AgentMemoryPattern)
                .outerjoin(
                    AgentMemoryOutcome,
                    AgentMemoryOutcome.episode_id == AgentMemoryEpisode.id,
                )
                .outerjoin(
                    AgentMemoryPattern,
                    (AgentMemoryPattern.project_id == AgentMemoryEpisode.project_id)
                    & (AgentMemoryPattern.pattern_key == AgentMemoryOutcome.pattern_key),
                )
                .where(
                    AgentMemoryEpisode.project_id == project.project_id,
                    or_(*ilike_clauses),
                )
            )
            if not include_inactive:
                fallback_stmt = fallback_stmt.where(
                    AgentMemoryEpisode.status.not_in(["superseded", "rejected"])
                )
            fallback_exec = await db.execute(
                fallback_stmt.order_by(desc(AgentMemoryEpisode.created_at)).limit(limit)
            )
            rows = list(fallback_exec.all())

    episode_ids = [episode.id for episode, _pattern in rows]
    outcomes = {
        item.episode_id: item
        for item in await db.scalars(
            select(AgentMemoryOutcome).where(AgentMemoryOutcome.episode_id.in_(episode_ids))
        )
    }
    attempts_by_episode: dict[str, AgentMemoryAttempt] = {}
    for item in await db.scalars(
        select(AgentMemoryAttempt)
        .where(
            AgentMemoryAttempt.episode_id.in_(episode_ids),
            AgentMemoryAttempt.result == "success",
        )
        .order_by(AgentMemoryAttempt.episode_id, desc(AgentMemoryAttempt.sequence))
    ):
        attempts_by_episode.setdefault(item.episode_id, item)
    results: list[SearchResult] = []
    for episode, pattern in rows:
        outcome = outcomes.get(episode.id)
        attempt = attempts_by_episode.get(episode.id)
        scope_match = (not repository or episode.scope.get("repository") == repository) and (
            not environment or episode.scope.get("environment") == environment
        )
        results.append(
            SearchResult(
                episode=episode_view(episode),
                pattern=pattern_view(pattern) if pattern else None,
                recommended_actions=attempt.actions if attempt else [],
                lesson=outcome.lesson if outcome else None,
                scope_match=scope_match,
            )
        )
    return results


async def build_memory_graph(
    db: AsyncSession,
    project: ProjectContext,
    status: str | None,
    domain: str | None,
    limit: int,
) -> MemoryGraphView:
    statement = (
        select(AgentMemoryEpisode)
        .where(AgentMemoryEpisode.project_id == project.project_id)
        .order_by(desc(AgentMemoryEpisode.updated_at))
        .limit(limit)
    )
    if status:
        statement = statement.where(AgentMemoryEpisode.status == status)
    if domain:
        statement = statement.where(AgentMemoryEpisode.domain == domain)
    episodes = (await db.scalars(statement)).all()
    episode_ids = [e.id for e in episodes]

    nodes: list[MemoryGraphNode] = []
    edges: list[MemoryGraphEdge] = []
    stats = {
        "episodes": 0,
        "attempts": 0,
        "outcomes": 0,
        "patterns": 0,
        "verifiers": 0,
        "evidence": 0,
    }

    seen_episodes: set[str] = set()
    seen_attempts: set[str] = set()
    seen_patterns: set[str] = set()
    seen_verifiers: set[str] = set()
    seen_evidence: set[str] = set()

    for ep in episodes:
        if ep.id in seen_episodes:
            continue
        seen_episodes.add(ep.id)
        nodes.append(
            MemoryGraphNode(
                id=ep.id,
                type="episode",
                label=ep.title,
                status=ep.status,
                domain=ep.domain,
                metadata={
                    "goal": ep.goal,
                    "problem_signature": ep.problem_signature,
                    "feedback_score": ep.feedback_score,
                    "tags": ep.tags,
                    "created_at": ep.created_at.isoformat() if ep.created_at else None,
                },
            )
        )
        stats["episodes"] += 1

        if ep.superseded_by_id and ep.superseded_by_id in set(episode_ids):
            edges.append(
                MemoryGraphEdge(
                    id=f"sup-{ep.id}-{ep.superseded_by_id}",
                    source=ep.id,
                    target=ep.superseded_by_id,
                    type="supersedes",
                )
            )

    if not episode_ids:
        return MemoryGraphView(nodes=nodes, edges=edges, stats=stats)

    attempts = (
        await db.scalars(
            select(AgentMemoryAttempt)
            .where(AgentMemoryAttempt.episode_id.in_(episode_ids))
            .order_by(AgentMemoryAttempt.episode_id, AgentMemoryAttempt.sequence)
        )
    ).all()
    for att in attempts:
        if att.id in seen_attempts:
            continue
        seen_attempts.add(att.id)
        nodes.append(
            MemoryGraphNode(
                id=att.id,
                type="attempt",
                label=f"#{att.sequence}: {att.hypothesis[:60]}",
                status=att.result,
                metadata={
                    "hypothesis": att.hypothesis,
                    "result": att.result,
                    "notes": att.notes,
                    "sequence": att.sequence,
                },
            )
        )
        edges.append(
            MemoryGraphEdge(
                id=f"eat-{att.episode_id}-{att.id}",
                source=att.episode_id,
                target=att.id,
                type="has_attempt",
            )
        )
        stats["attempts"] += 1

    outcomes = (
        await db.scalars(
            select(AgentMemoryOutcome).where(AgentMemoryOutcome.episode_id.in_(episode_ids))
        )
    ).all()
    pattern_keys: set[str] = set()
    outcome_ids = [o.id for o in outcomes]
    for out in outcomes:
        nodes.append(
            MemoryGraphNode(
                id=out.id,
                type="outcome",
                label=f"{out.status}: {out.summary[:60]}",
                status=out.status,
                metadata={
                    "summary": out.summary,
                    "lesson": out.lesson,
                    "pattern_key": out.pattern_key,
                    "created_at": out.created_at.isoformat() if out.created_at else None,
                },
            )
        )
        edges.append(
            MemoryGraphEdge(
                id=f"eou-{out.episode_id}-{out.id}",
                source=out.episode_id,
                target=out.id,
                type="has_outcome",
            )
        )
        stats["outcomes"] += 1
        if out.pattern_key:
            pattern_keys.add(out.pattern_key)

    if pattern_keys:
        patterns = (
            await db.scalars(
                select(AgentMemoryPattern).where(
                    AgentMemoryPattern.project_id == project.project_id,
                    AgentMemoryPattern.pattern_key.in_(list(pattern_keys)),
                )
            )
        ).all()
        pattern_map = {p.pattern_key: p for p in patterns}
        for pat in patterns:
            if pat.id in seen_patterns:
                continue
            seen_patterns.add(pat.id)
            nodes.append(
                MemoryGraphNode(
                    id=pat.id,
                    type="pattern",
                    label=pat.pattern_key,
                    metadata={
                        "pattern_key": pat.pattern_key,
                        "confidence": pat.confidence,
                        "verified_outcomes": pat.verified_outcomes,
                        "promoted": pat.promoted,
                    },
                )
            )
            stats["patterns"] += 1

        for out in outcomes:
            if out.pattern_key and out.pattern_key in pattern_map:
                pat = pattern_map[out.pattern_key]
                edges.append(
                    MemoryGraphEdge(
                        id=f"omp-{out.id}-{pat.id}",
                        source=out.id,
                        target=pat.id,
                        type="matches_pattern",
                    )
                )

    if outcome_ids:
        verifiers = (
            await db.scalars(
                select(AgentMemoryVerifier).where(AgentMemoryVerifier.outcome_id.in_(outcome_ids))
            )
        ).all()
        for ver in verifiers:
            if ver.id in seen_verifiers:
                continue
            seen_verifiers.add(ver.id)
            nodes.append(
                MemoryGraphNode(
                    id=ver.id,
                    type="verifier",
                    label=f"{ver.kind}: {ver.name}",
                    status=ver.status,
                    metadata={
                        "kind": ver.kind,
                        "name": ver.name,
                        "command": ver.command,
                        "artifact_uri": ver.artifact_uri,
                    },
                )
            )
            edges.append(
                MemoryGraphEdge(
                    id=f"ovr-{ver.outcome_id}-{ver.id}",
                    source=ver.outcome_id,
                    target=ver.id,
                    type="verified_by",
                )
            )
            stats["verifiers"] += 1

    evidence = (
        await db.scalars(
            select(AgentMemoryEvidence).where(AgentMemoryEvidence.episode_id.in_(episode_ids))
        )
    ).all()
    for ev in evidence:
        if ev.id in seen_evidence:
            continue
        seen_evidence.add(ev.id)
        nodes.append(
            MemoryGraphNode(
                id=ev.id,
                type="evidence",
                label=ev.reference[:80],
                metadata={**ev.metadata_, "reference": ev.reference},
            )
        )
        edges.append(
            MemoryGraphEdge(
                id=f"eev-{ev.episode_id}-{ev.id}",
                source=ev.episode_id,
                target=ev.id,
                type="has_evidence",
            )
        )
        stats["evidence"] += 1

    return MemoryGraphView(nodes=nodes, edges=edges, stats=stats)
