import hashlib
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TextChunk:
    id: str
    index: int
    text: str
    token_count: int
    start_char: int
    end_char: int


class Chunker(Protocol):
    version: str

    def split(self, document_id: str, text: str) -> list[TextChunk]: ...


class RecursiveTextChunker:
    version = "recursive-v1"

    def __init__(self, size: int = 1200, overlap: int = 200, maximum: int = 500) -> None:
        if size <= overlap or overlap < 0:
            raise ValueError("chunk size must exceed non-negative overlap")
        self.size, self.overlap, self.maximum = size, overlap, maximum

    def split(self, document_id: str, text: str) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        start = 0
        while start < len(text) and len(chunks) < self.maximum:
            end = min(start + self.size, len(text))
            if end < len(text):
                separators = ("\n\n", "\n", ". ", " ")
                candidates = [text.rfind(separator, start, end) for separator in separators]
                boundary = max(candidates)
                if boundary > start + self.size // 2:
                    end = boundary + 1
            value = text[start:end].strip()
            if value:
                index = len(chunks)
                identity = f"{document_id}:{self.version}:{index}:{value}".encode()
                digest = hashlib.sha256(identity).hexdigest()[:24]
                chunks.append(
                    TextChunk(f"chunk_{digest}", index, value, len(value.split()), start, end)
                )
            if end == len(text):
                break
            start = max(start + 1, end - self.overlap)
        if start < len(text) and len(chunks) >= self.maximum:
            raise ValueError("document exceeds maximum chunk count")
        return chunks
