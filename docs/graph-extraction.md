# Graph Extraction

Milestone 3 stores extraction artifacts in PostgreSQL first, then projects the scoped topology to Neo4j. PostgreSQL is authoritative; Neo4j can be reconciled or rebuilt.

## Model and provenance

The initial topology is `Dataset -> Document -> Chunk`, `Chunk -> Entity`, and relation assertions between entities. Every extraction run, entity/relation evidence row, and job records project, dataset, document, chunk, extractor/provider/model/prompt/ontology versions, confidence, and timestamps. Relation responses expose evidence citations.

Normalized name and type are only exact candidate keys inside one dataset. The system does not merge entities across datasets or guess ambiguous references. Aliases and merge history remain explicit data structures. A relation whose source or target is ambiguous is intentionally omitted rather than fabricated.

## Extractors

`DeterministicExtractor` is the default test/runtime extractor. It recognizes only explicit fixture grammar:

```text
Acme Labs [Organization]
Acme Labs -> EMPLOYS -> Alice Nguyen
```

Unsupported grammar is ignored deliberately. `NlpExtractor` is a local dependency-free option for conservative explicit active sentences such as `Alice Nguyen works at Acme Labs` and `Acme Labs acquired Widget Cloud`. It emits typed entities and relations only for matched sentence patterns; it never creates co-occurrence edges. `OpenAICompatibleExtractor` remains available as a configurable adapter with caller-supplied base URL, key, model, prompt version, timeout, target batch size, and request character limit; it requests strict JSON Schema at temperature zero. One request returns explicit per-target `chunk_id` results. Previous document chunks are reference-only and cannot own output or evidence. PostgreSQL persistence and exact target-chunk evidence validation remain per chunk. Malformed batch output falls back deterministically for every target. Credentials are never persisted by graph artifacts.

## Operations and API

Successful ingestion atomically creates graph job and outbox record. Dispatcher publishes committed outbox records; workers lease, retry, reconcile expired leases, and safely ignore duplicate delivery of active or succeeded job. `documents.status` and `documents.graph_stage` report ingestion and graph progress.

Use `GET /v1/datasets/{dataset_id}/graph?limit=100&depth=1` for bounded inspection, `GET /v1/entities/{id}/neighbors` for bounded neighbors, and `GET /v1/evidence/{id}` or `GET /v1/graph-runs/{id}` for provenance. Relations transition once from `unreviewed`/`needs_review` to `approved` or `rejected` through `PATCH /v1/relations/{id}/review`.

Run the real stack gate with `scripts/m3-runtime-gate.sh`. It starts a fresh Compose stack, uploads the versioned fixture through the API, verifies PostgreSQL and Neo4j artifacts, dispatch idempotency, bounded APIs, review transitions, and project isolation.
