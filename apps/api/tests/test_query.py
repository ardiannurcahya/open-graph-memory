from types import SimpleNamespace

import httpx
import pytest
from app.providers import ChatResult, Usage
from app.query import (
    answer_segments,
    authoritative_hits,
    build_context,
    chat_with_citation_repair,
    safe_provider_call,
    stream_event,
)
from app.vector_store import VectorHit


def test_build_context_keeps_evidence_blocks_and_citation_indexes_aligned() -> None:
    context = build_context(
        [
            VectorHit(
                "people", 0.9, {"document_id": "people-doc", "text": "Acme -> EMPLOYS -> Alice"}
            ),
            VectorHit(
                "product", 0.8, {"document_id": "product-doc", "text": "Atlas -> BUILT_BY -> Acme"}
            ),
        ]
    )
    assert "[1] chunk_id=people document_id=people-doc" in context
    assert "[2] chunk_id=product document_id=product-doc" in context
    assert context.index("[1]") < context.index("[2]")


def test_stream_helpers_emit_sse_and_token_segments() -> None:
    assert stream_event("status", {"stage": "retrieving"}) == (
        'event: status\ndata: {"stage":"retrieving"}\n\n'
    )
    assert answer_segments("Hello world") == ["Hello ", "world"]




class ScalarRows:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class ReverseOrderSession:
    async def scalars(self, statement: object) -> ScalarRows:
        return ScalarRows(
            [
                SimpleNamespace(id="second", document_id="doc-2", text="second text"),
                SimpleNamespace(id="first", document_id="doc-1", text="first text"),
            ]
        )


class ScriptedChat:
    name = "scripted"

    def __init__(self, texts: list[str]) -> None:
        self.texts = texts
        self.calls: list[list[dict[str, str]]] = []

    async def chat(self, messages: list[dict[str, str]], model: str) -> ChatResult:
        self.calls.append(messages)
        return ChatResult(
            self.texts[len(self.calls) - 1],
            Usage(prompt_tokens=2, completion_tokens=3, estimated_cost_usd=0.01),
        )


@pytest.mark.asyncio
async def test_authoritative_hits_preserves_raw_vector_rank_and_score() -> None:
    raw = [VectorHit("first", 0.91, {}), VectorHit("second", 0.72, {})]

    hits = await authoritative_hits(
        ReverseOrderSession(),  # type: ignore[arg-type]
        "project",
        "dataset",
        raw,
    )

    assert [(hit.id, hit.score) for hit in hits] == [("first", 0.91), ("second", 0.72)]


@pytest.mark.asyncio
async def test_chat_repairs_citation_format_once() -> None:
    chat = ScriptedChat(["Supported answer without citation.", "Supported answer [1]."])

    result, referenced = await chat_with_citation_repair(
        chat,  # type: ignore[arg-type]
        [{"role": "user", "content": "Question"}],
        "model",
        1,
    )

    assert result.text == "Supported answer [1]."
    assert referenced == {1}
    assert len(chat.calls) == 2
    assert result.usage.prompt_tokens == 4
    assert result.usage.completion_tokens == 6
    assert result.usage.estimated_cost_usd == 0.02


@pytest.mark.asyncio
async def test_chat_stops_after_one_failed_citation_repair() -> None:
    chat = ScriptedChat(["Answer [9].", "Still wrong [2]."])

    with pytest.raises(Exception) as caught:
        await chat_with_citation_repair(
            chat,  # type: ignore[arg-type]
            [{"role": "user", "content": "Question"}],
            "model",
            1,
        )

    assert getattr(caught.value, "status_code", None) == 502
    assert len(chat.calls) == 2


@pytest.mark.asyncio
async def test_provider_timeout_maps_to_safe_504() -> None:
    request = httpx.Request("POST", "https://provider.invalid/chat")

    async def fail() -> object:
        raise httpx.ReadTimeout("private upstream timeout", request=request)

    with pytest.raises(Exception) as caught:
        await safe_provider_call(fail)

    assert getattr(caught.value, "status_code", None) == 504
    assert getattr(caught.value, "detail", None) == "provider request timed out"


@pytest.mark.asyncio
async def test_provider_http_error_maps_to_safe_502() -> None:
    request = httpx.Request("POST", "https://provider.invalid/chat")
    response = httpx.Response(503, request=request)

    async def fail() -> object:
        raise httpx.HTTPStatusError("secret diagnostics", request=request, response=response)

    with pytest.raises(Exception) as caught:
        await safe_provider_call(fail)

    assert getattr(caught.value, "status_code", None) == 502
    assert getattr(caught.value, "detail", None) == "provider request failed"
