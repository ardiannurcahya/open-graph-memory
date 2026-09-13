"""Export/Import API for project data lifecycle."""

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from open_graph_core.ids import uuid7
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth import Project
from app.dependencies import Db
from app.models import (
    AgentMemoryAttempt,
    AgentMemoryEpisode,
    AgentMemoryEvidence,
    AgentMemoryOutcome,
)

router = APIRouter(prefix="/v1/projects", tags=["export-import"])


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
            select(AgentMemoryEpisode).where(AgentMemoryEpisode.project_id == project.project_id)
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
                {"id": e.id, "reference": e.reference, "metadata": e.metadata_} for e in evidence
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
        raw_id = ep_data.get("id")
        ep_id = raw_id or f"mem_{uuid7()}"
        remap_ids = False
        if raw_id:
            existing = await db.get(AgentMemoryEpisode, raw_id)
            if existing:
                if str(existing.project_id) == str(project.project_id):
                    continue
                ep_id = f"mem_{uuid7()}"
                remap_ids = True

        episode = AgentMemoryEpisode(
            id=ep_id,
            project_id=project.project_id,
            domain=ep_data.get("domain", "custom"),
            type=ep_data.get("type", "custom"),
            title=ep_data.get("title", "Imported episode"),
            goal=ep_data.get("goal", ""),
            problem_signature=ep_data.get("problem_signature", ""),
            scope=ep_data.get("scope", {}),
            tags=ep_data.get("tags", []),
            metadata_=ep_data.get("metadata", {}),
            content=ep_data.get("content"),
            confidence=ep_data.get("confidence", 0.5),
            version=ep_data.get("version", 1),
            status=ep_data.get("status", "open"),
            feedback_score=ep_data.get("feedback_score", 0),
        )
        db.add(episode)

        for attempt_data in ep_data.get("attempts", []):
            raw_att_id = attempt_data.get("id")
            att_id = f"att_{uuid7()}" if (remap_ids or not raw_att_id) else raw_att_id
            if not remap_ids and raw_att_id:
                if await db.get(AgentMemoryAttempt, raw_att_id):
                    att_id = f"att_{uuid7()}"
            attempt = AgentMemoryAttempt(
                id=att_id,
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
            raw_out_id = outcome_data.get("id")
            out_id = f"out_{uuid7()}" if (remap_ids or not raw_out_id) else raw_out_id
            if not remap_ids and raw_out_id:
                if await db.get(AgentMemoryOutcome, raw_out_id):
                    out_id = f"out_{uuid7()}"
            outcome = AgentMemoryOutcome(
                id=out_id,
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
            raw_ev_id = evidence_data.get("id")
            ev_id = f"ev_{uuid7()}" if (remap_ids or not raw_ev_id) else raw_ev_id
            if not remap_ids and raw_ev_id:
                if await db.get(AgentMemoryEvidence, raw_ev_id):
                    ev_id = f"ev_{uuid7()}"
            evidence = AgentMemoryEvidence(
                id=ev_id,
                episode_id=episode.id,
                reference=evidence_data.get("reference", ""),
                metadata_=evidence_data.get("metadata", {}),
            )
            db.add(evidence)

        imported += 1

    await db.commit()
    return ImportResult(episodes_imported=imported, project_id=str(project.project_id))
