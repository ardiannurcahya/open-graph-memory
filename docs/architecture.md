# Architecture

Caddy serves Vite SPA and forwards same-origin `/api/*` calls to FastAPI. PostgreSQL and S3-compatible object storage are authoritative. Neo4j is a rebuildable graph traversal projection; Redis carries Celery work only.

Ingestion parses source objects, persists chunks and evidence in PostgreSQL, extracts canonical entities and supported relations, then projects graph data to Neo4j. Graph jobs use durable PostgreSQL outboxes and graph workers. API graph reads remain project- and dataset-scoped and return source evidence from PostgreSQL.

Python SDK exposes dataset/document lifecycle plus structured entity, neighbor, graph search, path, subgraph, evidence, run, job, and review operations.
