"""Provider-neutral graph extraction and conservative entity resolution."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Protocol, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    type: str = "Entity"
    confidence: float = Field(ge=0, le=1)


class Relation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    target: str
    type: str
    confidence: float = Field(ge=0, le=1)


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entities: list[Entity]
    relations: list[Relation]


class Extractor(Protocol):
    def extract(self, text: str) -> Extraction: ...


def _object_map(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return {}


def _object_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _confidence(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0.0, min(1.0, float(value)))
    return 0.8


def _load_json_object(content: str) -> object:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(stripped[start : end + 1])


def _normalize_extraction_payload(payload: object) -> dict[str, list[dict[str, object]]]:
    root = _object_map(payload)
    raw_entities = _object_list(root.get("entities") or root.get("nodes"))
    raw_relations = _object_list(root.get("relations") or root.get("edges"))
    entities: list[dict[str, object]] = []
    id_to_name: dict[str, str] = {}
    for raw in raw_entities:
        item = _object_map(raw)
        name = _string(item.get("name")) or _string(item.get("label")) or _string(item.get("id"))
        if name is None:
            continue
        entity_type = _string(item.get("type")) or "Entity"
        entity = {
            "name": name,
            "type": entity_type,
            "confidence": _confidence(item.get("confidence")),
        }
        entities.append(entity)
        entity_id = _string(item.get("id"))
        if entity_id is not None:
            id_to_name[entity_id] = name
    relations: list[dict[str, object]] = []
    for raw in raw_relations:
        item = _object_map(raw)
        source = _string(item.get("source")) or _string(item.get("from"))
        target = _string(item.get("target")) or _string(item.get("to"))
        relation_type = _string(item.get("type")) or _string(item.get("relation"))
        if source is None or target is None or relation_type is None:
            continue
        relations.append(
            {
                "source": id_to_name.get(source, source),
                "target": id_to_name.get(target, target),
                "type": relation_type,
                "confidence": _confidence(item.get("confidence")),
            }
        )
    return {"entities": entities, "relations": relations}


def _parse_extraction_content(content: str, source_text: str) -> Extraction:
    deterministic = DeterministicExtractor().extract(source_text)
    try:
        extracted = Extraction.model_validate(
            _normalize_extraction_payload(_load_json_object(content))
        )
    except (json.JSONDecodeError, ValueError):
        return deterministic
    if not extracted.entities and not extracted.relations and (
        deterministic.entities or deterministic.relations
    ):
        return deterministic
    return extracted


def normalize_name(value: str) -> str:
    """Normalize conservatively: preserve punctuation and semantic tokens."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode()
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:32]}"


@dataclass(frozen=True)
class Candidate:
    id: str
    dataset_id: str
    normalized_name: str
    entity_type: str


def resolve_candidate(
    dataset_id: str, entity: Entity, candidates: list[Candidate]
) -> Candidate | None:
    """Only resolve exact normalized name and type within the same dataset."""
    key = (dataset_id, normalize_name(entity.name), normalize_name(entity.type))
    matches = [
        c
        for c in candidates
        if (c.dataset_id, c.normalized_name, normalize_name(c.entity_type)) == key
    ]
    return matches[0] if len(matches) == 1 else None


class DeterministicExtractor:
    """Fixture extractor for explicit `Name [Type]` and `A -> REL -> B` text."""

    entity_pattern = re.compile(r"(?P<name>[A-Z][\w .&'-]*?)\s*\[(?P<type>[A-Za-z][\w-]*)\]")
    relation_pattern = re.compile(
        r"(?P<source>[^\n;]+?)\s*->\s*(?P<type>[A-Z][A-Z0-9_]*)\s*->\s*(?P<target>[^\n;]+)"
    )
    phrase_pattern = re.compile(
        r"\b(?:[A-Z][A-Za-zÀ-ÿ0-9&+./'-]*|[A-Z]{2,})(?:\s+(?:[A-Z][A-Za-zÀ-ÿ0-9&+./'-]*|[A-Z]{2,})){1,5}\b"
    )
    email_pattern = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
    skill_pattern = re.compile(
        r"\b(?:FastAPI|Next\.js|PostgreSQL|Docker|Python|Machine Learning|LLM|OCR|"
        r"MinIO|Electron|GitHub Actions|Neo4j|Qdrant|React|TypeScript)\b",
        re.IGNORECASE,
    )

    def extract(self, text: str) -> Extraction:
        found: dict[tuple[str, str], Entity] = {}
        for match in self.entity_pattern.finditer(text):
            entity = Entity(name=match["name"].strip(), type=match["type"], confidence=1.0)
            found[(normalize_name(entity.name), normalize_name(entity.type))] = entity
        relations = [
            Relation(
                source=m["source"].strip(),
                type=m["type"],
                target=m["target"].strip(),
                confidence=1.0,
            )
            for m in self.relation_pattern.finditer(text)
        ]
        if not found:
            for match in self.email_pattern.finditer(text):
                name = match.group(0).strip()
                found[(normalize_name(name), "contact")] = Entity(
                    name=name, type="Contact", confidence=0.7
                )
            for match in self.skill_pattern.finditer(text):
                name = match.group(0).strip()
                found[(normalize_name(name), "skill")] = Entity(
                    name=name, type="Skill", confidence=0.7
                )
            for match in self.phrase_pattern.finditer(text):
                name = " ".join(match.group(0).split())
                if len(name) < 4 or len(name) > 80:
                    continue
                found.setdefault(
                    (normalize_name(name), "entity"),
                    Entity(name=name, type="Entity", confidence=0.6),
                )
                if len(found) >= 24:
                    break
        entities = sorted(found.values(), key=lambda e: (normalize_name(e.name), e.type))
        if not relations and len(entities) > 1:
            relations = [
                Relation(
                    source=entities[index].name,
                    type="CO_OCCURS_WITH",
                    target=entities[index + 1].name,
                    confidence=0.45,
                )
                for index in range(min(len(entities) - 1, 12))
            ]
        return Extraction(
            entities=entities,
            relations=sorted(
                relations,
                key=lambda r: (normalize_name(r.source), r.type, normalize_name(r.target)),
            ),
        )


@dataclass(frozen=True)
class OpenAICompatibleExtractor:
    base_url: str
    api_key: str
    model: str
    prompt_version: str = "graph-v1"
    timeout: float = 30.0

    def extract(self, text: str) -> Extraction:
        schema = Extraction.model_json_schema()
        response = httpx.post(
            f"{self.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Extract entities and relations. Return only valid JSON with top-level "
                            "entities and relations arrays. Entity fields: name, type, confidence. "
                            "Relation fields: source, target, type, confidence. No markdown, "
                            f"prose, or explanations. Prompt version: {self.prompt_version}"
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "graph_extraction", "strict": True, "schema": schema},
                },
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        try:
            payload = cast(dict[str, Any], _load_openai_response(response.text))
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return DeterministicExtractor().extract(text)
        return _parse_extraction_content(content, text)


def _load_openai_response(text: str) -> dict[str, object]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload, _ = json.JSONDecoder().raw_decode(text)
    if not isinstance(payload, dict):
        raise ValueError("OpenAI-compatible response is not a JSON object")
    return payload
