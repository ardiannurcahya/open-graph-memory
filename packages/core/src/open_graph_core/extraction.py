"""Provider-neutral graph extraction and conservative entity resolution."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

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
        return Extraction(
            entities=sorted(found.values(), key=lambda e: (normalize_name(e.name), e.type)),
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
                            f"Extract entities and relations. Prompt version: {self.prompt_version}"
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
        content = response.json()["choices"][0]["message"]["content"]
        return Extraction.model_validate(json.loads(content))
