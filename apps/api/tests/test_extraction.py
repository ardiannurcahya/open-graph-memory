import json

from open_graph_core.extraction import (
    Candidate,
    ChunkExtractionContext,
    ChunkReference,
    DeterministicExtractor,
    Entity,
    Extraction,
    NlpExtractor,
    OpenAICompatibleExtractor,
    _load_json_object,
    _load_openai_response,
    _normalize_extraction_payload,
    _parse_extraction_content,
    normalize_name,
    resolve_candidate,
    stable_id,
)


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


def test_deterministic_fixture_extraction() -> None:
    result = DeterministicExtractor().extract(
        "Acme Corp [Company]; Widget [Product]\nAcme Corp -> OWNS -> Widget"
    )
    assert [(e.name, e.type) for e in result.entities] == [
        ("Acme Corp", "Company"),
        ("Widget", "Product"),
    ]
    assert result.relations[0].model_dump() == {
        "source": "Acme Corp",
        "target": "Widget",
        "type": "OWNS",
        "confidence": 1.0,
        "source_type": None,
        "target_type": None,
        "quote": None,
    }
    assert result == DeterministicExtractor().extract(
        "Acme Corp [Company]; Widget [Product]\nAcme Corp -> OWNS -> Widget"
    )


def test_normalization_is_conservative_and_stable_ids_are_scoped() -> None:
    assert normalize_name("  ACME   Corp. ") == "acme corp."
    assert stable_id("ent", "ds_1", "acme", "company") == stable_id(
        "ent", "ds_1", "acme", "company"
    )
    assert stable_id("ent", "ds_1", "acme", "company") != stable_id(
        "ent", "ds_2", "acme", "company"
    )


def test_resolution_requires_exact_unique_dataset_match() -> None:
    candidate = Candidate("ent_1", "ds_1", "acme", "Company")
    entity = Entity(name=" ACME ", type="company", confidence=0.9)
    assert resolve_candidate("ds_1", entity, [candidate]) == candidate
    assert resolve_candidate("ds_2", entity, [candidate]) is None
    assert resolve_candidate("ds_1", entity, [candidate, candidate]) is None


def test_openai_payload_normalization_accepts_common_aliases() -> None:
    payload = {
        "entities": [
            {"id": "driver", "type": "Software", "name": "RX1 Driver", "version": "v1"},
            {"id": "printer", "type": "Printer", "name": "DNP RX1"},
        ],
        "relations": [
            {"source": "driver", "relation": "DRIVES", "target": "printer"},
        ],
    }

    result = Extraction.model_validate(_normalize_extraction_payload(payload))

    assert [(entity.name, entity.type, entity.confidence) for entity in result.entities] == [
        ("RX1 Driver", "Software", 0.8),
        ("DNP RX1", "Printer", 0.8),
    ]
    assert result.relations[0].model_dump() == {
        "source": "RX1 Driver",
        "target": "DNP RX1",
        "type": "DRIVES",
        "confidence": 0.8,
        "source_type": None,
        "target_type": None,
        "quote": None,
    }


def test_openai_payload_loader_accepts_fenced_json() -> None:
    payload = _load_json_object('```json\n{"entities": [], "relations": []}\n```')

    assert Extraction.model_validate(_normalize_extraction_payload(payload)).model_dump() == {
        "entities": [],
        "relations": [],
    }


def test_openai_response_loader_accepts_first_json_object_with_trailing_data() -> None:
    payload = _load_openai_response(
        '{"choices":[{"message":{"content":"{\\"entities\\":[],\\"relations\\":[]}"}}]}'
        '\n{"extra": true}'
    )

    assert payload["choices"][0]["message"]["content"] == '{"entities":[],"relations":[]}'


