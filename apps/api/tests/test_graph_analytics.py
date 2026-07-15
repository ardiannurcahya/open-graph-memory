from app.graph_analytics import LOUVAIN_RESOLUTION, LOUVAIN_SEED, analyze_graph


def test_analysis_is_deterministic_with_stable_community_ids() -> None:
    entities = ["a", "b", "c", "d"]
    relations = [("a", "b", 0.8), ("c", "d", 0.9)]

    first = analyze_graph(entities, relations)
    second = analyze_graph(list(reversed(entities)), list(reversed(relations)))

    assert first == second
    assert first.degree == {"a": 1, "b": 1, "c": 1, "d": 1}
    assert first.weighted_degree == {"a": 0.8, "b": 0.8, "c": 0.9, "d": 0.9}
    assert set(first.community_sizes.values()) == {2}
    assert LOUVAIN_SEED == 0
    assert LOUVAIN_RESOLUTION == 1.0


def test_analysis_retains_isolated_entities() -> None:
    result = analyze_graph(["connected", "isolated"], [])

    assert result.degree == {"connected": 0, "isolated": 0}
    assert len(result.communities) == 2
    assert sum(result.importance.values()) == 1.0
