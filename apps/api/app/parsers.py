import csv
import io
import re
from dataclasses import dataclass, field
from typing import Protocol

from bs4 import BeautifulSoup
from markdown_it import MarkdownIt
from pypdf import PdfReader

CSV_FIELD_SIZE_LIMIT = 10 * 1024 * 1024
CSV_SAMPLE_SIZE = 4096
CSV_DELIMITERS = (",", ";", "\t", "|")


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
        text = content.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").strip()
        return ParsedDocument(text)


class CsvParser:
    mime_types: tuple[str, ...] = ("text/csv", "application/csv")

    def parse(self, content: bytes) -> ParsedDocument:
        previous_limit = csv.field_size_limit()
        if previous_limit < CSV_FIELD_SIZE_LIMIT:
            csv.field_size_limit(CSV_FIELD_SIZE_LIMIT)
        text = content.decode("utf-8-sig", errors="replace")
        if text.count('"') % 2:
            return fallback_csv_parse(text)
        try:
            dialect = csv.Sniffer().sniff(
                text[:CSV_SAMPLE_SIZE], delimiters="".join(CSV_DELIMITERS)
            )
        except csv.Error:
            dialect = csv.excel
        try:
            rows = list(csv.reader(io.StringIO(text, newline=""), dialect))
        except csv.Error:
            return fallback_csv_parse(text)
        return rows_to_document(rows)


def rows_to_document(rows: list[list[str]]) -> ParsedDocument:
    rows = [[value.strip() for value in row] for row in rows if any(value.strip() for value in row)]
    if not rows:
        return ParsedDocument("")
    header, *body = rows
    lines = [format_csv_row(header, row) for row in body]
    return ParsedDocument("\n".join(lines), {"rows": len(body), "columns": header})


def fallback_csv_parse(text: str) -> ParsedDocument:
    source_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not source_lines:
        return ParsedDocument("")
    delimiter = max(CSV_DELIMITERS, key=lambda item: source_lines[0].count(item))
    header = [value.strip().strip('"') for value in source_lines[0].split(delimiter)]
    rows = []
    for line in source_lines[1:]:
        values = [value.strip().strip('"') for value in line.split(delimiter)]
        rows.append(normalize_csv_row(header, values))
    lines = [format_csv_row(header, row) for row in rows]
    return ParsedDocument(
        "\n".join(lines), {"rows": len(rows), "columns": header, "repaired": True}
    )


def normalize_csv_row(header: list[str], row: list[str]) -> list[str]:
    if len(row) <= len(header):
        return row
    return [*row[: len(header) - 1], " ".join(row[len(header) - 1 :])]


def format_csv_row(header: list[str], row: list[str]) -> str:
    return "; ".join(f"{key}: {value}" for key, value in zip(header, row, strict=False))


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
