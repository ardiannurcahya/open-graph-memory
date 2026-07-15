from app.community_reports import community_report_input_hash
from app.config import Settings
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


def test_community_report_input_hash_is_stable_and_versioned() -> None:
    settings = Settings()
    first = community_report_input_hash("run_1", "community_1", settings)
    assert first == community_report_input_hash("run_1", "community_1", settings)
    assert first != community_report_input_hash("run_1", "community_2", settings)
    assert first != community_report_input_hash(
        "run_1", "community_1", Settings(community_report_version="community-report-v2")
    )


def test_community_report_provider_and_model_default_to_chat() -> None:
    settings = Settings(chat_provider="openai", chat_model="gpt-test", openai_api_key="test")
    assert settings.resolved_community_report_provider == "openai"
    assert settings.resolved_community_report_model == "gpt-test"
