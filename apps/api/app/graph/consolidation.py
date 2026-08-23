import hashlib
import json
from dataclasses import dataclass

import httpx
from open_graph_core.extraction import find_evidence
from pydantic import BaseModel, ConfigDict, Field

from app.models import Chunk


class ConsolidationRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    source_type: str
    target: str
    target_type: str
    type: str
    evidence_chunk_id: str
    quote: str
    confidence: float = Field(ge=0, le=1)


class ConsolidationAlias(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonical_name: str
    entity_type: str
    alias: str
    evidence_chunk_id: str
    quote: str
    confidence: float = Field(ge=0, le=1)


class ConsolidationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relations: list[ConsolidationRelation] = Field(default_factory=list)
    aliases: list[ConsolidationAlias] = Field(default_factory=list)


@dataclass(frozen=True)
class ConsolidationInput:
    snapshot_hash: str
    payload: list[dict[str, object]]


def build_input(
    chunks: list[Chunk], raw_extractions: dict[str, dict[str, object]]
) -> ConsolidationInput:
    payload: list[dict[str, object]] = []
    identity: list[dict[str, object]] = []
    for chunk in sorted(chunks, key=lambda item: (item.chunk_index, item.id)):
        metadata = chunk.metadata_ or {}
        raw = raw_extractions.get(chunk.id)
        if raw is None:
            continue
        item = {
            "chunk_id": chunk.id,
            "chunk_index": chunk.chunk_index,
            "section_path": metadata.get("section_path", []),
            "page_number": metadata.get("page_number"),
            "entities": raw.get("entities", []),
            "relations": raw.get("relations", []),
        }
        payload.append(item)
        identity.append(
            {
                "chunk_id": chunk.id,
                "chunk_index": chunk.chunk_index,
                "text_hash": hashlib.sha256(chunk.text.encode()).hexdigest(),
                "raw_hash": hashlib.sha256(
                    json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "section_path": metadata.get("section_path", []),
                "page_number": metadata.get("page_number"),
            }
        )
    snapshot_hash = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ConsolidationInput(snapshot_hash, payload)


def validate_output(output: ConsolidationOutput, chunks: dict[str, Chunk]) -> None:
    seen: set[tuple[str, str, str]] = set()
    for relation_item in output.relations:
        chunk = chunks.get(relation_item.evidence_chunk_id)
        if chunk is None:
            raise ValueError("consolidation evidence references an unknown chunk")
        if not relation_item.quote or find_evidence(chunk.text, relation_item.quote) is None:
            raise ValueError("consolidation evidence quote is not an exact chunk substring")
        if (
            relation_item.source not in relation_item.quote
            or relation_item.target not in relation_item.quote
        ):
            raise ValueError("relation evidence must directly mention both endpoints")
        key = (
            relation_item.evidence_chunk_id,
            relation_item.quote,
            type(relation_item).__name__,
        )
        if key in seen:
            raise ValueError("consolidation output has duplicate evidence references")
        seen.add(key)
    for alias_item in output.aliases:
        chunk = chunks.get(alias_item.evidence_chunk_id)
        if chunk is None:
            raise ValueError("consolidation evidence references an unknown chunk")
        if not alias_item.quote or find_evidence(chunk.text, alias_item.quote) is None:
            raise ValueError("consolidation evidence quote is not an exact chunk substring")
        if (
            alias_item.alias not in alias_item.quote
            or alias_item.canonical_name not in alias_item.quote
        ):
            raise ValueError("alias evidence must directly mention alias and canonical name")
        key = (alias_item.evidence_chunk_id, alias_item.quote, type(alias_item).__name__)
        if key in seen:
            raise ValueError("consolidation output has duplicate evidence references")
        seen.add(key)
    for relation in output.relations:
        if relation.source == relation.target and relation.source_type == relation.target_type:
            raise ValueError("consolidation output has a self-relation")


def consolidate_openai(
    base_url: str,
    api_key: str,
    model: str,
    prompt_version: str,
    payload: list[dict[str, object]],
    timeout: float,
) -> ConsolidationOutput:
    response = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Consolidate only explicit extraction summaries. Return JSON matching "
                        "schema. Never infer from co-occurrence or fuzzy similarity. Every alias "
                        "and relation needs one exact evidence quote and source chunk ID. "
                        "Both endpoints must appear in every relation evidence quote. "
                        "Endpoints require exact names and types. "
                        f"Prompt version: {prompt_version}"
                    ),
                },
                {"role": "user", "content": json.dumps(payload, separators=(",", ":"))},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "graph_consolidation",
                    "strict": True,
                    "schema": ConsolidationOutput.model_json_schema(),
                },
            },
        },
        timeout=timeout,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return ConsolidationOutput.model_validate_json(content)
