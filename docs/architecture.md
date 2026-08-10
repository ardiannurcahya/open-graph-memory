# System Architecture

Caddy serves the Vite SPA and forwards same-origin `/api/*` calls to FastAPI. PostgreSQL stores application, temporal graph state, codebase AST entities, and agent memory. S3-compatible storage stores source documents, while Redis carries transient ARQ worker queues.

```text
Browser -> Caddy -> FastAPI -> PostgreSQL (Authoritative Temporal Graph & Agent Memory)
                         |-> S3-compatible object storage
                         `-> Redis -> ARQ worker

Document Ingestion -> Streaming upload -> tree-sitter / LiteParse -> Chunking & Evidence
                   -> Extract canonical entities & relation assertions
                   -> Hierarchical community analytics refresh

Codebase Ingestion -> Multi-language AST parsing (Python, TS/JS, Go, Rust, C/C++)
                   -> Canonical symbol IDs, Call Graph, & AST structural chunks
                   -> Real-time single-file incremental sync (`/v1/codebase/sync-file`)

Agent Memory       -> Episodes, attempts, outcomes, and patterns
                   -> Temporal supersession and feedback scoring
                   -> Cross-linked experience retrieval
```

## Tri-Memory Synergy Architecture

OpenGraphMemory unifies three critical memory dimensions under a single project boundary:

1. **Document Knowledge (Specs & ADRs):**
   - Ingest PDF, MD, Doc, CSV files containing system architecture, API specifications, and business requirements.
   - Extracts evidence-backed entities and relation assertions.

2. **Codebase Knowledge Graph (AST & Call Graph):**
   - Multi-language AST parsing for Python, TypeScript, JavaScript, Go, Rust, C, and C++.
   - Canonical symbol naming schemes (`py:module.path:SymbolName`, `ts:file.path:SymbolName`).
   - Call graph discovery (`calls`, `called_by`, `inherits`, `implements`).
   - Real-time incremental single-file sync for live AI agent coding.

3. **Operational Agent Memory (Experience & Lessons):**
   - Persistent operational memory recording episode attempts, outcomes, and verified patterns.
   - Enables AI agents to verify implementation against architecture specs, check call graph side-effects, and recall past bugfixes seamlessly.
