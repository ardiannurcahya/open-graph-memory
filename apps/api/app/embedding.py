"""Pluggable embedding providers for vector search and RAG retrieval."""

import hashlib
import math
from typing import Protocol

import httpx
import structlog

from app.config import Settings, get_settings

logger = structlog.get_logger(__name__)


class EmbeddingProvider(Protocol):
    """Protocol for asynchronous text embedding providers."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document chunks."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""
        ...


class DeterministicEmbeddingProvider:
    """Deterministic, zero-dependency embedding provider.

    Produces unit-normalized dense vectors based on token hashing.
    Used for local testing, offline development, and environments
    without an external OpenAI API key.
    """

    def __init__(self, dimensions: int = 1536) -> None:
        self.dimensions = dimensions

    def _embed_single(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        if not text.strip():
            # Return a default unit vector
            vec[0] = 1.0
            return vec

        words = text.lower().split()
        for word in words:
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimensions
            # Weight by word length
            vec[idx] += 1.0 + math.log(1 + len(word))

        # Add a subtle sequence signature from SHA-256
        seq_hash = hashlib.sha256(text.encode("utf-8")).digest()
        for i in range(min(len(seq_hash), 32)):
            idx = (i * 47) % self.dimensions
            vec[idx] += (seq_hash[i] / 255.0) * 0.1

        # L2-normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        else:
            vec[0] = 1.0
        return vec

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_single(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed_single(text)


class OpenAIEmbeddingProvider:
    """OpenAI API embedding provider using text-embedding-3-small or custom models."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions
        self.timeout = timeout

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "input": texts,
            "model": self.model,
            "dimensions": self.dimensions,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # Sort by index in case API returns out of order
        results = sorted(data["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in results]

    async def embed_query(self, text: str) -> list[float]:
        res = await self.embed_texts([text])
        return res[0]


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    """Factory function returning configured embedding provider."""
    cfg = settings or get_settings()
    provider_name = getattr(cfg, "vector_embedding_provider", "deterministic").lower()

    if provider_name == "openai" and cfg.openai_api_key.get_secret_value():
        return OpenAIEmbeddingProvider(
            api_key=cfg.openai_api_key.get_secret_value(),
            base_url=cfg.openai_base_url,
            model=getattr(cfg, "vector_embedding_model", "text-embedding-3-small"),
            dimensions=getattr(cfg, "vector_dimensions", 1536),
        )

    return DeterministicEmbeddingProvider(
        dimensions=getattr(cfg, "vector_dimensions", 1536),
    )
