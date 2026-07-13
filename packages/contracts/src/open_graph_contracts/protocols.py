"""Runtime-checkable protocols for all plugin contract interfaces.

These protocols mirror the shapes defined in app/providers.py, app/storage.py,
app/vector_store.py, app/graph_store.py, app/parsers.py, app/chunking.py,
app/retrieval.py, and open_graph_core/extraction.py, but are @runtime_checkable
so that isinstance() works for registry compatibility validation.

Data classes (VectorPoint, ParsedDocument, TextChunk, Extraction, etc.)
are NOT redefined here — they remain in their original modules to avoid
duplication.  Protocols reference them via type hints only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.chunking import TextChunk
    from app.graph_store import DocumentProjection
    from app.parsers import ParsedDocument
    from app.providers import ChatResult
    from app.retrieval import GraphEvidence
    from app.vector_store import VectorHit, VectorPoint
    from open_graph_core.extraction import Extraction


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Async embedding provider protocol."""

    name: str
    dimensions: int

    async def embed(self, texts: list[str], model: str) -> list[list[float]]: ...


@runtime_checkable
class ChatProvider(Protocol):
    """Async chat completion provider protocol."""

    name: str

    async def chat(self, messages: list[dict[str, str]], model: str) -> ChatResult: ...


@runtime_checkable
class Extractor(Protocol):
    """Graph extraction protocol (synchronous)."""

    def extract(self, text: str) -> Extraction: ...


@runtime_checkable
class Parser(Protocol):
    """Document parser protocol (synchronous)."""

    mime_types: tuple[str, ...]

    def parse(self, content: bytes) -> ParsedDocument: ...


@runtime_checkable
class Chunker(Protocol):
    """Text chunker protocol (synchronous)."""

    version: str

    def split(self, document_id: str, text: str) -> list[TextChunk]: ...


@runtime_checkable
class ObjectStore(Protocol):
    """Async object/blob store protocol."""

    async def upload(self, key: str, stream: object, content_type: str) -> None: ...
    async def download(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...


@runtime_checkable
class VectorStore(Protocol):
    """Async vector store protocol."""

    async def upsert(self, points: list[VectorPoint]) -> None: ...

    async def search(
        self, vector: list[float], project_id: str, dataset_id: str, limit: int
    ) -> list[VectorHit]: ...


@runtime_checkable
class GraphStore(Protocol):
    """Async graph store protocol."""

    async def bootstrap(self) -> None: ...
    async def project_document(self, projection: DocumentProjection) -> None: ...
    async def reconcile_dataset(self, project_id: str, dataset_id: str) -> None: ...
    async def delete_document(
        self, project_id: str, dataset_id: str, document_id: str
    ) -> None: ...

    async def traverse(
        self,
        project_id: str,
        dataset_id: str,
        seed_chunk_ids: list[str],
        seed_entity_names: list[str],
        max_depth: int,
        fanout: int,
        seed_limit: int,
    ) -> list[GraphEvidence]: ...


@runtime_checkable
class GraphRetriever(Protocol):
    """Async graph retriever protocol (traversal-only view of GraphStore)."""

    async def traverse(
        self,
        project_id: str,
        dataset_id: str,
        seed_chunk_ids: list[str],
        seed_entity_names: list[str],
        max_depth: int,
        fanout: int,
        seed_limit: int,
    ) -> list[GraphEvidence]: ...
