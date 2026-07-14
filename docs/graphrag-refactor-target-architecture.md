# GraphRAG Refactor Target Architecture

Status: draft target architecture for retrieval quality, graph reliability, and ingestion scalability.

## Goals

- Make `Hybrid` default mode produce useful answers for PDF, TXT, HTML, CSV, and mixed unstructured datasets.
- Make graph retrieval work even when vector chunk search returns zero candidates.
- Support typo-heavy natural language queries such as `whats is spessification of my project?`.
- Keep grounded citations from source chunks, not generated graph summaries alone.
- Improve CSV/TXT/PDF chunking so graph extraction sees clean semantic units.
- Add Microsoft GraphRAG-inspired local/global retrieval while preserving current API compatibility.
- Keep PostgreSQL and object storage authoritative; keep Qdrant and Neo4j rebuildable projections.

## Non-goals

- Do not replace vector RAG with graph-only retrieval.
- Do not make graph data authoritative over original chunks.
- Do not add dynamic plugin discovery.
- Do not store private provider responses or uploaded content outside existing storage boundaries.
- Do not remove deterministic provider paths; they remain test/default friendly.

## Current Problems

### Graph search depends too much on vector seeds

Current graph retrieval starts from vector chunk hits plus simple query token entity candidates. When vector search returns zero candidates, graph traversal often has no strong seed.

Observed trace shape:

```text
Vector Search: 0 candidates
Graph Traversal: 0 paths, 0 hydrated
Fusion: 0 fused
Answer: I cannot answer from the supplied evidence.
```

This is technically valid but poor UX. Graph retrieval should have its own entity seed path.

### Query typo and vocabulary mismatch break entity matching

Example:

```text
whats is spessification of my project?
```

Naive token matching extracts weak candidates:

```text
whats
spessification
project
```

If graph entities contain `specification`, `web portfolio`, `flask`, or `project requirements`, graph search may miss them.

### Chunking is not structure-aware

Current chunking is character based. It works for simple text but is weak for graph extraction.

Problems:

- PDF sections lose headings and page context.
- TXT/HTML paragraphs can be split mid-topic.
- CSV rows become long text without row-aware grouping.
- Large cells produce giant evidence text.
- Graph extractor receives noisy chunks instead of clean subject-relation units.

### No entity embeddings

Current vector search only targets chunks. Entity search uses names/tokens, not semantic similarity.

Missing search targets:

- canonical entity names
- aliases
- entity descriptions
- relation labels
- community summaries

### No community summaries

Microsoft GraphRAG quality comes partly from community detection and community reports. Current system has entities/relations but no graph communities or higher-level summaries.

Global corpus-level questions are therefore weak:

```text
What are the main themes in this dataset?
Explain the overall project.
Summarize all requirements.
```

### Trace lacks retrieval intent clarity

Current trace shows vector candidates, graph paths, hydration counts, and timings. It should also show:

- normalized query
- query intent
- extracted query entities
- typo corrections
- entity seeds
- entity embedding hits
- fuzzy entity hits
- community reports
- graph expansion fanout/depth
- evidence hydration source

## Target Architecture

Target design:

```text
Files
  -> Parsers
  -> Structure-aware chunkers
  -> Chunk embeddings
  -> Graph extraction
  -> Entity canonicalization
  -> Entity embeddings
  -> Relation projection
  -> Community detection
  -> Community reports

Query
  -> Query normalization
  -> Query entity extraction
  -> Vector chunk search
  -> Entity lexical/fuzzy search
  -> Entity embedding search
  -> Local graph expansion
  -> Community report search
  -> Evidence hydration
  -> Fusion/ranking
  -> Grounded generation with citations
```

## Retrieval Modes

### Vector

Purpose: fast chunk-level semantic search.

Flow:

```text
query -> query embedding -> Qdrant chunk search -> authoritative chunk hydration -> answer
```

Best for:

- exact facts in documents
- source-backed answers
- small and medium datasets

### Local Graph

Purpose: entity-specific reasoning and relation traversal.

