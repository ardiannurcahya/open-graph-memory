import csv
import io
import json
import re
from dataclasses import dataclass, field
from typing import Protocol

from bs4 import BeautifulSoup
from markdown_it import MarkdownIt
from pypdf import PdfReader

CSV_FIELD_SIZE_LIMIT = 10 * 1024 * 1024
CSV_SAMPLE_SIZE = 4096
CSV_DELIMITERS = (",", ";", "\t", "|")


def reject_json_constant(constant: str) -> object:
    raise ValueError(f"invalid JSON constant: {constant}")


@dataclass(frozen=True)
class ParsedSegment:
    text: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    metadata: dict[str, object] = field(default_factory=dict)
    segments: tuple[ParsedSegment, ...] = ()


class Parser(Protocol):
    mime_types: tuple[str, ...]

    def parse(self, content: bytes) -> ParsedDocument: ...


class TextParser:
    mime_types: tuple[str, ...] = ("text/plain",)

    def parse(self, content: bytes) -> ParsedDocument:
        return ParsedDocument(
            content.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").strip()
        )


class CsvParser:
    mime_types: tuple[str, ...] = ("text/csv", "application/csv")

    def parse(self, content: bytes) -> ParsedDocument:
        previous_limit = csv.field_size_limit()
        try:
            if previous_limit < CSV_FIELD_SIZE_LIMIT:
                csv.field_size_limit(CSV_FIELD_SIZE_LIMIT)
            text = content.decode("utf-8-sig", errors="replace")
            if text.count('"') % 2:
                raise ValueError("malformed CSV: unmatched quote")
            try:
                dialect = csv.Sniffer().sniff(
                    text[:CSV_SAMPLE_SIZE], delimiters="".join(CSV_DELIMITERS)
                )
            except csv.Error:
                dialect = csv.excel
            try:
                rows = list(csv.reader(io.StringIO(text, newline=""), dialect, strict=True))
            except csv.Error as exc:
                raise ValueError(f"malformed CSV: {exc}") from exc
            return rows_to_document(rows)
        finally:
            csv.field_size_limit(previous_limit)


def rows_to_document(rows: list[list[str]]) -> ParsedDocument:
    rows = [[value.strip() for value in row] for row in rows if any(value.strip() for value in row)]
    if not rows:
        return ParsedDocument("")
    header, *body = rows
    segments = tuple(
        ParsedSegment(
            format_csv_row(header, row),
            {
                "record_number": record_number,
                "columns": header,
                "values": {key: value for key, value in zip(header, row, strict=False)},
            },
        )
        for record_number, row in enumerate(body, 1)
    )
    return ParsedDocument(
        "\n".join(segment.text for segment in segments),
        {"rows": len(body), "columns": header},
        segments,
    )


def format_csv_row(header: list[str], row: list[str]) -> str:
    return "; ".join(f"{key}: {value}" for key, value in zip(header, row, strict=False))


class JsonParser:
    mime_types: tuple[str, ...] = ("application/json", "text/json")

    def parse(self, content: bytes) -> ParsedDocument:
        try:
            value = json.loads(content.decode("utf-8-sig"), parse_constant=reject_json_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc
        if isinstance(value, list):
            segments = tuple(
                ParsedSegment(
                    format_json_value(item),
                    {"record_number": record_number, "json_path": f"$[{record_number - 1}]"},
                )
                for record_number, item in enumerate(value, 1)
            )
            return ParsedDocument(
                "\n".join(segment.text for segment in segments),
                {"root_type": "array", "records": len(segments)},
                segments,
            )
        return ParsedDocument(
            format_json_value(value),
            {"root_type": json_type_name(value), "json_path": "$"},
        )


def format_json_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def json_type_name(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return "object"


class MarkdownParser:
    mime_types: tuple[str, ...] = ("text/markdown",)

    def parse(self, content: bytes) -> ParsedDocument:
        html = MarkdownIt().render(content.decode("utf-8"))
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
        segments = tuple(
            ParsedSegment(text.strip(), {"page_number": page_number})
            for page_number, text in enumerate(pages, 1)
            if text.strip()
        )
        return ParsedDocument(
            "\n\n".join(segment.text for segment in segments),
            {"pages": len(pages), "non_empty_pages": len(segments)},
            segments,
        )


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
        if mime_type == "text/plain" and filename.lower().endswith(".json"):
            parser = self._parsers.get("application/json")
        if parser is None:
            raise ValueError(f"unsupported MIME type: {mime_type}")
        parsed = parser.parse(content)
        return ParsedDocument(
            re.sub(r"\n{3,}", "\n\n", parsed.text),
            parsed.metadata,
            tuple(
                ParsedSegment(re.sub(r"\n{3,}", "\n\n", segment.text), segment.metadata)
                for segment in parsed.segments
            ),
        )


def default_registry() -> ParserRegistry:
    registry = ParserRegistry()
    registry.register(TextParser())
    registry.register(CsvParser())
    registry.register(JsonParser())
    registry.register(MarkdownParser())
    registry.register(HtmlParser())
    registry.register(PdfParser())
    return registry
