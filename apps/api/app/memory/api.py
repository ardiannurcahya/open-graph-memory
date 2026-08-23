from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import desc, func, select

from app.auth import Project
from app.dependencies import Db
from app.idempotency import check_idempotency, store_idempotency
from app.memory.confidence import (
    apply_confidence_feedback,
    get_version_history,
    merge_memories,
    supersede_memory,
)
from app.memory.schemas import (
    AttemptInput,
    AttemptView,
    ConfidenceFeedbackInput,
    EpisodeInput,
    EpisodeStatus,
    EpisodeView,
    FeedbackInput,
    MemoryGraphView,
    OutcomeInput,
    OutcomeView,
    PatternSupersedeInput,
    PatternView,
    SearchResponse,
    SupersedeInput,
)
from app.memory.service import (
    bayesian_confidence,
    build_memory_graph,
    episode_view,
    fetch_search_results,
    is_promoted,
    memory_id,
    normalize_pattern_key,
    owned_episode,
    pattern_view,
    verifier_weight,
)
from app.memory.types import list_memory_types, validate_typed_content
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
from app.redaction import sanitize_input

router = APIRouter(prefix="/v1/agent-memory", tags=["agent-memory"])




@router.post("/episodes", response_model=EpisodeView, status_code=201)
async def create_episode(body: EpisodeInput, project: Project, db: Db) -> EpisodeView:
    if body.idempotency_key:
        existing_id = await check_idempotency(
            db, body.idempotency_key, str(project.project_id), "episode.create"
        )
        if existing_id:
            existing = await db.get(AgentMemoryEpisode, existing_id)
            if existing:
                return episode_view(existing)

    if body.content:
        validate_typed_content(body.type, body.content)
        body.content = sanitize_input(body.content)

    sanitized_metadata = sanitize_input(body.metadata)

    item = AgentMemoryEpisode(
        id=memory_id(),
        project_id=project.project_id,
        domain=body.domain,
        type=body.type,
        title=body.title,
        goal=body.goal,
        problem_signature=body.problem_signature,
        scope=body.scope,
        tags=body.tags,
        metadata_=sanitized_metadata,
        content=body.content,
        confidence=body.confidence,
        version=1,
        root_id=None,
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
                metadata_=sanitize_input(evidence.metadata),
            )
        )

    if body.idempotency_key:
        await store_idempotency(
            db,
            body.idempotency_key,
            str(project.project_id),
            "episode.create",
            item.id,
            {"id": item.id, "type": item.type},
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
    results = await fetch_search_results(
        db,
        project,
        q,
        problem_signature=problem_signature,
        repository=repository,
        environment=environment,
        include_inactive=include_inactive,
        limit=limit,
    )
    db.add(
        AgentMemoryRetrievalAudit(
            id=memory_id(),
            project_id=project.project_id,
            # Audit only stable retrieval identifiers; never retain query text,
            # recommended actions, lessons, or other user-provided content.
            query="[redacted]",
            results=[
                {
                    "episode_id": item.episode.id,
                    "pattern_key": item.pattern.pattern_key if item.pattern else None,
                }
                for item in results
            ],
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
    replacement = await owned_episode(db, project, body.superseding_episode_id, lock=True)
    if item.id == body.superseding_episode_id:
        raise HTTPException(422, "an episode cannot supersede itself")
    if item.status == "superseded" or replacement.status == "superseded":
        raise HTTPException(409, "superseded episodes cannot be superseded or reactivated")
    cursor = replacement
    visited = {item.id}
    while True:
        if cursor.id in visited:
            raise HTTPException(409, "episode supersession would create a cycle")
        visited.add(cursor.id)
        if not cursor.superseded_by_id:
            break
        cursor = await owned_episode(db, project, cursor.superseded_by_id, lock=True)
    item.status, item.superseded_by_id = "superseded", body.superseding_episode_id
    await db.commit()
    return episode_view(item)


@router.post("/patterns/{pattern_key}/feedback", response_model=PatternView)
async def feedback_pattern(
    pattern_key: str, body: FeedbackInput, project: Project, db: Db
) -> PatternView:
    pattern = await db.scalar(
        select(AgentMemoryPattern)
        .where(
            AgentMemoryPattern.project_id == project.project_id,
            AgentMemoryPattern.pattern_key == pattern_key,
        )
        .with_for_update()
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
    if pattern_key == body.superseding_pattern_key:
        raise HTTPException(422, "a pattern cannot supersede itself")
    pattern = await db.scalar(
        select(AgentMemoryPattern)
        .where(
            AgentMemoryPattern.project_id == project.project_id,
            AgentMemoryPattern.pattern_key == pattern_key,
        )
        .with_for_update()
    )
    replacement = await db.scalar(
        select(AgentMemoryPattern)
        .where(
            AgentMemoryPattern.project_id == project.project_id,
            AgentMemoryPattern.pattern_key == body.superseding_pattern_key,
        )
        .with_for_update()
    )
    if pattern is None or replacement is None:
        raise HTTPException(404, "agent memory pattern not found")
    if pattern.superseded_by_key or replacement.superseded_by_key:
        raise HTTPException(409, "superseded patterns cannot be superseded or re-promoted")
    cursor = replacement
    visited = {pattern.pattern_key}
    while True:
        if cursor.pattern_key in visited:
            raise HTTPException(409, "pattern supersession would create a cycle")
        visited.add(cursor.pattern_key)
        if not cursor.superseded_by_key:
            break
        next_cursor = await db.scalar(
            select(AgentMemoryPattern)
            .where(
                AgentMemoryPattern.project_id == project.project_id,
                AgentMemoryPattern.pattern_key == cursor.superseded_by_key,
            )
            .with_for_update()
        )
        if next_cursor is None:
            raise HTTPException(409, "pattern supersession chain is invalid")
        cursor = next_cursor
    pattern.promoted = False
    pattern.superseded_by_key = replacement.pattern_key
    await db.commit()
    return pattern_view(replacement)


@router.get("/graph", response_model=MemoryGraphView)
async def memory_graph(
    project: Project,
    db: Db,
    status: str | None = Query(None, description="Filter episodes by status"),
    domain: str | None = Query(None, description="Filter episodes by domain"),
    limit: int = Query(50, ge=1, le=200, description="Max episodes to include"),
) -> MemoryGraphView:
    return await build_memory_graph(db, project, status=status, domain=domain, limit=limit)


@router.delete("/episodes/{episode_id}", status_code=204)
async def hard_delete_episode(
    episode_id: str, project: Project, db: Db, mode: str = "archive"
) -> None:
    if mode not in ("archive", "invalidate", "hard"):
        raise HTTPException(400, "mode must be archive, invalidate, or hard")

    episode = await owned_episode(db, project, episode_id, lock=True)

    if mode == "archive":
        episode.status = "archived"
        episode.updated_at = datetime.now(UTC)
        await db.commit()
        return

    if mode == "invalidate":
        episode.status = "rejected"
        episode.updated_at = datetime.now(UTC)
        await db.commit()
        return

    from app.legal_hold import check_legal_hold

    try:
        await check_legal_hold(db, str(project.project_id), [episode_id])
    except Exception as err:
        raise HTTPException(423, "episode is under legal hold") from err

    await db.delete(episode)
    await db.commit()


@router.post("/episodes/{episode_id}/confidence", response_model=EpisodeView)
async def apply_confidence(
    episode_id: str, body: ConfidenceFeedbackInput, project: Project, db: Db
) -> EpisodeView:
    episode = await owned_episode(db, project, episode_id, lock=True)

    if body.kind in ("correct", "merge"):
        if body.kind == "merge":
            if not body.target_id:
                raise HTTPException(400, "merge requires target_id")
            episode = await merge_memories(
                db, episode, body.target_id, body.content, body.confidence
            )
        else:
            episode = await apply_confidence_feedback(
                db, episode, body.kind, body.content, body.confidence
            )
    elif body.kind == "supersede":
        if not body.target_id:
            raise HTTPException(400, "supersede requires target_id")
        episode = await supersede_memory(db, episode, body.target_id)
    else:
        episode = await apply_confidence_feedback(db, episode, body.kind, body.content)

    await db.commit()
    attempts = list(
        await db.scalars(
            select(AgentMemoryAttempt)
            .where(AgentMemoryAttempt.episode_id == episode.id)
            .order_by(AgentMemoryAttempt.sequence)
        )
    )
    return episode_view(episode, attempts)


@router.get("/episodes/{episode_id}/versions")
async def get_version_history_endpoint(
    episode_id: str, project: Project, db: Db
) -> list[dict[str, object]]:
    await owned_episode(db, project, episode_id)
    versions = await get_version_history(db, episode_id)
    return [
        {
            "id": v.id,
            "version": v.version,
            "content": v.content,
            "confidence": v.confidence,
            "superseded_by": v.superseded_by,
            "created_at": v.created_at.isoformat(),
        }
        for v in versions
    ]


@router.get("/types")
async def list_types() -> list[str]:
    return list_memory_types()
