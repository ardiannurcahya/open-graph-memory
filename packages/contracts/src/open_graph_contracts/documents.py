"""Shared document parsing and chunking value objects.

These frozen dataclasses are the public interchange format between document
parsers, chunkers, and the ingestion pipeline. They live in the contracts
package so plugin authors can implement Parser/Chunker without importing the
application package.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsedSegment:
    text: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    metadata: dict[str, object] = field(default_factory=dict)
    segments: tuple[ParsedSegment, ...] = ()


@dataclass(frozen=True)
class TextChunk:
    id: str
    index: int
    text: str
    token_count: int
    start_char: int
    end_char: int
    metadata: dict[str, object] = field(default_factory=dict)
    segment_part: int = 1
    segment_count: int = 1
