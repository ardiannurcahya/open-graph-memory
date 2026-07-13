from datetime import UTC, datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Response, status
from open_graph_core.ids import new_id
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ProjectContext, require_project
from app.dependencies import get_session
from app.models import (
    MemoryAgent,
    MemoryFact,
    MemoryFactStatus,
    MemoryMessage,
    MemorySession,
    MemoryUser,
)

router = APIRouter(prefix="/v1", tags=["memory"])
Project = Annotated[ProjectContext, Depends(require_project)]
Db = Annotated[AsyncSession, Depends(get_session)]
MemoryScope = Literal["user", "agent", "session"]
MessageRole = Literal["system", "user", "assistant", "tool"]


class MemoryUserInput(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    metadata: dict[str, object] = Field(default_factory=dict)


class MemoryUserView(MemoryUserInput):
    id: str
    project_id: str


class MemoryAgentInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    metadata: dict[str, object] = Field(default_factory=dict)


class MemoryAgentView(MemoryAgentInput):
    id: str
    project_id: str


class MemorySessionInput(BaseModel):
    user_id: str
    agent_id: str
    title: str | None = Field(default=None, max_length=255)
    metadata: dict[str, object] = Field(default_factory=dict)


class MemorySessionView(MemorySessionInput):
    id: str
    project_id: str
    archived_at: datetime | None


class MemoryMessageInput(BaseModel):
    role: MessageRole
    content: str = Field(min_length=1, max_length=50_000)
    metadata: dict[str, object] = Field(default_factory=dict)


class MemoryMessageView(MemoryMessageInput):
    id: str
    project_id: str
    session_id: str
    created_at: datetime


class MemoryFactInput(BaseModel):
    scope: MemoryScope = "user"
    subject: str = Field(min_length=1, max_length=255)
    predicate: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=5000)
    confidence: int = Field(default=100, ge=0, le=100)
    metadata: dict[str, object] = Field(default_factory=dict)


class MemoryFactView(MemoryFactInput):
    id: str
    project_id: str
    user_id: str | None
    agent_id: str | None
    session_id: str | None
    content: str
    status: str
    supersedes_id: str | None
    source_message_id: str | None
    provenance: dict[str, object]
    valid_from: datetime
    valid_until: datetime | None
    deleted_at: datetime | None


class MessageBatchInput(BaseModel):
    messages: list[MemoryMessageInput] = Field(min_length=1, max_length=50)
    facts: list[MemoryFactInput] = Field(default_factory=list, max_length=50)


class MessageBatchView(BaseModel):
    messages: list[MemoryMessageView]
    facts: list[MemoryFactView]


def default_memory_scopes() -> list[MemoryScope]:
    return ["user", "agent", "session"]


class MemorySearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=5000)
    user_id: str | None = None
    agent_id: str | None = None
    session_id: str | None = None
    scopes: list[MemoryScope] = Field(default_factory=default_memory_scopes)
    limit: int = Field(default=10, ge=1, le=50)
    include_superseded: bool = False


class MemorySearchHit(MemoryFactView):
    score: float
    matched_terms: list[str]


def user_view(row: MemoryUser) -> MemoryUserView:
    return MemoryUserView(
        id=row.id,
        project_id=str(row.project_id),
        external_id=row.external_id,
        display_name=row.display_name,
        metadata=row.metadata_,
    )


def agent_view(row: MemoryAgent) -> MemoryAgentView:
    return MemoryAgentView(
        id=row.id,
        project_id=str(row.project_id),
        name=row.name,
        description=row.description,
        metadata=row.metadata_,
    )


def session_view(row: MemorySession) -> MemorySessionView:
    return MemorySessionView(
        id=row.id,
        project_id=str(row.project_id),
        user_id=row.user_id,
        agent_id=row.agent_id,
        title=row.title,
        metadata=row.metadata_,
        archived_at=row.archived_at,
    )


def message_view(row: MemoryMessage) -> MemoryMessageView:
    return MemoryMessageView(
        id=row.id,
        project_id=str(row.project_id),
        session_id=row.session_id,
        role=cast(MessageRole, row.role),
        content=row.content,
        metadata=row.metadata_,
        created_at=row.created_at,
    )


def fact_content(subject: str, predicate: str, value: str) -> str:
    return f"{subject} {predicate}: {value}"


