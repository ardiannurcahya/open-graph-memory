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
    aliases: list[str] = Field(default_factory=list)


class Relation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    target: str
    type: str
    confidence: float = Field(ge=0, le=1)
    source_type: str | None = None
    target_type: str | None = None
    quote: str | None = None


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entities: list[Entity]
    relations: list[Relation]


class _BatchExtractionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str
    entities: list[Entity]
    relations: list[Relation]


class _BatchExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: list[_BatchExtractionItem]


class Extractor(Protocol):
    def extract(self, text: str) -> Extraction: ...


@dataclass(frozen=True)
class ChunkExtractionContext:
    document_title: str
    section_path: tuple[str, ...]
    page_number: int | None
    chunk_index: int
    chunk_count: int
    previous_excerpt: str
    target_text: str
    next_excerpt: str
    previous_chunks: tuple[ChunkReference, ...] = ()
    chunk_id: str = ""


@dataclass(frozen=True)
class ChunkReference:
    chunk_id: str
    chunk_index: int
    text: str


@dataclass(frozen=True)
class BatchExtractionResult:
    chunk_id: str
    extraction: Extraction


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
            "aliases": [
                alias for alias in _object_list(item.get("aliases")) if isinstance(alias, str)
            ],
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
                "source_type": _string(item.get("source_type")),
                "target_type": _string(item.get("target_type")),
                "quote": _string(item.get("quote")),
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
    if (
        not extracted.entities
        and not extracted.relations
        and (deterministic.entities or deterministic.relations)
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
        return Extraction(
            entities=entities,
            relations=sorted(
                relations,
                key=lambda r: (normalize_name(r.source), r.type, normalize_name(r.target)),
            ),
        )


@dataclass(frozen=True)
class NlpExtractor:
    model: str = "nlp-graph-v1"

    relation_patterns = (
        (
            re.compile(
                r"(?P<source>[A-Z][A-Za-z0-9&' -]{1,79}?)\s+works at\s+"
                r"(?P<target>[A-Z][A-Za-z0-9&' -]{1,79}?)(?=[.!?;]|$)"
            ),
            "WORKS_AT",
            "Person",
            "Organization",
        ),
        (
            re.compile(
                r"(?P<source>[A-Z][A-Za-z0-9&' -]{1,79}?)\s+(?:acquired|bought)\s+"
                r"(?P<target>[A-Z][A-Za-z0-9&' -]{1,79}?)(?=[.!?;]|$)"
            ),
            "ACQUIRED",
            "Organization",
            "Organization",
        ),
        (
            re.compile(
                r"(?P<source>[A-Z][A-Za-z0-9&' -]{1,79}?)\s+(?:built|developed|created)\s+"
                r"(?P<target>[A-Z][A-Za-z0-9&' -]{1,79}?)(?=[.!?;]|$)"
            ),
            "BUILT",
            "Person",
            "Product",
        ),
        (
            re.compile(
                r"(?P<source>[A-Z][A-Za-z0-9&' -]{1,79}?)\s+(?:use|uses)\s+"
                r"(?P<target>[A-Z][A-Za-z0-9&' .+-]{1,79}?)(?=[.!?;]|$)"
            ),
            "USES",
            "Organization",
            "Technology",
        ),
    )

    def extract(self, text: str) -> Extraction:
        entities: dict[tuple[str, str], Entity] = {}
        relations: list[Relation] = []
        for pattern, relation_type, source_type, target_type in self.relation_patterns:
            for match in pattern.finditer(text):
                source = " ".join(match["source"].split())
                target = " ".join(match["target"].split())
                if not source or not target:
                    continue
                entities[(normalize_name(source), source_type)] = Entity(
                    name=source, type=source_type, confidence=0.85
                )
                entities[(normalize_name(target), target_type)] = Entity(
                    name=target, type=target_type, confidence=0.85
                )
                relations.append(
                    Relation(
                        source=source,
                        target=target,
                        type=relation_type,
                        confidence=0.85,
                    )
                )
        return Extraction(
            entities=sorted(
                entities.values(),
                key=lambda entity: (normalize_name(entity.name), entity.type),
            ),
            relations=sorted(
                relations,
                key=lambda relation: (
                    normalize_name(relation.source),
                    relation.type,
                    normalize_name(relation.target),
                ),
            ),
        )


@dataclass(frozen=True)
class OpenAICompatibleExtractor:
    base_url: str
    api_key: str
    model: str
    prompt_version: str = "graph-v2"
    timeout: float = 30.0
    max_batch_chars: int = 100_000

    def extract(self, text: str) -> Extraction:
        return self._extract(text, text)

    def extract_with_context(self, context: ChunkExtractionContext) -> Extraction:
        return self.extract_batch([context])[0].extraction

    def extract_batch(
        self, contexts: list[ChunkExtractionContext]
    ) -> list[BatchExtractionResult]:
        results: list[BatchExtractionResult] = []
        remaining = list(contexts)
        while remaining:
            request_contexts = _fit_batch_contexts(remaining, self.max_batch_chars)
            response = httpx.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": self._system_prompt()},
                        {"role": "user", "content": json.dumps(_batch_payload(request_contexts))},
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "graph_extraction_batch",
                            "strict": True,
                            "schema": _batch_schema(),
                        },
                    },
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            try:
                content = _load_openai_content(response.text)
                results.extend(_parse_batch_content(content, request_contexts))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                results.extend(
                    BatchExtractionResult(
                        _context_chunk_id(context),
                        DeterministicExtractor().extract(context.target_text),
                    )
                    for context in request_contexts
                )
            remaining = remaining[len(request_contexts) :]
        return results

    def _extract(self, user_content: str, source_text: str) -> Extraction:
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
                            self._system_prompt()
                        ),
                    },
                    {"role": "user", "content": user_content},
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
            content = _load_openai_content(response.text)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return DeterministicExtractor().extract(source_text)
        return _parse_extraction_content(content, source_text)

    def _system_prompt(self) -> str:
        return (
            "Extract entities and relations. Return only valid JSON. Entity fields: name, type, "
            "confidence, aliases. Relation fields: source, source_type, target, target_type, type, "
            "confidence, quote. Each TARGET CHUNK is its result's only factual source. Previous "
            "chunks are reference-only and cannot own entities, aliases, relations, or evidence. "
            "Every entity name, alias, and relation quote must be an exact substring of its TARGET "
            "CHUNK. Do not infer relations from co-occurrence. Emit a typed relation for every "
            "explicit action, ownership, development, and acquisition relationship. "
            "Relation source "
            "and target exactly match emitted entity names. No markdown, prose, or explanations. "
            f"Prompt version: {self.prompt_version}"
        )