Flow:

```text
query
  -> normalize/repair query
  -> extract candidate entities
  -> lexical/fuzzy entity search in PostgreSQL
  -> entity embedding search in Qdrant
  -> merge entity seeds
  -> graph traversal in Neo4j
  -> relation evidence chunk hydration from PostgreSQL
  -> answer with chunk citations
```

Best for:

- `what framework does this project use?`
- `which features belong to the portfolio project?`
- `how is X related to Y?`
- typo-tolerant entity questions

Important: Local Graph must not require vector chunk hits. Vector hits may be extra seeds, not the only seed.

### Global Graph

Purpose: corpus-level summarization using community reports.

Flow:

```text
query
  -> query embedding
  -> retrieve community reports
  -> optional local graph expansion for named entities
  -> map/reduce answer from reports + source chunks
```

Best for:

- `what are the main themes?`
- `summarize this dataset`
- `what topics appear across documents?`

### Hybrid

Purpose: default best mode.

Flow:

```text
query
  -> vector chunk search
  -> local graph search
  -> optional community report search
  -> fusion/ranking
  -> answer with citations
```

Default mode should be `Hybrid` because it combines semantic recall, explicit relations, and source chunks.

## Indexing Pipeline Target

### 1. Parse

Parsers produce structured text blocks, not only flat text.

Target parsed block schema:

```text
ParsedBlock
  id
  document_id
  block_type: title | heading | paragraph | table_row | list_item | code | page
  text
  page_number
  section_path
  row_number
  column_name
  metadata
```

Parser targets:

- PDF: text per page, headings when detectable, page metadata.
- TXT: paragraphs, headings by heuristic.
- HTML: title, headings, paragraphs, tables.
- CSV: header + row blocks, large cell splitting.
- Markdown: headings, paragraphs, lists, code.

### 2. Structure-aware chunking

Chunker should produce chunks optimized for both vector retrieval and graph extraction.

Target chunk metadata:

```text
Chunk
  id
  document_id
  dataset_id
  chunk_index
  text
  token_count
  start_char
  end_char
  page_start
  page_end
  section_path
  row_start
  row_end
  chunk_type
  pipeline_version
```

Recommended sizes:

- PDF/TXT/HTML vector chunk: 600-1,000 tokens, overlap 80-150 tokens.
- Graph extraction chunk: 300-700 tokens, section heading repeated.
- CSV chunk: header + 10-50 rows depending row size.
- Huge CSV cell: split by paragraph/sentence while preserving `row_number` and `column_name`.

Chunk text should include context prefix:

```text
Document: Capstone_WebPortofolio_Flask_PengantarPemrograman.pdf
Section: Project Specification > Features
Page: 4

...
```

For CSV:

```text
Document: documents.csv
Rows: 120-145
Columns: name, description, category

Row 120:
name: ...
description: ...
```

### 3. Chunk embeddings

Current chunk embeddings stay. Improvements:

- Batch embedding calls, default 64 chunks per request.
- Retry transient provider failures with bounded backoff.
- Persist partial progress only after successful full indexing or use resumable batches.
- Store embedding model and dimensions in artifact metadata.
- Validate Qdrant collection dimensions before indexing.

### 4. Graph extraction

Extractor reads graph-optimized chunks.

Target extraction output:

```text
EntityCandidate
  name
  type
  aliases
  description
  confidence
  evidence_offsets

RelationCandidate
  source_name
  target_name
  relation_type
  description
  confidence
  evidence_quote
  evidence_chunk_ids
```

Extraction prompt should require:

- JSON only.
- Relation source/target must refer to extracted entity names.
- Evidence quote must be copied from chunk.
- No inferred relation without source evidence.
- Entity types normalized to controlled vocabulary where possible.

### 5. Entity canonicalization

Current canonical entities should expand with aliases and descriptions.

Target:

```text
CanonicalEntity
  id
  dataset_id
  canonical_name
  normalized_name
  entity_type
  description
  aliases
  confidence
  source_count
  degree
  embedding_point_id
```

