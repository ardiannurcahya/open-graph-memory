# Architecture

Caddy serves the Vite SPA and forwards same-origin `/api/*` calls to one Uvicorn process. FastAPI coordinates PostgreSQL metadata and Celery jobs; Redis is transport only. RustFS supplies local S3-compatible source storage. Qdrant and Neo4j are rebuildable projections. Milestone 0 intentionally contains no ingestion or retrieval implementation. Decisions are in `docs/adr/`.
