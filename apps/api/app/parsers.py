import csv
import io
import json
import re
from dataclasses import dataclass, field
from typing import Protocol

from bs4 import BeautifulSoup
from liteparse import LiteParse, ParseError
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
        return html_to_document(html)


class HtmlParser:
    mime_types: tuple[str, ...] = ("text/html",)

    def parse(self, content: bytes) -> ParsedDocument:
        soup = BeautifulSoup(content, "lxml")
        for node in soup(["script", "style", "noscript"]):
            node.decompose()
        title = soup.title.get_text(strip=True) if soup.title else None
        parsed = html_to_document(str(soup))
        return ParsedDocument(
            parsed.text,
            {**parsed.metadata, **({"title": title} if title else {})},
            parsed.segments,
        )


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
            {
                "parser": "pypdf",
                "parser_version": "pypdf",
                "pages": len(pages),
                "non_empty_pages": len(segments),
            },
            segments,
        )


class LiteParsePdfParser:
    """PDF-only LiteParse adapter with explicit OCR routing and no fallback."""

    mime_types: tuple[str, ...] = ("application/pdf",)

    def __init__(
        self,
        ocr_mode: str = "auto",
        dpi: int = 150,
        max_pages: int = 300,
        ocr_workers: int = 1,
        parser_factory: type[LiteParse] = LiteParse,
    ) -> None:
        self.ocr_mode = ocr_mode
        self.dpi = dpi
        self.max_pages = max_pages
        self.ocr_workers = ocr_workers
        self.parser_factory = parser_factory

    def _parser(self, ocr_enabled: bool) -> LiteParse:
        return self.parser_factory(
            ocr_enabled=ocr_enabled,
            ocr_failure_fatal=True,
            quiet=True,
            max_pages=self.max_pages,
            dpi=self.dpi,
            num_workers=self.ocr_workers,
            image_mode="off",
        )

    def parse(self, content: bytes) -> ParsedDocument:
        probe = self._parser(False)
        try:
            complexity = probe.is_complex(content) if self.ocr_mode == "auto" else []
            complex_pages = [item.page_number for item in complexity if item.needs_ocr]
            ocr_requested = self.ocr_mode == "always" or bool(complex_pages)
            result = (self._parser(True) if ocr_requested else probe).parse(content)
        except ParseError as exc:
            raise ValueError(f"LiteParse PDF parsing failed: {exc}") from exc
        segments = tuple(
            ParsedSegment(
                item.text.strip(),
                {
                    "page_number": page.page_num,
                    "bbox": [item.x, item.y, item.x + item.width, item.y + item.height],
                    "bbox_coordinate_system": "pdf_points_top_left_xyxy",
                    "font_name": item.font_name,
                    "font_size": item.font_size,
                    "rotation": item.rotation,
                },
            )
            for page in result.pages
            for item in page.text_items
            if item.text.strip()
        )
        if not segments:
            segments = tuple(
                ParsedSegment(page.text.strip(), {"page_number": page.page_num})
                for page in result.pages
                if page.text.strip()
            )
        return ParsedDocument(
            result.text,
            {
                "parser": "liteparse",
                "parser_version": "2.6.0",
                "pages": result.num_pages,
                "ocr_mode": self.ocr_mode,
                "ocr_requested": ocr_requested,
                "complex_pages": complex_pages,
            },
            segments,
        )


def html_to_document(html: str) -> ParsedDocument:
    soup = BeautifulSoup(html, "lxml")
    body = soup.body or soup
    section_path: list[str] = []
    segments: list[ParsedSegment] = []
    for node in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "table"]):
        text = node.get_text("\n" if node.name in {"pre", "table"} else " ", strip=True)
        if not text:
            continue
        if node.name and node.name.startswith("h"):
            level = int(node.name[1])
            section_path[level - 1 :] = [text]
            continue
        metadata: dict[str, object] = {"block_type": _html_block_type(node.name or "")}
        if section_path:
            metadata["section_title"] = section_path[-1]
            metadata["section_path"] = list(section_path)
        segments.append(ParsedSegment(text, metadata))
    if not segments:
        return ParsedDocument("")
    return ParsedDocument(
        "\n\n".join(segment.text for segment in segments), segments=tuple(segments)
    )


def _html_block_type(name: str) -> str:
    if name == "li":
        return "list"
    if name == "table":
        return "table"
    if name == "pre":
        return "code"
    return "paragraph"


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


def default_registry(pdf_parser: Parser | None = None) -> ParserRegistry:
    registry = ParserRegistry()
    registry.register(TextParser())
    registry.register(CsvParser())
    registry.register(JsonParser())
    registry.register(MarkdownParser())
    registry.register(HtmlParser())
    registry.register(pdf_parser or PdfParser())
    return registry