Canonicalization strategy:

- exact normalized match
- alias match
- fuzzy string match
- semantic entity embedding match
- type-aware merge threshold

Avoid merging:

- people with organizations
- generic terms like `project`, `system`, `data` unless strongly supported
- numeric/date/value-only entities unless relation degree is high

### 6. Entity embeddings

Create Qdrant collection or namespace for entities.

Entity embedding text:

```text
Name: Web Portfolio Flask
Type: PROJECT
Aliases: Portfolio Website, Flask Portfolio
Description: Capstone project using Flask for web portfolio.
Connected relations: USES Flask; HAS_FEATURE Contact Form; USES SQLite
```

Search target:

```text
query embedding -> entity embeddings -> entity seeds -> graph expansion
```

Collection options:

- Separate collection: `entities_<dimensions>`
- Same Qdrant collection with payload `point_type=entity`

Recommendation: separate collection to keep chunk/entity filters simple.

### 7. Relation projection

Neo4j remains graph projection. PostgreSQL remains authoritative.

Relation node/edge should include:

- relation id
- dataset id
- source entity id
- target entity id
- relation type
- confidence
- evidence chunk ids
- document ids
- extractor version

Neo4j traversal should return:

```text
GraphEvidence
  path
  relation_ids
  entity_ids
  evidence_chunk_ids
  score
```

### 8. Community detection

Add dataset-level graph clustering.

Potential algorithms:

- Louvain / Leiden if graph tooling available.
- Weakly connected components as first deterministic fallback.
- Label propagation as simple baseline.

Community schema:

```text
GraphCommunity
  id
  dataset_id
  level
  title
  summary
  entity_ids
  relation_ids
  source_document_ids
  embedding_point_id
  created_at
  updated_at
```

### 9. Community reports

Community report prompt input:

- top entities by degree
- top relations by confidence/degree
- representative evidence chunks
- source document names

Report output:

```text
title
summary
key_points
important_entities
source_chunk_ids
confidence
```

Reports should be cited via underlying chunks, not only report text.

## Query Pipeline Target

### 1. Query normalization

Normalize query before retrieval:

- lowercase canonical form
- punctuation cleanup
- common typo repair
- domain synonym expansion
- singular/plural normalization

Example:

```text
Input: whats is spessification of my project?
Normalized: what is specification of my project?
Terms: specification, project
Synonyms: requirements, tech stack, features, architecture
```

Use deterministic rules first. Optional provider-based query rewriting later.

### 2. Query intent detection

Detect intent:

```text
fact_lookup
entity_relation
global_summary
comparison
list
troubleshooting
```

Routing:

- `global_summary` -> include community reports.
- `entity_relation` -> prioritize Local Graph.
- `fact_lookup` -> Vector + Local Graph.
- unknown -> Hybrid.

### 3. Query entity extraction

Candidate extraction sources:

- deterministic token phrases
- noun phrase heuristic
- known entity alias match
- optional LLM extractor
- typo-corrected terms

Output:

```text
QueryEntityCandidate
  text
  normalized_text
  type_hint
  source: token | phrase | alias | fuzzy | llm
  confidence
```

### 4. Entity seed retrieval

Merge several seed channels:

```text
lexical exact entity match
alias match
fuzzy trigram match
entity embedding search
vector chunk-derived entities
```

Ranking:

```text
score = lexical_weight + fuzzy_weight + embedding_weight + degree_prior + query_intent_boost
```

Seed trace:

```text
entity_seeds: [
  {entity_id, name, type, score, channels: ["fuzzy", "embedding"]}
]
```

### 5. Local graph expansion

Traversal inputs:

- entity seed ids
- optional chunk seed ids
- max depth
- fanout
- relation type filters
- timeout

Scoring factors:

- seed score
- relation confidence
- path length penalty
- evidence chunk recency/order
- relation type relevance
- entity degree normalization

Output hydrates chunks from `evidence_chunk_ids`.

### 6. Community report retrieval

For Global/Hybrid:

