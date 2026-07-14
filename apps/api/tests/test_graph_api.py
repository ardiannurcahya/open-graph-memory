from types import SimpleNamespace

from app.graph_api import low_signal_entity, rank_graph_entities


def entity(row_id: str, name: str, entity_type: str) -> SimpleNamespace:
    return SimpleNamespace(id=row_id, canonical_name=name, entity_type=entity_type)


def test_low_signal_entity_filters_numeric_dates_and_identifiers() -> None:
    assert low_signal_entity("0.15", "numeric value")
    assert low_signal_entity("20 August 2024", "access_date")
    assert low_signal_entity("10.3390/app14177509", "doi")
    assert not low_signal_entity("Ardian Nurcahya", "Person")


def test_rank_graph_entities_prefers_connected_human_readable_nodes() -> None:
    rows = [
        entity("n", "0.15", "numeric value"),
        entity("p", "Ardian Nurcahya", "Person"),
        entity("s", "Python", "Skill"),
        entity("d", "20 August 2024", "access_date"),
    ]

    ranked = rank_graph_entities(rows, {"n": 100, "p": 20, "s": 10, "d": 50}, 3)  # type: ignore[arg-type]

    assert [item.canonical_name for item in ranked] == ["Ardian Nurcahya", "Python"]
