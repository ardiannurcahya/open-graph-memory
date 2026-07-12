# Graph extraction core

PostgreSQL is authoritative for graph artifacts and graph-delivery state. Extraction runs retain provider, model, prompt, ontology, input hash, and chunk/document/dataset/project provenance. Entities never merge across datasets; normalized name plus type only identifies a candidate and ambiguous matches remain unresolved.

## Durable dispatch

A successful vector indexing transaction creates one versioned `graph_extraction_jobs` row and its `graph_extraction_outbox` row before marking the transaction committed. Indexing never sends a graph task directly. Celery beat dispatches committed, due outbox records and records every publish attempt plus a sanitized publish error. A publish failure leaves the outbox pending, so restart or the next beat pass retries it.

Workers claim jobs under a row lock, assign a lease, and preserve `documents.status = indexed`; graph progress is recorded separately in `documents.graph_stage`. Duplicate Celery deliveries return safely for a running leased or succeeded job. Failed extraction schedules bounded retries through the outbox; terminal failure retains the sanitized error. Reconciliation returns expired leases to queued state and republishes them. The job includes project, dataset, document, extractor, prompt, provider, model, and ontology metadata, and verifies document scope before extraction.

## Deterministic fixtures

`DeterministicExtractor` recognizes `Name [Type]` and `Source -> RELATION -> Target`. It is intentionally narrow and repeatable for tests, not production NLP.

## OpenAI-compatible adapter

`OpenAICompatibleExtractor` accepts a base URL, API key, model, prompt version, and timeout. It requests strict JSON Schema output with temperature zero. Configure secrets in the caller; the core does not read environment variables or persist credentials.