```text
query embedding -> community report embedding search
query terms -> community title/key point lexical search
```

Community report evidence must hydrate backing chunks.

### 7. Fusion and reranking

Candidate sources:

- vector chunks
- graph evidence chunks
- community report chunks
- memory facts where enabled

Fusion options:

- RRF default.
- Weighted fusion for tuned workloads.
- Optional cross-encoder/reranker later.

Trace per fused hit:

```text
chunk_id
score
channels: [vector, graph, community]
source_scores
document_id
section_path
```

### 8. Grounded generation

Prompt rules:

- Answer only from supplied evidence.
- Cite each factual claim with exact markers.
- Do not cite community reports unless backing chunks are included.
- If evidence insufficient, say exact refusal.
- Keep answer concise by default.

Citation repair remains one retry.

## Data Model Additions

### Entity aliases and descriptions

Add or extend:

```text
entity_aliases
  id
  entity_id
  dataset_id
  alias
  normalized_alias
  source

canonical_entities.description
canonical_entities.embedding_point_id
canonical_entities.degree
canonical_entities.source_count
```

### Entity embedding projection

Either table:

```text
entity_embedding_artifacts
  entity_id
  dataset_id
  qdrant_collection
  point_id
  model
  dimensions
  input_hash
```

Or store in existing artifact metadata.

### Communities

Add:

```text
graph_communities
community_entities
community_relations
community_reports
```

### Query trace expansion

Trace target:

```json
{
  "trace_id": "...",
  "mode": "hybrid",
  "normalized_query": "what is specification of my project",
  "intent": "entity_relation",
  "query_entities": [],
  "channel_candidates": {
    "vector": [],
    "entity": [],
    "graph": [],
    "community": []
  },
  "graph": {
    "status": "ok",
    "entity_seeds": [],
    "paths_found": 0,
    "evidence_chunk_ids": 0,
    "hydrated_chunks": 0,
    "missing_chunks": 0,
    "paths": []
  },
  "community": {
    "reports_considered": 0,
    "reports_used": 0
  },
  "fusion": [],
  "timings_ms": {
    "normalize": 0,
    "vector": 0,
    "entity": 0,
    "graph": 0,
    "community": 0,
    "hydrate": 0,
    "generation": 0
  }
}
```

## API Changes

Keep current `/v1/query` compatible.

Extend `mode` options:

```text
vector_only
graph_only
hybrid
graph_local
graph_global
```

Compatibility mapping:

- `graph_only` -> `graph_local` initially.
- `hybrid` -> vector + local graph, later vector + local graph + community.

Add optional controls:

```json
{
  "query_rewrite": true,
  "entity_top_k": 10,
  "community_top_k": 5,
  "include_communities": true,
  "reranker": "none"
}
```

## UI Changes

Rename query mode labels:

```text
Vector
Local Graph
Global Graph
Hybrid
```

Default: `Hybrid`.

Trace UI should show:

- query normalization
- intent
- vector candidates
- entity seeds
- graph paths
- community reports
- hydrated chunks
- timings
- reason for zero evidence

If graph has zero paths, show actionable message:

```text
Graph found no paths. Entity seeds were empty. Try Hybrid or reindex with graph extraction.
```

## Operational Concerns

### Reindexing

Any chunking/entity/community schema change needs reindex.

Recommended reindex path:

```text
new pipeline_version
rebuild chunks + vectors + graph projection
keep old version until new succeeds
swap active pipeline version
garbage collect old projection
```

### Idempotency

- Stable chunk ids include `document_id`, content hash, pipeline version, chunk index.
- Entity ids use canonical dataset/name/type hash.
- Community ids use dataset + algorithm version + entity set hash.

### Failure handling

- Parser failure -> document failed with sanitized error.
- Chunking failure -> document failed with guidance.
- Embedding transient failure -> retry batch.
- Graph extraction failure -> mark graph stage failed but preserve vector index if policy allows.
- Community failure -> graph still usable without global search.

### Performance

