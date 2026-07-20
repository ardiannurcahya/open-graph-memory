import re
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from open_graph_core.ids import uuid7
from pydantic import BaseModel, Field
from sqlalchemy import case, desc, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.auth import ProjectContext, require_project
from app.dependencies import get_session
from app.models import (
    AgentMemoryAttempt,
    AgentMemoryEpisode,
    AgentMemoryEvidence,
    AgentMemoryOutcome,
    AgentMemoryPattern,
    AgentMemoryPatternMember,
    AgentMemoryRetrievalAudit,
    AgentMemoryVerifier,
)

router = APIRouter(prefix="/v1/agent-memory", tags=["agent-memory"])
Project = Annotated[ProjectContext, Depends(require_project)]
Db = Annotated[AsyncSession, Depends(get_session)]
Domain = Literal["engineering", "trading", "research", "operations", "custom"]
EpisodeStatus = Literal["open", "active", "degraded", "superseded", "rejected"]
OutcomeStatus = Literal["success", "failed", "partial", "cancelled"]
VerifierKind = Literal["ci", "runtime", "test", "build", "self_report", "custom"]


class EvidenceInput(BaseModel):
    reference: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class EpisodeInput(BaseModel):
    domain: Domain
    title: str = Field(min_length=1, max_length=255)
    goal: str = Field(min_length=1)
    problem_signature: str = Field(min_length=1, max_length=512)
    scope: dict[str, object] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    evidence: list[EvidenceInput] = Field(default_factory=list)


class AttemptInput(BaseModel):
    hypothesis: str = Field(min_length=1)
    actions: list[object] = Field(default_factory=list)
    result: Literal["success", "failed", "partial"]
    notes: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class VerifierInput(BaseModel):
    kind: VerifierKind
    name: str = Field(min_length=1, max_length=255)
    status: str = Field(min_length=1, max_length=32)
    command: str | None = None
    artifact_uri: str | None = None
    metrics: dict[str, object] = Field(default_factory=dict)


class OutcomeInput(BaseModel):
    status: OutcomeStatus
    summary: str = Field(min_length=1)
    lesson: str | None = None
    verifiers: list[VerifierInput] = Field(default_factory=list)
    metrics: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    pattern_key: str | None = Field(default=None, max_length=255)


class FeedbackInput(BaseModel):
    score: int = Field(ge=-1, le=1)


class SupersedeInput(BaseModel):
    superseding_episode_id: str


class PatternSupersedeInput(BaseModel):
    superseding_pattern_key: str = Field(min_length=1, max_length=255)


class AttemptView(AttemptInput):
    id: str
    sequence: int


class EpisodeView(BaseModel):
    id: str
    project_id: str
    domain: Domain
    title: str
    goal: str
    problem_signature: str
    scope: dict[str, object]
    tags: list[str]
    metadata: dict[str, object]
    status: EpisodeStatus
    feedback_score: int
    superseded_by_id: str | None
    attempts: list[AttemptView] = Field(default_factory=list)


class PatternView(BaseModel):
    pattern_key: str
    verified_outcomes: int
    weighted_successes: float
    weighted_total: float
    confidence: float
    promoted: bool


class OutcomeView(BaseModel):
    id: str
    status: OutcomeStatus
    pattern: PatternView


class SearchResult(BaseModel):
    episode: EpisodeView
    pattern: PatternView | None
    recommended_actions: list[object]
    lesson: str | None
    scope_match: bool


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


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
    return (successes + 1.0) / (total + 2.0)


def is_promoted(verified_outcomes: int, confidence: float) -> bool:
    return verified_outcomes >= 3 and confidence >= 0.7