def test_openai_extractor_combines_sse_content_chunks(monkeypatch) -> None:
    def fake_post(*_args, **_kwargs) -> _FakeResponse:
        first_event = json.dumps(
            {"choices": [{"delta": {"content": '{"entities":[{"name":"Acme",'}}]}
        )
        second_event = json.dumps(
            {
                "choices": [
                    {"delta": {"content": '"type":"Company","confidence":0.9}],"relations":[]}'}}
                ]
            }
        )
        return _FakeResponse(f"data: {first_event}\n\ndata: {second_event}\n\ndata: [DONE]\n\n")

    monkeypatch.setattr("open_graph_core.extraction.httpx.post", fake_post)

    result = OpenAICompatibleExtractor("http://provider", "key", "model").extract("input")

    assert [entity.model_dump() for entity in result.entities] == [
        {"name": "Acme", "type": "Company", "confidence": 0.9, "aliases": []}
    ]
    assert result.relations == []


def test_openai_extractor_preserves_json_response_handling(monkeypatch) -> None:
    def fake_post(*_args, **_kwargs) -> _FakeResponse:
        return _FakeResponse(
            json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"entities":[{"name":"Acme","type":"Company",'
                                '"confidence":0.9}],"relations":[]}'
                            }
                        }
                    ]
                }
            )
        )

    monkeypatch.setattr("open_graph_core.extraction.httpx.post", fake_post)

    result = OpenAICompatibleExtractor("http://provider", "key", "model").extract("input")

    assert result.entities[0].name == "Acme"


def test_openai_extractor_accepts_final_message_sse(monkeypatch) -> None:
    def fake_post(*_args, **_kwargs) -> _FakeResponse:
        event = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"entities":[{"name":"Acme","type":"Company",'
                            '"confidence":0.9}],"relations":[]}'
                        },
                        "finish_reason": "stop",
                    }
                ]
            }
        )
        return _FakeResponse(f"data: {event}\n\n")

    monkeypatch.setattr("open_graph_core.extraction.httpx.post", fake_post)

    result = OpenAICompatibleExtractor("http://provider", "key", "model").extract("input")

    assert result.entities[0].name == "Acme"


def test_openai_extractor_prompt_requires_complete_named_relations(monkeypatch) -> None:
    request: dict[str, object] = {}

    def fake_post(*_args, **kwargs) -> _FakeResponse:
        request.update(kwargs["json"])
        return _FakeResponse(
            '{"choices":[{"message":{"content":"{\\"entities\\":[],\\"relations\\":[]}"}}]}'
        )

    monkeypatch.setattr("open_graph_core.extraction.httpx.post", fake_post)

    OpenAICompatibleExtractor("http://provider", "key", "model").extract("input")

    system_prompt = request["messages"][0]["content"]
    required_relation_instruction = (
        "every explicit action, ownership, development, and acquisition relationship"
    )
    assert required_relation_instruction in system_prompt
    assert "source and target exactly match emitted entity names" in system_prompt


def test_contextual_extraction_marks_neighbors_reference_only(monkeypatch) -> None:
    request: dict[str, object] = {}

    def fake_post(*_args, **kwargs) -> _FakeResponse:
        request.update(kwargs["json"])
        return _FakeResponse(
            '{"choices":[{"message":{"content":"{\\"entities\\":[],\\"relations\\":[]}"}}]}'
        )

    monkeypatch.setattr("open_graph_core.extraction.httpx.post", fake_post)
    context = ChunkExtractionContext(
        "manual.pdf",
        ("Architecture",),
        2,
        1,
        3,
        "Acme introduced Project Nova.",
        "It uses PostgreSQL.",
        "Next section.",
    )

    OpenAICompatibleExtractor("http://provider", "key", "model").extract_with_context(context)

    user_payload = json.loads(request["messages"][1]["content"])
    target = user_payload["targets"][0]
    assert target["target_chunk_only_factual_source"] == "It uses PostgreSQL."
    assert user_payload["previous_chunks_reference_only"] == []


