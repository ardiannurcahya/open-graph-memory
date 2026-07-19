# LiteParse Knowledge Graph Implementation Plan

## Goal

Build a lightweight, evidence-safe knowledge graph pipeline with better PDF parsing,
section-aware chunking, parallel LLM extraction, durable document consolidation, and
conservative entity resolution.

The initial scope prioritizes PDF quality and graph correctness. It does not include RAG,
AI agents, broad Office conversion, source-code graphs, or embedding-based automatic merges.

## Architecture Decisions

| Area                       | Decision                                                   |
| -------------------------- | ---------------------------------------------------------- |
| LiteParse                  | Use only for PDF in initial release                        |
| OCR                        | Run only for pages detected as complex                     |
| DOCX/PPTX/XLSX             | Defer; avoid LibreOffice dependency in initial release     |
| CSV/JSON/HTML/Markdown/TXT | Keep native parsers                                        |
| Source code                | Defer to AST/tree-sitter implementation                    |
| Sections                   | Store as chunk metadata; do not add a section table yet    |
| LLM extraction             | Extract entities and relations in one structured call      |
| Chunk context              | Use short neighboring excerpts, not rolling memory         |
| Consolidation              | Run one durable document-level pass after chunk extraction |
| Entity resolution          | Exact, typed, scoped, and evidence-backed                  |
| Authoritative database     | PostgreSQL                                                 |
| Neo4j                      | Rebuildable traversal projection                           |
| Visualization              | Show semantic entities and relations by default            |
| Rollout                    | Opt-in configuration                                       |

## Target Pipeline

```text
Upload
  |
  v
Parser Router
  |-- PDF/scan       -> LiteParse
  |-- Markdown/HTML  -> native section-aware parser
  |-- CSV/JSON       -> native record-aware parser
  |-- TXT            -> native text parser
  `-- Source code    -> AST parser, deferred
  |
  v
Structural Cleanup
  |
  v
Section-Aware Chunking
  |
  v
Parallel Joint Entity + Relation Extraction
  |
  v
Durable Document Consolidation
  |
  v
Exact Entity and Alias Resolution
  |
  v
PostgreSQL Graph Persistence
  |
  v
Neo4j Projection + Analytics
  |
  v
Semantic Graph Visualization
```

## Stage 1: LiteParse Compatibility Spike

### Purpose

Verify LiteParse Python API, structured output, page metadata, OCR routing, and container
compatibility before replacing the current PDF parser.

### Work

1. Pin `liteparse==2.6.0` or a later patch release that passes repository tests.
2. Parse representative digital and scanned PDF fixtures from bytes.
3. Inspect `result.text`, `result.pages`, text blocks, page numbers, and bounding boxes.
4. Run `is_complex()` against digital and scanned fixtures.
5. Measure parse latency, peak memory, wheel size, and worker startup impact.
6. Verify Python 3.12 Linux wheel availability.
7. Verify operation under non-root container user `65532`.
8. Record actual Python result shape in adapter tests instead of relying only on README examples.

### Artifacts

```text
Digital PDF fixture
Scanned PDF fixture
LiteParse compatibility test
Normalized ParsedDocument example
Short parsing benchmark report
```

### Pass Conditions

```text
Digital PDF parses without OCR
Scanned PDF is detected as requiring OCR
Page numbers remain stable
Structured block data can be normalized
No persistent temporary file is required
API and worker images can import LiteParse
```

## Stage 2: PDF Parser Adapter

### Files

```text
pyproject.toml
uv.lock
apps/api/app/parsers.py
apps/api/tests/test_ingestion.py
apps/api/Dockerfile
apps/worker/Dockerfile
```

### Adapter

Add an explicit parser implementation:

```python
class LiteParsePdfParser:
    mime_types = ("application/pdf",)

    def parse(self, content: bytes) -> ParsedDocument:
        ...
```

Use complexity routing:

```text
PDF bytes
  |
  v
LiteParse is_complex
  |-- simple  -> parse without OCR
  `-- complex -> parse with OCR
```

Initial runtime preset:

```text
Output format: structured JSON
DPI: 150
OCR workers: 1
Maximum pages: 300
Image extraction: off
Screenshots: off
```