- Batch embeddings.
- Parallel graph extraction with configured semaphore.
- Persist DB writes in batches.
- Cap graph fanout/depth.
- Cache query entity seeds by normalized query + dataset.
- Cache community report embeddings.

### Observability

Add structured logs:

```text
ingestion chunks_created document=... count=...
embedding batch_started document=... batch=x/y size=...
embedding batch_completed document=... batch=x/y ms=...
entity seeds query=... count=...
graph traversal dataset=... seeds=... paths=... ms=...
community search dataset=... reports=... ms=...
```

Metrics:

- chunks per document
- embedding batch latency
- graph extraction chunks/sec
- entity count per document
- relation count per document
- graph query paths found
- hydrated chunks count
- zero-evidence query rate

## Testing Plan

### Unit tests

- CSV large cell parsing.
- CSV row-aware chunking.
- TXT/HTML/PDF structure block parsing.
- Query typo normalization.
- Entity lexical/fuzzy search ranking.
- Entity embedding search payload filters.
- Graph evidence hydration from relation evidence chunk ids.
- Community report retrieval and backing chunk hydration.

### Integration tests

- Upload CSV >700 KB with large fields -> indexed.
- Query typo asks project specification -> non-empty evidence.
- Graph mode with vector candidates zero still finds entity seeds.
- Hybrid returns citations from chunks.
- Global graph answers corpus summary using community reports.

### Runtime checks

- Docker compose readiness.
- Qdrant point counts per dataset for chunks and entities.
- Neo4j path count per dataset.
- Dashboard query trace shows entity seeds and hydrated chunks.

## Migration Phases

### Phase 1: Local Graph independence

Deliverables:

- Query normalization and typo repair.
- PostgreSQL entity lexical/fuzzy seed search.
- Graph mode uses entity seeds before vector chunk seeds.
- Trace includes entity seeds.
- Tests for graph path with zero vector hits.

Pass condition:

```text
Graph query can return evidence when vector candidates are zero but matching entities exist.
```

### Phase 2: Entity embeddings

Deliverables:

- Entity embedding projection to Qdrant.
- Entity embedding refresh after graph extraction.
- Entity search channel in query trace.
- Hybrid fuses chunk vector + entity graph evidence.

Pass condition:

```text
Typo/semantic query finds relevant entity seeds without exact lexical match.
```

### Phase 3: Structure-aware chunking

Deliverables:

- Parsed block model.
- Section-aware PDF/TXT/HTML chunks.
- Row-aware CSV chunks.
- New pipeline version and reindex path.

Pass condition:

```text
Large PDF/TXT/CSV files index without chunk cap failures and produce meaningful graph evidence.
```

### Phase 4: Community reports

Deliverables:

- Community detection.
- Community report generation.
- Community report embeddings.
- `graph_global` mode.

Pass condition:

```text
Global corpus summary queries use community reports and cite backing chunks.
```

### Phase 5: UI and evaluation

Deliverables:

- Mode labels: Vector, Local Graph, Global Graph, Hybrid.
- Trace UI for entity/community channels.
- Golden evaluation cases.
- Runtime gate for upload -> index -> query.

Pass condition:

```text
Dashboard explains why evidence was found or missing, and default Hybrid answers project specification query with citations.
```

## Recommended First Implementation Slice

Start with Phase 1 because it directly fixes current zero-path graph behavior.

Minimal slice:

1. Add query normalization with typo map and synonym expansion.
2. Add entity seed search from PostgreSQL canonical entities and aliases.
3. Update graph retrieval to accept entity ids/names from seed search.
4. Keep vector chunk seeds as optional additional seeds.
5. Hydrate graph evidence chunks from relation `evidence_chunk_ids`.
6. Extend trace and UI.
7. Add tests for vector-zero graph-positive query.

Expected impact:

```text
Query: whats is spessification of my project?
Normalized: what is specification of my project?
Entity seeds: Web Portfolio Flask, Project Specification, Flask
Graph paths: >0
Hydrated chunks: >0
Answer: grounded with citations
```
