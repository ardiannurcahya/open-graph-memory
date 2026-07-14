from open_graph_core.extraction import (
    Candidate,
    DeterministicExtractor,
    Entity,
    Extraction,
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
    }


def test_openai_payload_loader_accepts_fenced_json() -> None:
    payload = _load_json_object('```json\n{"entities": [], "relations": []}\n```')

    assert Extraction.model_validate(_normalize_extraction_payload(payload)).model_dump() == {
        "entities": [],
        "relations": [],
    }


def test_openai_response_loader_accepts_first_json_object_with_trailing_data() -> None:
    payload = _load_openai_response(
        '{"choices":[{"message":{"content":"{\\\"entities\\\":[],\\\"relations\\\":[]}"}}]}'
        '\n{"extra": true}'
    )

    assert payload["choices"][0]["message"]["content"] == '{"entities":[],"relations":[]}'


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
    assert result.relations


def test_openai_extractor_falls_back_when_provider_response_is_not_json(monkeypatch) -> None:
    def fake_post(*_args, **_kwargs) -> _FakeResponse:
        return _FakeResponse("")

    monkeypatch.setattr("open_graph_core.extraction.httpx.post", fake_post)
    result = OpenAICompatibleExtractor("http://provider", "key", "model").extract(
        "RX1 Driver [Software] -> DRIVES -> DNP RX1 [Printer]"
    )

    assert result.relations[0].type == "DRIVES"
