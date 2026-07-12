import csv
import io
import re
from dataclasses import dataclass, field
from typing import Protocol

from bs4 import BeautifulSoup
from markdown_it import MarkdownIt
from pypdf import PdfReader


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    metadata: dict[str, object] = field(default_factory=dict)


class Parser(Protocol):
    mime_types: tuple[str, ...]

    def parse(self, content: bytes) -> ParsedDocument: ...


class TextParser:
    mime_types: tuple[str, ...] = ("text/plain",)

    def parse(self, content: bytes) -> ParsedDocument:
        return ParsedDocument(content.decode("utf-8").replace("\r\n", "\n").strip())


class CsvParser:
    mime_types: tuple[str, ...] = ("text/csv", "application/csv")

    def parse(self, content: bytes) -> ParsedDocument:
        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
        if not rows:
            return ParsedDocument("")
        header, *body = rows
        text = "\n".join(
            "; ".join(f"{key}: {value}" for key, value in zip(header, row, strict=False))
            for row in body
        )
        return ParsedDocument(text, {"rows": len(body), "columns": header})


class MarkdownParser:
    mime_types: tuple[str, ...] = ("text/markdown",)

    def parse(self, content: bytes) -> ParsedDocument:
        source = content.decode("utf-8")
        html = MarkdownIt().render(source)
        return ParsedDocument(BeautifulSoup(html, "lxml").get_text("\n", strip=True))


class HtmlParser:
    mime_types: tuple[str, ...] = ("text/html",)

    def parse(self, content: bytes) -> ParsedDocument:
        soup = BeautifulSoup(content, "lxml")
        for node in soup(["script", "style", "noscript"]):
            node.decompose()
        title = soup.title.get_text(strip=True) if soup.title else None
        return ParsedDocument(soup.get_text("\n", strip=True), {"title": title} if title else {})


class PdfParser:
    mime_types: tuple[str, ...] = ("application/pdf",)

    def parse(self, content: bytes) -> ParsedDocument:
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return ParsedDocument("\n\n".join(pages).strip(), {"pages": len(pages)})


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, Parser] = {}

    def register(self, parser: Parser) -> None:
        for mime in parser.mime_types:
            self._parsers[mime] = parser

    def parse(self, mime_type: str, content: bytes, filename: str = "") -> ParsedDocument:
        parser = self._parsers.get(mime_type)
        if mime_type == "text/plain" and filename.lower().endswith(".md"):
            parser = self._parsers.get("text/markdown")
        if mime_type == "text/plain" and filename.lower().endswith(".csv"):
            parser = self._parsers.get("text/csv")
        if parser is None:
            raise ValueError(f"unsupported MIME type: {mime_type}")
        parsed = parser.parse(content)
        return ParsedDocument(re.sub(r"\n{3,}", "\n\n", parsed.text), parsed.metadata)


def default_registry() -> ParserRegistry:
    registry = ParserRegistry()
    registry.register(TextParser())
    registry.register(CsvParser())
    registry.register(MarkdownParser())
    registry.register(HtmlParser())
    registry.register(PdfParser())
    return registry
