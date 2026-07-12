# Vector RAG Design and Runtime Gate

## Scope

Vector RAG is a rebuildable retrieval projection over authoritative PostgreSQL document/chunk metadata and S3-compatible source objects. Qdrant stores vectors and routing payload only. This plan fits the current FastAPI, Celery, PostgreSQL, object-storage, provider-adapter and Qdrant boundaries; it does not require evaluation code to import app models, providers or query modules.

## Indexing path

1. Upload commits a document and source object using existing dataset/project authorization and indexing states.
2. Celery parses and deterministically chunks content. A stable evidence ID should be derived from document ID, content revision and chunk index; retries upsert the same point.
3. The embedding adapter batches chunks, records model name/dimension and returns vectors plus usage. Empty or invalid vectors fail the job rather than entering the index.
4. Qdrant points contain vector plus `project_id`, `dataset_id`, `document_id`, stable `evidence_id`, chunk index, content revision and embedding-model version. Payload should not become the source of truth for document text.
5. Mark the document indexed only after all point upserts succeed. Retry with bounded backoff; stale revisions are removed asynchronously. Reindex into a versioned collection/alias, validate counts, then atomically swap the alias.

## Query path

1. Authenticate project and validate dataset ownership before retrieval. Reject cross-project dataset IDs before contacting providers.
2. Normalize the question, embed once, and search Qdrant with mandatory project and dataset filters. Use deterministic score-descending/evidence-ID-ascending tie breaking where the client supports it.
3. Resolve returned evidence IDs against PostgreSQL, dropping missing, stale or unauthorized rows. Fetch exact chunk text from the authoritative record.
4. Build a bounded prompt containing numbered evidence blocks and require evidence-ID citations. If no evidence clears the configured score threshold, return the standard unanswerable response without generation where practical.
5. Validate generated citations against supplied evidence. Remove or reject unknown citations; never convert model text into a trusted identifier. Return answer, citations, retrieval metadata, latency and provider usage.

Default starting values are chunk size 500 tokens, overlap 75, retrieval `k=5`, candidate pool 20 and a provider/model-specific similarity threshold. These are configuration, not universal truths; tune them against a frozen golden version. Avoid graph expansion until vector-only quality is baselined.

## Failure and security behavior

- Time out embedding, vector search and generation separately; expose a bounded end-to-end timeout.
- Do not silently query without tenant filters. Treat Qdrant outage as unavailable, not an invitation to scan another store.
- Redact credentials and source text from logs. Log IDs, model/version, duration, counts and usage.
- Make deletion remove authoritative metadata first and enqueue projection cleanup; retrieval's authoritative join prevents stale points from leaking.
- Cap question length, retrieved context, completion tokens, provider retries and batch concurrency. Apply existing API rate limits at the authenticated project boundary.

## Observability

Emit structured spans for query embedding, vector search, metadata hydration and generation. Record request count/error rate, stage and end-to-end latency histograms, candidates/hits, refusal rate, prompt/completion tokens and estimated USD. Tag by provider/model and deployment, not raw question or high-cardinality document IDs.

## Evaluation adapter

A thin, separate harness reads `evaluation/golden/v1.0.json`, invokes the public query service or HTTP endpoint serially, and writes `artifacts/m2-results.jsonl` in the contract documented in `evaluation/README.md`. It maps response evidence identifiers to `retrieved`, validated answer citations to `citations`, measures monotonic end-to-end latency, and copies provider-reported usage/cost. Temperature must be zero, model/config pinned, corpus revision recorded, concurrency one, and case order preserved. The deterministic evaluator scores this artifact offline.

## Runtime gate rollout

`scripts/m2-runtime-gate.sh` is intentionally independent from `scripts/runtime-gate.sh`: the existing gate proves stack health, while M2 requires an indexed fixture corpus and may spend provider budget. CI or release automation should:

1. Start the stack and run migrations/bucket initialization with the existing runtime gate setup.
2. Seed a versioned fixture corpus whose stable evidence IDs match the golden set; wait for terminal indexing states and verify point counts/tenant payloads.
3. Run the pinned query harness to create JSONL. Keep secrets in CI secret storage and retain no answer text longer than the artifact policy permits.
4. Invoke `M2_PREDICTIONS=... scripts/m2-runtime-gate.sh`. Defaults gate Recall@5 >= .80, evidence hit >= .85, citation correctness >= .95, unanswerable accuracy >= .90, p95 <= 3000 ms and total cost <= $1. Override thresholds only through reviewed environment configuration.
5. Retain report, predictions, corpus revision, application SHA, golden version, provider/model and pricing snapshot. Compare trends, but block only against the frozen absolute thresholds.

Run mock-provider fixtures on every PR for contract and isolation checks. Run the real-provider gate nightly and before release to limit cost and external flakiness. Add a zero cross-tenant-hit assertion and an index retry/idempotency check to the fixture harness before making the gate release-blocking. Roll out first in report-only mode, freeze a baseline after repeated stable runs, then enable blocking. Roll back by disabling the M2 gate job; never weaken production tenant filtering or citation validation to satisfy evaluation.