def test_openai_extractor_batches_target_results_with_fixed_previous_references(
    monkeypatch,
) -> None:
    request: dict[str, object] = {}

    def fake_post(*_args, **kwargs) -> _FakeResponse:
        request.update(kwargs["json"])
        return _FakeResponse(
            json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "results": [
                                            {
                                                "chunk_id": "two",
                                                "entities": [
                                                    {
                                                        "name": "Bob",
                                                        "type": "Person",
                                                        "confidence": 1,
                                                    }
                                                ],
                                                "relations": [],
                                            },
                                            {
                                                "chunk_id": "three",
                                                "entities": [],
                                                "relations": [],
                                            },
                                        ]
                                    }
                                )
                            }
                        }
                    ]
                }
            )
        )

    monkeypatch.setattr("open_graph_core.extraction.httpx.post", fake_post)
    contexts = [
        ChunkExtractionContext("doc", (), None, 1, 3, "", "Bob", "", (), "two"),
        ChunkExtractionContext(
            "doc", (), None, 2, 3, "", "Carol", "", (ChunkReference("two", 1, "Bob"),), "three"
        ),
    ]

    results = OpenAICompatibleExtractor("http://provider", "key", "model").extract_batch(contexts)

    assert [result.chunk_id for result in results] == ["two", "three"]
    assert results[0].extraction.entities[0].name == "Bob"
    payload = json.loads(request["messages"][1]["content"])
    assert payload["previous_chunks_reference_only"] == [
        {"chunk_id": "two", "text": "Bob"}
    ]
    assert "cannot own entities" in request["messages"][0]["content"]
    schema = request["response_format"]["json_schema"]["schema"]
    assert "$defs" in schema
    assert schema["properties"]["results"]["items"]["$ref"].startswith("#/$defs/")
    assert set(schema["$defs"]["Entity"]["required"]) == {
        "name",
        "type",
        "confidence",
        "aliases",
    }
    assert set(schema["$defs"]["Relation"]["required"]) == {
        "source",
        "target",
        "type",
        "confidence",
        "source_type",
        "target_type",
        "quote",
    }


def test_openai_batch_malformed_response_falls_back_per_target(monkeypatch) -> None:
    def fake_post(*_args, **_kwargs) -> _FakeResponse:
        return _FakeResponse('{"choices":[{"message":{"content":"{\\"results\\":[]}"}}]}')

    monkeypatch.setattr("open_graph_core.extraction.httpx.post", fake_post)
    contexts = [
        ChunkExtractionContext("doc", (), None, 0, 2, "", "Acme [Org]", "", (), "one"),
        ChunkExtractionContext("doc", (), None, 1, 2, "", "Bob [Person]", "", (), "two"),
    ]

    results = OpenAICompatibleExtractor("http://provider", "key", "model").extract_batch(contexts)

    assert [(result.chunk_id, result.extraction.entities[0].name) for result in results] == [
        ("one", "Acme"),
        ("two", "Bob"),
    ]


def test_openai_batch_guard_trims_oldest_references_then_reduces_targets(monkeypatch) -> None:
    requests: list[dict[str, object]] = []

    def fake_post(*_args, **kwargs) -> _FakeResponse:
        requests.append(json.loads(kwargs["json"]["messages"][1]["content"]))
        results = [
            {"chunk_id": target["chunk_id"], "entities": [], "relations": []}
            for target in requests[-1]["targets"]
        ]
        return _FakeResponse(
            json.dumps({"choices": [{"message": {"content": json.dumps({"results": results})}}]})
        )

    monkeypatch.setattr("open_graph_core.extraction.httpx.post", fake_post)
    contexts = [
        ChunkExtractionContext(
            "d",
            (),
            None,
            2,
            4,
            "",
            "target-one",
            "",
            (ChunkReference("old", 0, "x" * 80),),
            "one",
        ),
        ChunkExtractionContext("d", (), None, 3, 4, "", "target-two", "", (), "two"),
    ]

    results = OpenAICompatibleExtractor(
        "http://provider", "key", "model", max_batch_chars=180
    ).extract_batch(contexts)

    assert [result.chunk_id for result in results] == ["one", "two"]
    assert requests[0]["previous_chunks_reference_only"] == []
    assert [
        target["chunk_id"] for request in requests for target in request["targets"]
    ] == ["one", "two"]


