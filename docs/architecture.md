# Architecture

Caddy serves the Vite SPA and forwards same-origin `/api/*` calls to FastAPI. PostgreSQL stores application and temporal graph state, S3-compatible storage stores source documents, and Redis carries transient ARQ work.

Ingestion parses source objects, persists chunks and evidence in PostgreSQL, and extracts canonical entities and supported relations. Durable PostgreSQL outboxes feed one async ARQ worker, whose maintenance loop dispatches and reconciles jobs. API graph reads remain project- and dataset-scoped and return source evidence from PostgreSQL.

Python SDK exposes dataset/document lifecycle plus structured entity, neighbor, graph search, path, subgraph, evidence, run, job, and review operations.
