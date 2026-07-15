from types import SimpleNamespace

import httpx
import pytest
from app.providers import ChatResult, OpenAIChatProvider, Usage, load_json_response
from app.query import (
    answer_segments,
    authoritative_hits,
    build_context,
    chat_with_citation_repair,
    community_hits,
    graph_evidence_chunk_ids,
    graph_evidence_scores,
    rank_community_reports,
    retrieval_plan,
    safe_provider_call,
    stream_event,
)
from app.retrieval import GraphEvidence
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


def test_build_context_includes_source_location_when_present() -> None:
    context = build_context(
        [
            VectorHit(
                "chunk",
                0.9,
                {
                    "document_id": "doc",
                    "text": "Evidence",
                    "page_number": 2,
                    "record_number": 4,
                    "segment_part": 3,
                },
            )
        ]
    )

    assert "source={'page_number': 2, 'record_number': 4, 'segment_part': 3}" in context


def test_community_ranking_is_lexical_and_deterministic() -> None:
    reports = [
        SimpleNamespace(id="z", title="Atlas", summary="launch", key_points=[]),
        SimpleNamespace(id="a", title="Atlas", summary="launch", key_points=[]),
        SimpleNamespace(id="b", title="Other", summary="", key_points=[]),
    ]

    ranked = rank_community_reports(reports, "Atlas launch", 3)

    assert [(score, report.id) for score, report in ranked] == [(2, "a"), (2, "z"), (0, "b")]


@pytest.mark.parametrize(
    ("mode", "query", "override", "expected"),
    [
        ("graph_global", "What happened?", None, ("graph_global", "local", False, True)),
        ("graph_local", "global overview", None, ("graph_local", "global_summary", True, False)),
        ("graph_only", "What happened?", None, ("graph_local", "local", True, False)),
        ("hybrid", "Give global overview", None, ("hybrid", "global_summary", True, True)),
        ("vector_only", "What happened?", True, ("vector_only", "local", False, True)),
    ],
)
def test_retrieval_plan_keeps_mode_contracts(
    mode: str, query: str, override: bool | None, expected: tuple[str, str, bool, bool]
) -> None:
    assert retrieval_plan(mode, query, override) == expected


def test_stream_helpers_emit_sse_and_token_segments() -> None:
    assert stream_event("status", {"stage": "retrieving"}) == (
        'event: status\ndata: {"stage":"retrieving"}\n\n'
    )
    assert answer_segments("Hello world") == ["Hello ", "world"]


def test_provider_json_loader_accepts_first_object_with_trailing_data() -> None:
    payload = load_json_response('{"choices": []}\n{"extra": true}')

    assert payload == {"choices": []}


def test_graph_hydration_uses_relation_evidence_chunk_ids() -> None:
    evidence = [
        GraphEvidence(
            chunk_id="path-only",
            score=0.7,
            path=("Alice", "Acme"),
            entity_ids=("ent-1", "ent-2"),
            relation_ids=("rel-1",),
            evidence_chunk_ids=("source-a", "source-b"),
        ),
        GraphEvidence(
            chunk_id="source-b",
            score=0.9,
            path=("Acme", "Atlas"),
            entity_ids=("ent-2", "ent-3"),
            relation_ids=("rel-2",),
            evidence_chunk_ids=("source-b", "source-c"),
        ),
    ]

    chunk_ids = graph_evidence_chunk_ids(evidence, 4)

    assert chunk_ids == ["source-a", "source-b", "path-only", "source-c"]
    assert graph_evidence_scores(evidence, chunk_ids) == {
        "source-a": 0.7,
        "source-b": 0.9,
        "path-only": 0.7,
        "source-c": 0.9,
    }




class CommunitySession:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def scalar(self, statement: object) -> object:
        self.statements.append(str(statement))
        return SimpleNamespace(id="run-latest")

    async def scalars(self, statement: object) -> "ScalarRows":
        self.statements.append(str(statement))
        text = str(statement)
        if "community_reports" in text:
            return ScalarRows(
                [
                    SimpleNamespace(
                        id="report-1", title="Atlas", summary="REPORT PROSE", key_points=[]
                    )
                ]
            )
        if "community_report_evidence" in text:
            return ScalarRows([SimpleNamespace(chunk_id="backing-chunk", rank=1)])
        return ScalarRows(
            [SimpleNamespace(id="backing-chunk", document_id="doc", text="backing evidence")]
        )


@pytest.mark.asyncio
async def test_community_hits_scope_latest_run_and_hydrate_backing_chunks_only() -> None:
    db = CommunitySession()

    hits, trace = await community_hits(db, "project", "dataset", "Atlas", 5)  # type: ignore[arg-type]

    assert [hit.id for hit in hits] == ["backing-chunk"]
    assert "REPORT PROSE" not in build_context(hits)
    assert trace["report_ids"] == ["report-1"]
    assert trace["backing_chunk_ids"] == ["backing-chunk"]
    statements = "\n".join(db.statements)
    assert "graph_analytics_runs.project_id" in statements
    assert "graph_analytics_runs.dataset_id" in statements
    assert "community_reports.analytics_run_id" in statements
    assert "chunks.project_id" in statements and "chunks.dataset_id" in statements


class ScalarRows:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def __iter__(self):
        return iter(self.rows)

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


class FakeChatClient:
    async def post(self, *args: object, **kwargs: object) -> httpx.Response:
        request = httpx.Request("POST", "https://provider.test/chat/completions")
        return httpx.Response(
            200,
            request=request,
            text=(
                '{"choices":[{"message":{"content":"Answer [1]."}}],'
                '"usage":{"prompt_tokens":4,"completion_tokens":2}}\n{"extra":true}'
            ),
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
async def test_openai_chat_accepts_provider_response_with_trailing_data() -> None:
    chat = OpenAIChatProvider("https://provider.test", "key", client=FakeChatClient())  # type: ignore[arg-type]

    result = await chat.chat([{"role": "user", "content": "Question"}], "model")

    assert result.text == "Answer [1]."
    assert result.usage.prompt_tokens == 4
    assert result.usage.completion_tokens == 2


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
