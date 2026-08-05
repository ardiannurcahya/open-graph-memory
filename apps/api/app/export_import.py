"""Export/Import API for project data lifecycle."""

import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from open_graph_core.ids import uuid7
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ProjectContext, require_project
from app.dependencies import get_session
from app.models import (
    AgentMemoryAttempt,
    AgentMemoryEpisode,
    AgentMemoryEvidence,
    AgentMemoryOutcome,
)

router = APIRouter(prefix="/v1/projects", tags=["export-import"])
Project = Annotated[ProjectContext, Depends(require_project)]
Db = Annotated[AsyncSession, Depends(get_session)]


class ExportMetadata(BaseModel):
    project_id: str
    exported_at: str
    schema_version: str = "1.0.0"
    episode_count: int


class ExportPayload(BaseModel):
    metadata: ExportMetadata
    episodes: list[dict[str, object]]


class ImportInput(BaseModel):
    data: dict[str, object]
    owner_email: str = Field(min_length=1)
    new_project_id: str | None = None


class ImportResult(BaseModel):
    episodes_imported: int
    project_id: str


@router.get("/{project_id}/export")
async def export_project(project_id: str, project: Project, db: Db) -> StreamingResponse:
    episodes = list(
        await db.scalars(
            select(AgentMemoryEpisode).where(
                AgentMemoryEpisode.project_id == project.project_id
            )
        )
    )

    export_episodes = []
    for ep in episodes:
        attempts = list(
            await db.scalars(
                select(AgentMemoryAttempt)
                .where(AgentMemoryAttempt.episode_id == ep.id)
                .order_by(AgentMemoryAttempt.sequence)
            )
        )
        outcome = await db.scalar(
            select(AgentMemoryOutcome).where(AgentMemoryOutcome.episode_id == ep.id)
        )
        evidence = list(
            await db.scalars(
                select(AgentMemoryEvidence).where(AgentMemoryEvidence.episode_id == ep.id)
            )
        )

        ep_data = {
            "id": ep.id,
            "domain": ep.domain,
            "title": ep.title,
            "goal": ep.goal,
            "problem_signature": ep.problem_signature,
            "scope": ep.scope,
            "tags": ep.tags,
            "metadata": ep.metadata_,
            "status": ep.status,
            "feedback_score": ep.feedback_score,
            "created_at": ep.created_at.isoformat(),
            "updated_at": ep.updated_at.isoformat(),
            "attempts": [
                {
                    "id": a.id,
                    "sequence": a.sequence,
                    "hypothesis": a.hypothesis,
                    "actions": a.actions,
                    "result": a.result,
                    "notes": a.notes,
                    "metadata": a.metadata_,
                }
                for a in attempts
            ],
            "outcome": (
                {
                    "id": outcome.id,
                    "status": outcome.status,
                    "summary": outcome.summary,
                    "lesson": outcome.lesson,
                    "metrics": outcome.metrics,
                    "pattern_key": outcome.pattern_key,
                    "metadata": outcome.metadata_,
                }
                if outcome
                else None
            ),
            "evidence": [
                {"id": e.id, "reference": e.reference, "metadata": e.metadata_}
                for e in evidence
            ],
        }
        export_episodes.append(ep_data)

    payload = {
        "metadata": {
            "project_id": str(project.project_id),
            "exported_at": datetime.now(UTC).isoformat(),
            "schema_version": "1.0.0",
            "episode_count": len(export_episodes),
        },
        "episodes": export_episodes,
    }

    content = json.dumps(payload, indent=2, default=str)
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=project-{project_id}-export.json"},
    )


@router.post("/{project_id}/import", response_model=ImportResult)
async def import_project(
    project_id: str, body: ImportInput, project: Project, db: Db
) -> ImportResult:
    episodes_data = body.data.get("episodes", [])

    if not isinstance(episodes_data, list):
        raise HTTPException(400, "invalid import data: episodes must be an array")

    imported = 0
    for ep_data in episodes_data:
        existing = await db.scalar(
            select(AgentMemoryEpisode).where(
                AgentMemoryEpisode.project_id == project.project_id,
                AgentMemoryEpisode.id == ep_data.get("id"),
            )
        )
        if existing:
            continue

        episode = AgentMemoryEpisode(
            id=ep_data.get("id", f"mem_{uuid7()}"),
            project_id=project.project_id,
            domain=ep_data.get("domain", "custom"),
            title=ep_data.get("title", "Imported episode"),
            goal=ep_data.get("goal", ""),
            problem_signature=ep_data.get("problem_signature", ""),
            scope=ep_data.get("scope", {}),
            tags=ep_data.get("tags", []),
            metadata_=ep_data.get("metadata", {}),
            status=ep_data.get("status", "open"),
            feedback_score=ep_data.get("feedback_score", 0),
        )
        db.add(episode)

        for attempt_data in ep_data.get("attempts", []):
            attempt = AgentMemoryAttempt(
                id=attempt_data.get("id", f"att_{uuid7()}"),
                episode_id=episode.id,
                sequence=attempt_data.get("sequence", 1),
                hypothesis=attempt_data.get("hypothesis", ""),
                actions=attempt_data.get("actions", []),
                result=attempt_data.get("result", "success"),
                notes=attempt_data.get("notes"),
                metadata_=attempt_data.get("metadata", {}),
            )
            db.add(attempt)

        outcome_data = ep_data.get("outcome")
        if outcome_data:
            outcome = AgentMemoryOutcome(
                id=outcome_data.get("id", f"out_{uuid7()}"),
                episode_id=episode.id,
                status=outcome_data.get("status", "success"),
                summary=outcome_data.get("summary", ""),
                lesson=outcome_data.get("lesson"),
                metrics=outcome_data.get("metrics", {}),
                pattern_key=outcome_data.get("pattern_key", ""),
                metadata_=outcome_data.get("metadata", {}),
            )
            db.add(outcome)

        for evidence_data in ep_data.get("evidence", []):
            evidence = AgentMemoryEvidence(
                id=evidence_data.get("id", f"ev_{uuid7()}"),
                episode_id=episode.id,
                reference=evidence_data.get("reference", ""),
                metadata_=evidence_data.get("metadata", {}),
            )
            db.add(evidence)

        imported += 1

    await db.commit()
    return ImportResult(episodes_imported=imported, project_id=str(project.project_id))