Normalize output to the existing internal parser contract:

```python
ParsedDocument(
    text=full_text,
    metadata={
        "parser": "liteparse",
        "parser_version": "2.6.0",
        "pages": page_count,
        "ocr_used": ocr_used,
        "complex_pages": complex_page_numbers,
    },
    segments=(
        ParsedSegment(
            text=block_text,
            metadata={
                "page_number": 1,
                "block_type": "paragraph",
                "section_title": "Introduction",
                "section_path": ["Introduction"],
                "bbox": [72, 110, 530, 310],
            },
        ),
    ),
)
```

### Failure Policy

LiteParse runtime or provider failures must fail ingestion explicitly and use the existing
retry mechanism. Do not silently fall back to `pypdf`, because silent fallback creates
different graph quality without an audit signal.

Keep `pypdf` available as an explicit rollout backend:

```env
PDF_PARSER=pypdf
```

## Stage 3: Structural Cleanup

Process LiteParse blocks before chunking.

### Rules

1. Normalize line endings and excessive blank lines.
2. Preserve page boundaries.
3. Preserve heading hierarchy.
4. Preserve tables as logical blocks when block size is safe.
5. Mark paragraph, heading, list, table, caption, and footnote block types when available.
6. Detect repeated headers and footers using normalized text and stable page position.
7. Do not remove every margin block; headings and scientific footnotes may occupy margins.
8. Do not infer sections from font size alone.
9. Store block-level bounding boxes only; avoid token-level metadata growth in initial release.

Repeated artifact candidate:

```text
Same normalized text pattern
+ similar page position
+ present on most pages
= repeated header/footer candidate
```

Example normalized metadata:

```json
{
  "page_number": 5,
  "section_title": "CNN Architecture",
  "section_path": ["Methodology", "CNN Architecture"],
  "block_type": "paragraph",
  "bbox": [72, 110, 530, 310]
}
```

## Stage 4: Section-Aware Chunking

### Files

```text
apps/api/app/chunking.py
apps/api/app/ingestion.py
apps/api/tests/test_ingestion.py
```

Keep initial chunk sizing near current defaults:

```text
Size: 1200 characters
Overlap: 200 characters
```

### Changes

1. Prefer paragraph and heading boundaries.
2. Do not mix unrelated sections into one chunk.
3. Keep page, section path, block type, and source offsets.
4. Pass heading context through metadata instead of duplicating it into every chunk body.
5. Preserve current record isolation for CSV and JSON.
6. Increment `PIPELINE_VERSION` because chunk identity and metadata semantics change.
7. Update parser and chunker version metadata.

Example chunk:

```json
{
  "chunk_index": 8,
  "text": "Backend menggunakan FastAPI dan PostgreSQL.",
  "metadata": {
    "page_number": 4,
    "section_title": "LLM Agent Trade Platform",
    "section_path": ["Projects", "LLM Agent Trade Platform"],
    "block_type": "paragraph",
    "segment_part": 2,
    "segment_count": 3
  }
}
```

Do not add a `sections` table in this stage. Add one later only if section navigation,
editing, search, or graph projection creates a concrete requirement.

## Stage 5: Context-Aware Chunk Extraction

### Files

```text
packages/core/src/open_graph_core/extraction.py
apps/api/app/graph_pipeline.py
apps/api/app/plugin_registry.py
apps/api/tests/test_extraction.py
apps/api/tests/test_graph_pipeline.py
```

Keep public plugin contract compatible:

```python
class Extractor(Protocol):
    def extract(self, text: str) -> Extraction: ...
```

Add a private optional contextual extraction protocol. Existing deterministic, NLP, and
third-party extractors continue to work without contextual methods.

### Context Per Chunk

```text
Document filename/title
Section title/path
Page number
Chunk index and total count
Previous excerpt: 300-500 characters
Target chunk
Next excerpt: 300-500 characters
```

Prompt requirements:

```text
TARGET CHUNK is the factual source.
Neighbor excerpts may only resolve references and pronouns.
Every quote must be an exact TARGET CHUNK substring.
Do not emit relations from co-occurrence alone.
Every relation endpoint must be present in emitted entities.
```

All chunk contexts are built before provider calls, so extraction remains parallel and
does not depend on rolling chat memory.