def fact_view(row: MemoryFact) -> MemoryFactView:
    return MemoryFactView(
        id=row.id,
        project_id=str(row.project_id),
        user_id=row.user_id,
        agent_id=row.agent_id,
        session_id=row.session_id,
        scope=row.scope,  # type: ignore[arg-type]
        subject=row.subject,
        predicate=row.predicate,
        value=row.value,
        content=row.content,
        confidence=row.confidence,
        status=row.status.value,
        supersedes_id=row.supersedes_id,
        source_message_id=row.source_message_id,
        provenance=row.provenance,
        metadata=row.metadata_,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        deleted_at=row.deleted_at,
    )


async def require_user(db: AsyncSession, project_id: object, user_id: str) -> MemoryUser:
    row = await db.scalar(
        select(MemoryUser).where(MemoryUser.id == user_id, MemoryUser.project_id == project_id)
    )
    if row is None:
        raise HTTPException(404, "memory user not found")
    return row


async def require_agent(db: AsyncSession, project_id: object, agent_id: str) -> MemoryAgent:
    row = await db.scalar(
        select(MemoryAgent).where(MemoryAgent.id == agent_id, MemoryAgent.project_id == project_id)
    )
    if row is None:
        raise HTTPException(404, "memory agent not found")
    return row


async def require_session(db: AsyncSession, project_id: object, session_id: str) -> MemorySession:
    row = await db.scalar(
        select(MemorySession).where(
            MemorySession.id == session_id, MemorySession.project_id == project_id
        )
    )
    if row is None:
        raise HTTPException(404, "memory session not found")
    return row


async def persist_fact(
    db: AsyncSession,
    project_id: object,
    body: MemoryFactInput,
    *,
    user_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    source_message_id: str | None = None,
) -> MemoryFact:
    now = datetime.now(UTC)
    scoped_user = user_id if body.scope in {"user", "session"} else None
    scoped_agent = agent_id if body.scope in {"agent", "session"} else None
    scoped_session = session_id if body.scope == "session" else None
    active = await db.scalar(
        select(MemoryFact).where(
            MemoryFact.project_id == project_id,
            MemoryFact.scope == body.scope,
            MemoryFact.subject == body.subject,
            MemoryFact.predicate == body.predicate,
            MemoryFact.status == MemoryFactStatus.ACTIVE,
            MemoryFact.user_id.is_(scoped_user)
            if scoped_user is None
            else MemoryFact.user_id == scoped_user,
            MemoryFact.agent_id.is_(scoped_agent)
            if scoped_agent is None
            else MemoryFact.agent_id == scoped_agent,
            MemoryFact.session_id.is_(scoped_session)
            if scoped_session is None
            else MemoryFact.session_id == scoped_session,
        )
    )
    if active is not None and active.value == body.value:
        return active
    if active is not None:
        active.status = MemoryFactStatus.SUPERSEDED
        active.valid_until = now
    fact = MemoryFact(
        id=new_id("mem"),
        project_id=project_id,
        user_id=scoped_user,
        agent_id=scoped_agent,
        session_id=scoped_session,
        scope=body.scope,
        subject=body.subject,
        predicate=body.predicate,
        value=body.value,
        content=fact_content(body.subject, body.predicate, body.value),
        confidence=body.confidence,
        status=MemoryFactStatus.ACTIVE,
        supersedes_id=active.id if active is not None else None,
        source_message_id=source_message_id,
        provenance={
            "source": "message" if source_message_id else "api",
            "source_message_id": source_message_id,
        },
        metadata_=body.metadata,
        valid_from=now,
    )
    db.add(fact)
    return fact


@router.post("/memory/users", response_model=MemoryUserView, status_code=201)
async def create_user(body: MemoryUserInput, project: Project, db: Db) -> MemoryUserView:
    row = MemoryUser(
        id=new_id("usr"),
        project_id=project.project_id,
        external_id=body.external_id,
        display_name=body.display_name,
        metadata_=body.metadata,
    )
    db.add(row)
    await db.commit()
    return user_view(row)


@router.post("/memory/agents", response_model=MemoryAgentView, status_code=201)
async def create_agent(body: MemoryAgentInput, project: Project, db: Db) -> MemoryAgentView:
    row = MemoryAgent(
        id=new_id("agt"),
        project_id=project.project_id,
        name=body.name,
        description=body.description,
        metadata_=body.metadata,
    )
    db.add(row)
    await db.commit()
    return agent_view(row)


@router.post("/memory/sessions", response_model=MemorySessionView, status_code=201)
async def create_session(body: MemorySessionInput, project: Project, db: Db) -> MemorySessionView:
    await require_user(db, project.project_id, body.user_id)
    await require_agent(db, project.project_id, body.agent_id)
    row = MemorySession(
        id=new_id("ses"),
        project_id=project.project_id,
        user_id=body.user_id,
        agent_id=body.agent_id,
        title=body.title,
        metadata_=body.metadata,
    )
    db.add(row)
    await db.commit()
    return session_view(row)


