from open_graph_contracts import Capability
from open_graph_contracts import __all__ as public_names


def test_contract_surface_is_graph_ingestion_only() -> None:
    assert {capability.value for capability in Capability} == {
        "extraction",
        "parser",
        "chunker",
        "object_store",
        "graph_store",
        "graph_retriever",
    }
    assert {"EmbeddingProvider", "ChatProvider", "VectorStore"}.isdisjoint(public_names)