### Joint Schema

Extract entities and relations in one provider call:

```json
{
  "entities": [
    {
      "name": "FastAPI",
      "type": "Technology",
      "confidence": 0.95,
      "aliases": []
    }
  ],
  "relations": [
    {
      "source": "LLM Agent Trade Platform",
      "source_type": "Project",
      "type": "USES",
      "target": "FastAPI",
      "target_type": "Technology",
      "confidence": 0.91,
      "quote": "Backend menggunakan FastAPI."
    }
  ]
}
```

Entity and relation extraction remain logically separate concerns but share one structured
request to keep endpoint names, evidence, latency, and cost consistent.

## Stage 6: Durable Raw Extraction

### Migration

```text
apps/api/migrations/versions/0018_document_graph_consolidation.py
```

Add nullable `JSONB` to `graph_extraction_runs`:

```text
raw_extraction
```

After successful validation:

```python
run.raw_extraction = extraction.model_dump(mode="json")
run.status = RunStatus.SUCCEEDED
```

Benefits:

```text
Successful chunks are not called again during retry
Consolidation can rebuild from PostgreSQL
Original provider output remains auditable
Existing parallel batch checkpoints remain useful
Worker crashes do not lose completed extraction work
```

## Stage 7: Durable Document Consolidation

Add a `graph_consolidation_runs` table.

### Columns

```text
id
project_id
dataset_id
document_id
snapshot_hash
extractor_version
consolidation_version
prompt_version
status
output JSONB
error_message
created_at
updated_at
completed_at
```

Unique identity:

```text
document_id
snapshot_hash
extractor_version
consolidation_version
```

Snapshot hash uses stable ordered inputs:

```text
Chunk ID
Chunk index
Chunk text hash
Raw extraction hash
Relevant page and section metadata
```

### Consolidation Input

Send extraction summaries, not full document text:

```json
{
  "chunk_id": "chunk_2",
  "section_path": ["Projects", "Trading"],
  "entities": [],
  "relations": [],
  "source_mentions": []
}
```

Small exact excerpts may accompany evidence references. Do not resend every complete chunk.

### Consolidation Responsibilities

```text
Select canonical entity names
Resolve explicit aliases
Resolve document-scoped references
Remove duplicate relation proposals
Propose evidence-backed cross-chunk relations
Retain concrete evidence chunk IDs
```

### Prohibited Behavior

```text
Adding facts without evidence
Global fuzzy entity merging
Creating semantic-similarity relations
Rewriting evidence quotes
Treating document co-occurrence as a relation
```

## Stage 8: Alias and Entity Resolution

Use existing `entity_aliases` as the canonical alias registry.

Add an evidence association table:

```text
entity_alias_evidence
```

Columns:

```text
alias_id
evidence_id
created_at
```

Primary key:

```text
(alias_id, evidence_id)
```

Resolution order:

```text
1. Exact normalized canonical name + normalized type
2. Exact explicit alias + normalized type
3. Explicit acronym/full-name evidence
4. Unique untyped exact match
5. Otherwise remain unresolved or needs_review
```

Do not auto-merge from fuzzy strings or embeddings alone.

Safe example:

```text
CNN <-> Convolutional Neural Network
```

Merge only when source evidence supports the alias relationship.

Ambiguous example:

```text
AI -> Artificial Intelligence
AI -> Adobe Illustrator
```

Keep unresolved unless document context and evidence identify one unique entity.

## Stage 9: Evidence Validation

Validate every LLM artifact server-side before persistence.

### Validation Rules

```text
Evidence chunk belongs to target document
Quote is non-empty
Quote is an exact substring of chunk text
Offsets are recomputed by server
Source entity exists
Target entity exists
Endpoint types match
Self-relations are rejected
Alias has direct source evidence
Project and dataset scopes match
Unknown or duplicate chunk references are rejected
```

Do not use fuzzy quote matching. Invalid output must not become graph state.

One relation may have multiple evidence rows:

```text
Chunk 1 introduces project subject
Chunk 2 contains technology-use statement
```

Every citation must point to a concrete source chunk. Do not create synthetic evidence
chunks.

## Stage 10: Final Pipeline Ordering

Final `extract_document()` flow:

```text
Load ordered chunks
Build contextual extraction inputs
Extract pending chunks in parallel
Persist raw extraction per batch
Commit checkpoint
Renew job lease
Load all successful raw extraction
Load or run document consolidation
Validate consolidation and evidence
Persist canonical entities, aliases, relations, and evidence
Commit consolidation state
Renew job lease
Project PostgreSQL state to Neo4j
Refresh graph analytics
Commit
Complete graph job
```

Retry behavior:

```text
Consolidation fails
  -> successful chunk runs stay complete
  -> graph job retries consolidation

Projection or analytics fails
  -> chunk extraction is not repeated
  -> successful consolidation is not repeated
  -> projection rebuilds from PostgreSQL
```

## Stage 11: Configuration

Add settings with safe defaults:

```env
PDF_PARSER=pypdf
LITEPARSE_OCR_MODE=auto
LITEPARSE_DPI=150
LITEPARSE_MAX_PAGES=300
LITEPARSE_OCR_WORKERS=1
LITEPARSE_IMAGE_MODE=off

GRAPH_DOCUMENT_CONSOLIDATION_ENABLED=false
GRAPH_DOCUMENT_CONSOLIDATION_VERSION=graph-consolidation-v1
GRAPH_DOCUMENT_CONSOLIDATION_PROMPT_VERSION=graph-consolidation-prompt-v1
GRAPH_DOCUMENT_CONSOLIDATION_MAX_CHARS=100000
GRAPH_DOCUMENT_CONTEXT_EXCERPT_CHARS=500
```

Validation rules:

```text
PDF parser must be pypdf or liteparse
OCR mode must be auto, always, or disabled
DPI, page limit, and worker count must be positive
Consolidation is initially valid only for OpenAI-compatible extractor
Consolidation versions and prompt versions must be non-empty
Consolidation character limit must be positive
```

Activation example after validation:

```env
PDF_PARSER=liteparse
GRAPH_EXTRACTOR_PROVIDER=openai
GRAPH_EXTRACTOR_VERSION=graph-extractor-v2
GRAPH_DOCUMENT_CONSOLIDATION_ENABLED=true
GRAPH_DOCUMENT_CONSOLIDATION_VERSION=graph-consolidation-v1
```

Changing extraction or consolidation semantics requires a version bump so old jobs and
runs are not treated as current.

## Stage 12: Cleanup and Re-Extraction

Update graph garbage collection and deletion lifecycle.

Expected cascade:

```text
Delete document
  -> delete chunk extraction runs
  -> delete consolidation runs
  -> delete document evidence
  -> delete alias-evidence associations
  -> remove aliases with no remaining evidence
  -> remove relations with no remaining evidence
  -> remove entities with no evidence or supported relations
```

Shared entities, aliases, and relations survive while evidence from another document
remains.

PostgreSQL remains authoritative. Neo4j cleanup and rebuild follow persisted PostgreSQL
state.

## Stage 13: Visualization and Review UX

Default canvas displays only semantic graph content:

```text
Project
Technology
Concept
Person
Organization
Dataset
Other canonical entity types
Evidence-backed relations
```

Do not display every document, section, chunk, and evidence item as a canvas node by
default.

Selected-node or relation panel displays:

```text
Document
Section path
Page number
Exact quote
Bounding box when available
Confidence
Review state
Extractor and consolidation version
```

Initial UX improvements:

```text
Entity-type/community color mode
Adaptive labels based on zoom and importance
Relation confidence filter
Approve/reject relation workflow
Alias and evidence inspection
```

Manual merge/split editing is deferred until persistence and provenance behavior is stable.

## Testing Plan

### Parser Tests

```text
Digital PDF without OCR
Scanned PDF with automatic OCR
Mixed digital/scanned pages
Multi-column PDF
Table-containing PDF
Repeated header/footer removal
Blank pages and stable page numbering
Malformed and encrypted PDF behavior
Maximum-page enforcement
Non-root container execution
Native CSV/JSON/HTML/Markdown/TXT regression coverage
```

### Chunking Tests

```text
Section metadata survives chunking
Chunks do not mix unrelated sections
Page and record boundaries remain stable
Long sections split deterministically
Overlap does not create invalid offsets
Chunk IDs change with pipeline version
```