def episode_view(
    item: AgentMemoryEpisode, attempts: list[AgentMemoryAttempt] | None = None
) -> EpisodeView:
    return EpisodeView(
        id=item.id,
        project_id=str(item.project_id),
        domain=cast(Domain, item.domain),
        title=item.title,
        goal=item.goal,
        problem_signature=item.problem_signature,
        scope=item.scope,
        tags=item.tags,
        metadata=item.metadata_,
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


@router.post("/episodes", response_model=EpisodeView, status_code=201)
async def create_episode(body: EpisodeInput, project: Project, db: Db) -> EpisodeView:
    item = AgentMemoryEpisode(
        id=memory_id(),
        project_id=project.project_id,
        domain=body.domain,
        title=body.title,
        goal=body.goal,
        problem_signature=body.problem_signature,
        scope=body.scope,
        tags=body.tags,
        metadata_=body.metadata,
        status="open",
        feedback_score=0,
    )
    db.add(item)
    for evidence in body.evidence:
        db.add(
            AgentMemoryEvidence(
                id=memory_id(),
                episode_id=item.id,
                reference=evidence.reference,
                metadata_=evidence.metadata,
            )
        )
    await db.commit()
    return episode_view(item)


@router.get("/episodes", response_model=list[EpisodeView])
async def list_episodes(
    project: Project,
    db: Db,
    status: EpisodeStatus | None = None,
    limit: int = Query(25, ge=1, le=100),
) -> list[EpisodeView]:
    statement = select(AgentMemoryEpisode).where(
        AgentMemoryEpisode.project_id == project.project_id
    )
    if status:
        statement = statement.where(AgentMemoryEpisode.status == status)
    return [
        episode_view(row)
        for row in await db.scalars(
            statement.order_by(desc(AgentMemoryEpisode.created_at)).limit(limit)
        )
    ]


@router.get("/episodes/{episode_id}", response_model=EpisodeView)
async def get_episode(episode_id: str, project: Project, db: Db) -> EpisodeView:
    item = await owned_episode(db, project, episode_id)
    attempts = list(
        await db.scalars(
            select(AgentMemoryAttempt)
            .where(AgentMemoryAttempt.episode_id == item.id)
            .order_by(AgentMemoryAttempt.sequence)
        )
    )
    return episode_view(item, attempts)


@router.post("/episodes/{episode_id}/attempts", response_model=AttemptView, status_code=201)
async def append_attempt(
    episode_id: str, body: AttemptInput, project: Project, db: Db
) -> AttemptView:
    item = await owned_episode(db, project, episode_id, lock=True)
    if item.status not in {"open", "active", "degraded"}:
        raise HTTPException(409, "attempts require an open, active, or degraded episode")
    sequence = (
        await db.scalar(
            select(func.coalesce(func.max(AgentMemoryAttempt.sequence), 0) + 1).where(
                AgentMemoryAttempt.episode_id == item.id
            )
        )
    ) or 1
    item.status = (
        "active"
        if body.result == "success"
        else "degraded"
        if body.result == "failed"
        else "active"
    )
    attempt = AgentMemoryAttempt(
        id=memory_id(),
        episode_id=item.id,
        sequence=sequence,
        hypothesis=body.hypothesis,
        actions=body.actions,
        result=body.result,
        notes=body.notes,
        metadata_=body.metadata,
    )
    db.add(attempt)
    await db.commit()
    return AttemptView(id=attempt.id, sequence=sequence, **body.model_dump())


@router.post("/episodes/{episode_id}/outcomes", response_model=OutcomeView, status_code=201)
async def record_outcome(
    episode_id: str, body: OutcomeInput, project: Project, db: Db
) -> OutcomeView:
    episode = await owned_episode(db, project, episode_id, lock=True)
    if episode.status in {"superseded", "rejected"}:
        raise HTTPException(409, "cannot finalize a superseded or rejected episode")
    if await db.scalar(
        select(AgentMemoryOutcome.id).where(AgentMemoryOutcome.episode_id == episode.id)
    ):
        raise HTTPException(409, "episode already has a finalized outcome")
    key = body.pattern_key or normalize_pattern_key(episode.problem_signature)
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(f"{project.project_id}:{key}", 0)))
    )
    pattern = await db.scalar(
        select(AgentMemoryPattern)
        .where(
            AgentMemoryPattern.project_id == project.project_id,
            AgentMemoryPattern.pattern_key == key,
        )
        .with_for_update()
    )
    if pattern is None:
        pattern = AgentMemoryPattern(
            id=memory_id(),
            project_id=project.project_id,
            pattern_key=key,
            verified_outcomes=0,
            weighted_successes=0.0,
            weighted_total=0.0,
            confidence=0.5,
            promoted=False,
        )
        db.add(pattern)
    quality = verifier_weight(body.verifiers)
    pattern.weighted_total += quality
    pattern.weighted_successes += quality * (
        1.0 if body.status == "success" else 0.5 if body.status == "partial" else 0.0
    )
    pattern.verified_outcomes += int(quality > 0)
    pattern.confidence = bayesian_confidence(pattern.weighted_successes, pattern.weighted_total)
    pattern.promoted = is_promoted(pattern.verified_outcomes, pattern.confidence)
    outcome = AgentMemoryOutcome(
        id=memory_id(),
        episode_id=episode.id,
        status=body.status,
        summary=body.summary,
        lesson=body.lesson,
        metrics=body.metrics,
        metadata_=body.metadata,
        pattern_key=key,
    )
    db.add(outcome)
    db.add(AgentMemoryPatternMember(pattern_id=pattern.id, outcome_id=outcome.id))
    for verifier in body.verifiers:
        db.add(
            AgentMemoryVerifier(
                id=memory_id(),
                outcome_id=outcome.id,
                kind=verifier.kind,
                name=verifier.name,
                status=verifier.status,
                command=verifier.command,
                artifact_uri=verifier.artifact_uri,
                metrics=verifier.metrics,
            )
        )
    await db.commit()
    return OutcomeView(id=outcome.id, status=body.status, pattern=pattern_view(pattern))


