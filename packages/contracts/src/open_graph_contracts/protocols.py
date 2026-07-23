"""Runtime-checkable protocols for graph ingestion and storage plugins."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.chunking import TextChunk
    from app.parsers import ParsedDocument
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