### Extraction Tests

```text
Joint entity/relation schema is strict
Neighbor context resolves pronouns
Neighbor context cannot become unsupported evidence
Quote must come from target chunk
Extraction remains parallel
Existing extract-only plugins remain compatible
Malformed provider output follows explicit failure policy
```

### Consolidation Tests

```text
Subject in chunk 1 and relation in chunk 2 become connected
Consolidation runs after all chunks succeed
Consolidation runs once per snapshot
Retry does not repeat successful chunk calls
Projection retry does not repeat successful consolidation
Unknown evidence chunk is rejected
Fabricated quote is rejected
Alias collision remains unresolved
Same name with different types remains distinct
Duplicate execution creates no duplicate rows
Multiple source chunks produce multiple evidence rows
Empty document is a valid no-op
Large document follows bounded batching policy
Lease renews before and after consolidation
Provider secrets never enter stored output or errors
```

### Cleanup Tests

```text
Deleting one source preserves shared entity and relation
Deleting final evidence removes unsupported graph artifacts
Alias disappears after final alias evidence is removed
Unresolved data remains scoped to project and dataset
Neo4j rebuild reproduces PostgreSQL graph
```

### Verification Commands

```powershell
uv run ruff check .
uv run mypy
uv run pytest
docker compose -f deployments/docker-compose.yml config --quiet
```

Full gate:

```powershell
bash scripts/check.sh
```

Runtime gate after all cheaper checks pass:

```powershell
bash scripts/m3-runtime-gate.sh
```

`scripts/m3-runtime-gate.sh` is destructive to its test Compose volumes. Do not use it
before unit, type, lint, and compose checks pass.

## Rollout Plan

### Phase 1: Shadow Parsing

```text
Keep PDF_PARSER=pypdf
Run LiteParse against evaluation fixtures
Compare output and performance
Do not change production graph state
```

### Phase 2: Opt-In LiteParse

```text
Enable PDF_PARSER=liteparse in development/staging
Keep consolidation disabled
Measure parse failures, OCR use, latency, and graph quality
```

### Phase 3: Opt-In Consolidation

```text
Bump GRAPH_EXTRACTOR_VERSION
Enable document consolidation in staging
Compare relation recall, orphan rate, duplicates, and citation validity
```

### Phase 4: Production Enablement

```text
Enable LiteParse and consolidation only after quality and resource gates pass
Retain explicit configuration rollback to pypdf and disabled consolidation
Do not silently switch parsers at runtime
```

## Metrics

Evaluate a representative corpus of 20-50 documents.

Track:

```text
PDF parse failure rate
Empty-page rate
OCR page rate
Heading preservation rate
Entity precision and recall
Relation precision and recall
Orphan node rate
Duplicate entity rate
Unsupported relation rate
Citation validity
Tokens per document
Processing time per document
Peak worker memory
```

Initial quality targets:

```text
Citation validity: 100%
Orphan node rate: reduce by at least 30%
Duplicate entity rate: below 10%
Unsupported relation rate: below 5%
PDF parse failure rate: below 2%
```

Performance limits must be established from the compatibility spike rather than guessed.

## Deferred Scope

Do not include these items in the initial implementation:

```text
DOCX/PPTX/XLSX conversion through LibreOffice
Image conversion through ImageMagick
Source-code graph extraction
Embedding-based automatic entity merging
Semantic-similarity edges
Temporal graph
RAG
AI agents
Manual section editor
Document and chunk nodes on the default canvas
Global fuzzy entity resolution
```

## Done Criteria

Implementation is complete when all conditions hold:

```text
LiteParse PDF adapter passes digital and scanned fixtures
OCR runs only according to configured routing
Section and page metadata survive parsing and chunking
Chunk extraction remains parallel
Cross-chunk fixture produces previously missing relation
Every persisted relation has exact source evidence
Retries do not repeat successful provider work
Duplicate execution remains idempotent
Alias resolution remains exact and scoped
PostgreSQL can rebuild equivalent Neo4j projection
Orphan and duplicate metrics improve against baseline
All lint, type, test, build, compose, and runtime gates pass
LiteParse and consolidation remain opt-in until rollout approval
```
