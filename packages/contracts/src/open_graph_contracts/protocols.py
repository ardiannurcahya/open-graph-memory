"""Runtime-checkable protocols for graph ingestion and storage plugins."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.chunking import TextChunk
    from app.graph_store import DocumentProjection
    from app.parsers import ParsedDocument
    from app.retrieval import GraphEvidence
    from open_graph_core.extraction import Extraction


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
