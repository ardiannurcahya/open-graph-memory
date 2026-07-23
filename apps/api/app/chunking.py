import hashlib
from dataclasses import dataclass, field
from typing import Protocol

from app.parsers import ParsedDocument, ParsedSegment


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


class Chunker(Protocol):
    version: str

    def split(self, document_id: str, text: str) -> list[TextChunk]: ...


class RecursiveTextChunker:
    version = "recursive-v5-page-aware-exact-offsets"

    def __init__(self, size: int = 1200, overlap: int = 200, maximum: int = 5000) -> None:
        if size <= overlap or overlap < 0:
            raise ValueError("chunk size must exceed non-negative overlap")
        self.size, self.overlap, self.maximum = size, overlap, maximum

    def split(self, document_id: str, text: str) -> list[TextChunk]:
        return self._split_segments(document_id, (ParsedSegment(text),))

    def split_document(self, document_id: str, document: ParsedDocument) -> list[TextChunk]:
        return self._split_segments(
            document_id, document.segments or (ParsedSegment(document.text),)
        )

    def _split_segments(
        self, document_id: str, segments: tuple[ParsedSegment, ...]
    ) -> list[TextChunk]:
        drafts: list[tuple[str, int, int, dict[str, object]]] = []
        for segment in segments:
            text = segment.text
            if isinstance(segment.metadata.get("page_number"), int):
                if len(drafts) >= self.maximum:
                    raise ValueError("document exceeds maximum chunk count")
                left, right = 0, len(text)
                while left < right and text[left].isspace():
                    left += 1
                while right > left and text[right - 1].isspace():
                    right -= 1
                if left < right:
                    drafts.append(
                        (
                            text[left:right],
                            left,
                            right,
                            {
                                **segment.metadata,
                                "segment_start_char": left,
                                "segment_end_char": right,
                                "start_char": left,
                                "end_char": right,
                                "segment_part": 1,
                                "segment_count": 1,
                            },
                        )
                    )
                continue
            start = 0
            segment_drafts: list[tuple[str, int, int, dict[str, object]]] = []
            while start < len(text):
                if len(drafts) + len(segment_drafts) >= self.maximum:
                    raise ValueError("document exceeds maximum chunk count")
                end = min(start + self.size, len(text))
                if end < len(text):
                    boundary = max(
                        text.rfind(separator, start, end) for separator in ("\n\n", "\n", ". ", " ")
                    )
                    if boundary > start + self.size // 2:
                        end = boundary + 1
                left, right = start, end
                while left < right and text[left].isspace():
                    left += 1
                while right > left and text[right - 1].isspace():
                    right -= 1
                value = text[left:right]
                if value:
                    segment_drafts.append((value, left, right, segment.metadata))
                if end == len(text):
                    break
                start = max(start + 1, end - self.overlap)
            count = len(segment_drafts)
            drafts.extend(
                (
                    text,
                    start,
                    end,
                    {
                        **metadata,
                        # Offsets are segment-local, not concatenated-document offsets.
                        "segment_start_char": start,
                        "segment_end_char": end,
                        # Compatibility aliases. New consumers must use segment_* names.
                        "start_char": start,
                        "end_char": end,
                        "segment_part": part,
                        "segment_count": count,
                    },
                )
                for part, (text, start, end, metadata) in enumerate(segment_drafts, 1)
            )
        chunks = []
        for index, (value, start, end, metadata) in enumerate(drafts):
            identity = f"{document_id}:{self.version}:{index}:{value}".encode()
            chunks.append(
                TextChunk(
                    f"chunk_{hashlib.sha256(identity).hexdigest()[:24]}",
                    index,
                    value,
                    len(value.split()),
                    start,
                    end,
                    metadata,
                    metadata["segment_part"],  # type: ignore[arg-type]
                    metadata["segment_count"],  # type: ignore[arg-type]
                )
            )
        return chunks