def test_openai_extractor_falls_back_for_malformed_or_empty_sse(monkeypatch) -> None:
    responses = iter(
        [
            "data: {not json}\n\ndata: [DONE]\n\n",
            'data: {"choices":[{"delta":{}}]}\n\ndata: [DONE]\n\n',
        ]
    )

    def fake_post(*_args, **_kwargs) -> _FakeResponse:
        return _FakeResponse(next(responses))

    monkeypatch.setattr("open_graph_core.extraction.httpx.post", fake_post)
    extractor = OpenAICompatibleExtractor("http://provider", "key", "model")
    source_text = "RX1 Driver [Software] -> DRIVES -> DNP RX1 [Printer]"

    assert extractor.extract(source_text).relations[0].type == "DRIVES"
    assert extractor.extract(source_text).relations[0].type == "DRIVES"


def test_openai_parse_falls_back_to_deterministic_extractor_for_non_json() -> None:
    result = _parse_extraction_content(
        "I cannot return JSON.",
        "RX1 Driver [Software] -> DRIVES -> DNP RX1 [Printer]",
    )

    assert [(entity.name, entity.type) for entity in result.entities] == [
        ("DNP RX1", "Printer"),
        ("RX1 Driver", "Software"),
    ]
    assert result.relations[0].type == "DRIVES"


def test_deterministic_extractor_falls_back_to_heuristic_entities() -> None:
    result = DeterministicExtractor().extract(
        "ARDIAN NURCAHYA built FastAPI, PostgreSQL, Docker, and LLM Agent Trade Platform."
    )

    assert {entity.name for entity in result.entities} >= {
        "ARDIAN NURCAHYA",
        "FastAPI",
        "PostgreSQL",
        "Docker",
    }
    assert result.relations == []


def test_nlp_extractor_emits_typed_entities_and_explicit_active_relations() -> None:
    result = NlpExtractor().extract(
        "Alice Nguyen works at Acme Labs. Acme Labs acquired Widget Cloud. "
        "Alice Nguyen built Atlas Service."
    )

    assert [(entity.name, entity.type) for entity in result.entities] == [
        ("Acme Labs", "Organization"),
        ("Alice Nguyen", "Person"),
        ("Atlas Service", "Product"),
        ("Widget Cloud", "Organization"),
    ]
    assert [relation.model_dump() for relation in result.relations] == [
        {
            "source": "Acme Labs",
            "target": "Widget Cloud",
            "type": "ACQUIRED",
            "confidence": 0.85,
            "source_type": None,
            "target_type": None,
            "quote": None,
        },
        {
            "source": "Alice Nguyen",
            "target": "Atlas Service",
            "type": "BUILT",
            "confidence": 0.85,
            "source_type": None,
            "target_type": None,
            "quote": None,
        },
        {
            "source": "Alice Nguyen",
            "target": "Acme Labs",
            "type": "WORKS_AT",
            "confidence": 0.85,
            "source_type": None,
            "target_type": None,
            "quote": None,
        },
    ]


def test_nlp_extractor_does_not_emit_cooccurrence_relations() -> None:
    result = NlpExtractor().extract("Alice Nguyen met Bob Smith at Acme Labs.")

    assert result.entities == []
    assert result.relations == []


def test_openai_extractor_falls_back_when_provider_response_is_not_json(monkeypatch) -> None:
    def fake_post(*_args, **_kwargs) -> _FakeResponse:
        return _FakeResponse("")

    monkeypatch.setattr("open_graph_core.extraction.httpx.post", fake_post)
    result = OpenAICompatibleExtractor("http://provider", "key", "model").extract(
        "RX1 Driver [Software] -> DRIVES -> DNP RX1 [Printer]"
    )

    assert result.relations[0].type == "DRIVES"