@router.get("/search", response_model=SearchResponse)
async def search(
    project: Project,
    db: Db,
    q: str = Query(min_length=1),
    problem_signature: str | None = None,
    repository: str | None = None,
    environment: str | None = None,
    include_inactive: bool = False,
    limit: int = Query(25, ge=1, le=100),
) -> SearchResponse:
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
    results: list[SearchResult] = []
    for episode, pattern in rows:
        outcome = await db.scalar(
            select(AgentMemoryOutcome).where(AgentMemoryOutcome.episode_id == episode.id)
        )
        attempt = await db.scalar(
            select(AgentMemoryAttempt)
            .where(
                AgentMemoryAttempt.episode_id == episode.id, AgentMemoryAttempt.result == "success"
            )
            .order_by(desc(AgentMemoryAttempt.sequence))
        )
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
    db.add(
        AgentMemoryRetrievalAudit(
            id=memory_id(),
            project_id=project.project_id,
            query=q,
            results=[item.model_dump(mode="json") for item in results],
        )
    )
    await db.commit()
    return SearchResponse(query=q, results=results)


@router.post("/episodes/{episode_id}/feedback", response_model=EpisodeView)
async def feedback(episode_id: str, body: FeedbackInput, project: Project, db: Db) -> EpisodeView:
    item = await owned_episode(db, project, episode_id, lock=True)
    item.feedback_score += body.score
    await db.commit()
    return episode_view(item)


@router.post("/episodes/{episode_id}/supersede", response_model=EpisodeView)
async def supersede_episode(
    episode_id: str, body: SupersedeInput, project: Project, db: Db
) -> EpisodeView:
    item = await owned_episode(db, project, episode_id, lock=True)
    await owned_episode(db, project, body.superseding_episode_id)
    if item.id == body.superseding_episode_id:
        raise HTTPException(422, "an episode cannot supersede itself")
    item.status, item.superseded_by_id = "superseded", body.superseding_episode_id
    await db.commit()
    return episode_view(item)


@router.post("/patterns/{pattern_key}/feedback", response_model=PatternView)
async def feedback_pattern(
    pattern_key: str, body: FeedbackInput, project: Project, db: Db
) -> PatternView:
    pattern = await db.scalar(
        select(AgentMemoryPattern).where(
            AgentMemoryPattern.project_id == project.project_id,
            AgentMemoryPattern.pattern_key == pattern_key,
        )
    )
    if pattern is None:
        raise HTTPException(404, "agent memory pattern not found")
    pattern.weighted_successes = max(0.0, pattern.weighted_successes + body.score * 0.1)
    pattern.confidence = bayesian_confidence(pattern.weighted_successes, pattern.weighted_total)
    pattern.promoted = is_promoted(pattern.verified_outcomes, pattern.confidence)
    await db.commit()
    return pattern_view(pattern)


@router.post("/patterns/{pattern_key}/supersede", response_model=PatternView)
async def supersede_pattern(
    pattern_key: str, body: PatternSupersedeInput, project: Project, db: Db
) -> PatternView:
    pattern = await db.scalar(
        select(AgentMemoryPattern).where(
            AgentMemoryPattern.project_id == project.project_id,
            AgentMemoryPattern.pattern_key == pattern_key,
        )
    )
    replacement = await db.scalar(
        select(AgentMemoryPattern).where(
            AgentMemoryPattern.project_id == project.project_id,
            AgentMemoryPattern.pattern_key == body.superseding_pattern_key,
        )
    )
    if pattern is None or replacement is None:
        raise HTTPException(404, "agent memory pattern not found")
    pattern.promoted = False
    await db.commit()
    return pattern_view(replacement)