def _context_chunk_id(context: ChunkExtractionContext) -> str:
    return context.chunk_id or f"chunk-{context.chunk_index}"


def _batch_schema() -> dict[str, object]:
    schema = cast(dict[str, object], _BatchExtractionResponse.model_json_schema())
    _require_all_properties(schema)
    return schema


def _require_all_properties(schema: object) -> None:
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            schema["required"] = list(properties)
            schema["additionalProperties"] = False
        for value in schema.values():
            _require_all_properties(value)
    elif isinstance(schema, list):
        for value in schema:
            _require_all_properties(value)


def _batch_payload(contexts: list[ChunkExtractionContext]) -> dict[str, object]:
    references = {
        reference.chunk_id: reference
        for context in contexts
        for reference in context.previous_chunks
    }
    return {
        "previous_chunks_reference_only": [
            {"chunk_id": reference.chunk_id, "text": reference.text}
            for reference in sorted(
                references.values(), key=lambda item: (item.chunk_index, item.chunk_id)
            )
        ],
        "targets": [
            {
                "chunk_id": _context_chunk_id(context),
                "document": context.document_title,
                "section": list(context.section_path),
                "page": context.page_number,
                "chunk": f"{context.chunk_index + 1}/{context.chunk_count}",
                "target_chunk_only_factual_source": context.target_text,
            }
            for context in contexts
        ]
    }


