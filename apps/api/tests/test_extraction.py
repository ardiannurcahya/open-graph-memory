from open_graph_core.extraction import (
    Candidate,
    DeterministicExtractor,
    Entity,
    normalize_name,
    resolve_candidate,
    stable_id,
)


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
