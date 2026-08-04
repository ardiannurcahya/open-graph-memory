"""Typed content validation for memory types."""

from typing import Any

from fastapi import HTTPException

TYPE_SCHEMAS: dict[str, dict[str, Any]] = {
    "bugfix": {
        "required": ["summary"],
        "optional": ["root_cause", "fix", "verified", "extensions"],
        "validators": {
            "verified": lambda v: isinstance(v, bool),
            "summary": lambda v: isinstance(v, str) and len(v) > 0 and len(v) <= 20000,
        },
    },
    "decision": {
        "required": ["decision", "rationale"],
        "optional": ["alternatives", "extensions"],
        "validators": {
            "decision": lambda v: isinstance(v, str) and len(v) > 0,
            "rationale": lambda v: isinstance(v, str) and len(v) > 0,
        },
    },
    "preference": {
        "required": ["subject", "preference"],
        "optional": ["context", "extensions"],
        "validators": {
            "subject": lambda v: isinstance(v, str) and len(v) > 0,
            "preference": lambda v: isinstance(v, str) and len(v) > 0,
        },
    },
    "procedure": {
        "required": ["name"],
        "optional": ["steps", "prerequisites", "extensions"],
        "validators": {
            "name": lambda v: isinstance(v, str) and len(v) > 0,
            "steps": lambda v: isinstance(v, list) and 0 < len(v) <= 100,
        },
    },
    "research": {
        "required": ["question", "finding"],
        "optional": ["sources", "extensions"],
        "validators": {
            "question": lambda v: isinstance(v, str) and len(v) > 0,
            "finding": lambda v: isinstance(v, str) and len(v) > 0,
        },
    },
    "trading": {
        "required": ["instrument", "thesis"],
        "optional": ["risk", "timeframe", "extensions"],
        "validators": {
            "instrument": lambda v: isinstance(v, str) and len(v) > 0,
            "thesis": lambda v: isinstance(v, str) and len(v) > 0,
        },
    },
    "learning": {
        "required": ["topic", "lesson"],
        "optional": ["application", "extensions"],
        "validators": {
            "topic": lambda v: isinstance(v, str) and len(v) > 0,
            "lesson": lambda v: isinstance(v, str) and len(v) > 0,
        },
    },
    "fact": {
        "required": ["value"],
        "optional": ["subject", "unit", "extensions"],
        "validators": {
            "value": lambda v: v is not None,
        },
    },
    "custom": {
        "required": [],
        "optional": [],
        "validators": {},
    },
}


def validate_typed_content(memory_type: str, content: dict[str, Any]) -> None:
    if memory_type not in TYPE_SCHEMAS:
        raise HTTPException(400, f"invalid memory type: {memory_type}")

    schema = TYPE_SCHEMAS[memory_type]

    if memory_type == "custom":
        if not content:
            raise HTTPException(400, "custom content cannot be empty")
        return

    for field in schema["required"]:
        if field not in content:
            raise HTTPException(400, f"missing required field '{field}' for type '{memory_type}'")

    allowed_fields = set(schema["required"] + schema["optional"])
    for field in content:
        if field not in allowed_fields:
            raise HTTPException(400, f"unknown field '{field}' for type '{memory_type}'")

    for field, validator in schema["validators"].items():
        if field in content and not validator(content[field]):
            raise HTTPException(400, f"invalid value for field '{field}' in type '{memory_type}'")

    if "verified" in content and memory_type == "bugfix":
        if content["verified"] and not content.get("verification_evidence"):
            raise HTTPException(
                400, "verified bugfix requires verification evidence"
            )


def get_type_schema(memory_type: str) -> dict[str, Any] | None:
    return TYPE_SCHEMAS.get(memory_type)


def list_memory_types() -> list[str]:
    return list(TYPE_SCHEMAS.keys())