@router.post(
    "/memory/sessions/{session_id}/messages", response_model=MessageBatchView, status_code=201
)
async def add_messages(
    session_id: str, body: MessageBatchInput, project: Project, db: Db
) -> MessageBatchView:
    session = await require_session(db, project.project_id, session_id)
    messages = [
        MemoryMessage(
            id=new_id("msg"),
            project_id=project.project_id,
            session_id=session_id,
            role=item.role,
            content=item.content,
            metadata_=item.metadata,
        )
        for item in body.messages
    ]
    db.add_all(messages)
    source_message_id = messages[-1].id if messages else None
    facts = [
        await persist_fact(
            db,
            project.project_id,
            fact,
            user_id=session.user_id,
            agent_id=session.agent_id,
            session_id=session.id,
            source_message_id=source_message_id,
        )
        for fact in body.facts
    ]
    await db.commit()
    return MessageBatchView(
        messages=[message_view(row) for row in messages], facts=[fact_view(row) for row in facts]
    )


@router.get("/memory/sessions/{session_id}/memory", response_model=list[MemoryFactView])
async def session_memory(session_id: str, project: Project, db: Db) -> list[MemoryFactView]:
    session = await require_session(db, project.project_id, session_id)
    rows = await db.scalars(
        select(MemoryFact)
        .where(
            MemoryFact.project_id == project.project_id,
            MemoryFact.status == MemoryFactStatus.ACTIVE,
            or_(
                MemoryFact.user_id == session.user_id,
                MemoryFact.agent_id == session.agent_id,
                MemoryFact.session_id == session.id,
            ),
        )
        .order_by(MemoryFact.created_at.desc())
    )
    return [fact_view(row) for row in rows]


@router.get("/memory/users/{user_id}/context", response_model=list[MemoryFactView])
async def user_context(
    user_id: str, project: Project, db: Db, limit: int = 20
) -> list[MemoryFactView]:
    await require_user(db, project.project_id, user_id)
    rows = await db.scalars(
        select(MemoryFact)
        .where(
            MemoryFact.project_id == project.project_id,
            MemoryFact.user_id == user_id,
            MemoryFact.status == MemoryFactStatus.ACTIVE,
        )
        .order_by(MemoryFact.created_at.desc())
        .limit(min(max(limit, 1), 50))
    )
    return [fact_view(row) for row in rows]


@router.post("/memory/search", response_model=list[MemorySearchHit])
async def search_memory(body: MemorySearchInput, project: Project, db: Db) -> list[MemorySearchHit]:
    stmt = select(MemoryFact).where(
        MemoryFact.project_id == project.project_id, MemoryFact.scope.in_(body.scopes)
    )
    if not body.include_superseded:
        stmt = stmt.where(MemoryFact.status == MemoryFactStatus.ACTIVE)
    if body.user_id:
        stmt = stmt.where(MemoryFact.user_id == body.user_id)
    if body.agent_id:
        stmt = stmt.where(MemoryFact.agent_id == body.agent_id)
    if body.session_id:
        stmt = stmt.where(MemoryFact.session_id == body.session_id)
    rows = list(await db.scalars(stmt.order_by(MemoryFact.created_at.desc()).limit(200)))
    terms = {term.lower() for term in body.query.split() if len(term) > 1}
    hits: list[MemorySearchHit] = []
    for row in rows:
        haystack = f"{row.subject} {row.predicate} {row.value} {row.content}".lower()
        matched = sorted(term for term in terms if term in haystack)
        if not matched:
            continue
        view = fact_view(row)
        hits.append(
            MemorySearchHit(
                **view.model_dump(), score=len(matched) / max(len(terms), 1), matched_terms=matched
            )
        )
    return sorted(hits, key=lambda hit: (hit.score, hit.valid_from), reverse=True)[: body.limit]


@router.delete("/memory/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: str, project: Project, db: Db) -> Response:
    row = await db.scalar(
        select(MemoryFact).where(
            MemoryFact.id == memory_id, MemoryFact.project_id == project.project_id
        )
    )
    if row is None:
        raise HTTPException(404, "memory fact not found")
    row.status = MemoryFactStatus.DELETED
    row.deleted_at = datetime.now(UTC)
    row.valid_until = row.deleted_at
    await db.commit()
    return Response(status_code=204)
