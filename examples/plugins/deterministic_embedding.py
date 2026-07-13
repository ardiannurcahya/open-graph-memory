from __future__ import annotations

from hashlib import sha256

from open_graph_contracts import EmbeddingProvider


class ExampleDeterministicEmbedding:
    name = "example-deterministic"

    def __init__(self, dimensions: int = 8) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        del model
        vectors: list[list[float]] = []
        for text in texts:
            digest = sha256(text.encode("utf-8")).digest()
            vectors.append([digest[i] / 255.0 for i in range(self.dimensions)])
        return vectors


def build_provider() -> EmbeddingProvider:
    return ExampleDeterministicEmbedding()
