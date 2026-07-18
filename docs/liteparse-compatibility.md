# LiteParse 2.6.0 Compatibility

Verified integration surface for initial PDF-only rollout:

- Public entry point: `liteparse.LiteParse`.
- `parse()` and `is_complex()` accept PDF bytes directly.
- `is_complex()` returns one-based `PageComplexityStats` records with `needs_ocr`.
- `parse()` returns `ParseResult.pages`; each `ParsedPage` exposes one-based `page_num`,
  dimensions, text, and spatial `text_items`.
- `TextItem` geometry is `(x, y, width, height)` in top-left-origin page coordinates.
  Adapter stores normalized `(x1, y1, x2, y2)` block-level bounds.
- Python API does not expose semantic paragraph, heading, table, or section blocks. Adapter
  therefore preserves spatial items without inventing semantic labels.
- CPython 3.12 wheels exist for Linux x86-64 and aarch64. Local OCR needs Tesseract runtime
  libraries and English trained data, installed in API and worker images.
- PDF byte parsing does not require persistent temporary files. Images and screenshots stay off.

Runtime preset: DPI 150, one OCR worker, maximum 300 pages, fatal OCR failures, and explicit
application-side routing for `auto`, `always`, or `disabled` modes.

Performance remains corpus-dependent. Production rollout stays opt-in until container parsing
and memory measurements run against representative PDFs under worker resource limits.