def _payload_chars(contexts: list[ChunkExtractionContext]) -> int:
    return len(json.dumps(_batch_payload(contexts), separators=(",", ":"), ensure_ascii=False))


def _fit_batch_contexts(
    contexts: list[ChunkExtractionContext], max_batch_chars: int
) -> list[ChunkExtractionContext]:
    selected = list(contexts)
    while _payload_chars(selected) > max_batch_chars:
        references = [
            reference for context in selected for reference in context.previous_chunks
        ]
        if not references:
            if len(selected) == 1:
                return selected
            selected.pop()
            continue
        oldest = min(references, key=lambda item: (item.chunk_index, item.chunk_id)).chunk_id
        selected = [
            ChunkExtractionContext(
                context.document_title,
                context.section_path,
                context.page_number,
                context.chunk_index,
                context.chunk_count,
                context.previous_excerpt,
                context.target_text,
                context.next_excerpt,
                tuple(
                    reference
                    for reference in context.previous_chunks
                    if reference.chunk_id != oldest
                ),
                context.chunk_id,
            )
            for context in selected
        ]
    return selected


def _parse_batch_content(
    content: str, contexts: list[ChunkExtractionContext]
) -> list[BatchExtractionResult]:
    payload = _object_map(_load_json_object(content))
    requested = {_context_chunk_id(context): context for context in contexts}
    items = _object_list(payload.get("results"))
    parsed: list[BatchExtractionResult] = []
    seen: set[str] = set()
    for raw_item in items:
        item = _object_map(raw_item)
        chunk_id = _string(item.get("chunk_id"))
        if chunk_id is None or chunk_id not in requested or chunk_id in seen:
            raise ValueError("batch response contains invalid chunk IDs")
        parsed.append(
            BatchExtractionResult(
                chunk_id,
                Extraction.model_validate(_normalize_extraction_payload(item)),
            )
        )
        seen.add(chunk_id)
    if seen != set(requested):
        raise ValueError("batch response does not include every target chunk")
    return parsed


def _load_openai_response(text: str) -> dict[str, object]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload, _ = json.JSONDecoder().raw_decode(text)
    if not isinstance(payload, dict):
        raise ValueError("OpenAI-compatible response is not a JSON object")
    return payload


def _load_openai_content(text: str) -> str:
    try:
        payload = cast(dict[str, Any], _load_openai_response(text))
        content = payload["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("OpenAI-compatible response content is not a string")
        return content
    except json.JSONDecodeError:
        return _load_openai_sse_content(text)


def _load_openai_sse_content(text: str) -> str:
    content_parts: list[str] = []
    event_data: list[str] = []
    received_data = False
    done = False

    def consume_event() -> None:
        nonlocal done, received_data
        if not event_data:
            return
        raw_data = "\n".join(event_data)
        event_data.clear()
        received_data = True
        if raw_data == "[DONE]":
            done = True
            return
        payload = _object_map(json.loads(raw_data))
        choices = _object_list(payload.get("choices"))
        for choice in choices:
            choice_data = _object_map(choice)
            if choice_data.get("finish_reason") == "stop":
                done = True
            delta = _object_map(choice_data.get("delta"))
            message = _object_map(choice_data.get("message"))
            chunk = delta.get("content", message.get("content"))
            if chunk is not None and not isinstance(chunk, str):
                raise ValueError("OpenAI-compatible SSE content is not a string")
            if isinstance(chunk, str):
                content_parts.append(chunk)

    for line in text.splitlines():
        if not line:
            consume_event()
            continue
        if line.startswith("data:"):
            event_data.append(line[5:].lstrip(" "))
        elif not line.startswith(("event:", "id:", "retry:", ":")):
            raise ValueError("OpenAI-compatible response is not valid SSE")
    consume_event()
    if not received_data or not done or not content_parts:
        raise ValueError("OpenAI-compatible SSE response contains no content")
    return "".join(content_parts)
