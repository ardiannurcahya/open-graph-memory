# M4 Hybrid Retrieval

## Configuration

`POST /api/v1/query` accepts `vector_only`, `graph_only`, and `hybrid`. `hybrid` uses Reciprocal Rank Fusion (RRF) by default; it never adds raw vector similarity to graph confidence. Set `RETRIEVAL_FUSION=weighted` only when calibrated channel weights are deliberately configured.

The bounded graph defaults are `RETRIEVAL_GRAPH_MAX_DEPTH=2`, `RETRIEVAL_GRAPH_SEED_LIMIT=8`, `RETRIEVAL_GRAPH_FANOUT=10`, and `RETRIEVAL_GRAPH_TIMEOUT_MS=500`. Request overrides remain capped at depth two, fanout 100, and timeout 10 seconds. The runtime gate exercises depth two and fanout three, with a six-path gate budget.

## Fusion And Fallback

Vector candidates are authorization-filtered against PostgreSQL. Query entity tokens and vector chunks seed a tenant-scoped Neo4j traversal. Graph evidence is hydrated from authoritative chunks, deduplicated, then fused with vectors by RRF. The trace retains per-channel candidates, fusion decisions, graph evidence paths, and final chunk IDs.

A Neo4j timeout or outage is recorded as `graph.status=fallback` with a reason. Hybrid and graph-only requests then use the already scoped vector candidates rather than failing or exposing unscoped graph data. This is availability fallback, not a substitute for graph-quality evaluation.

## Trace Schema

Each successful query persists `query_logs.retrieval_trace` and returns it as `retrieval_trace`. It contains `trace_id`, `mode`, `channel_candidates.vector`, `channel_candidates.graph`, `fusion`, `graph.status`, `graph.reason` when applicable, `graph.latency_ms`, `graph.paths`, final `chunk_ids`, `scores`, and end-to-end `latency_ms`. Every graph path records its chunk, entity path, and relation IDs. The persisted trace is the source used by the M4 evaluator; avoid putting secrets or raw credentials in it.

## Evaluation And Runtime Gate

`evaluation/m4_golden/v1.0.json` is immutable once baselined. Its 20 questions cover graph multi-hop, vector-only, graph-only, hybrid, aliases, ambiguity, unsupported facts, unanswerable requests, tenant isolation, cycles, and fanout. It uses the real M3 extraction fixture, not fabricated predictions.

Run `scripts/m4-runtime-gate.sh`. It starts a fresh Compose slice, uploads and indexes fixtures, waits for graph extraction, calls every retrieval mode through the public API, verifies persisted traces, tenant isolation, traversal budget, and Neo4j-outage vector fallback. It writes ignored `artifacts/m4-results.jsonl` and `artifacts/m4-report.json`.

The gate applies the existing frozen evaluation thresholds to every mode: Recall@5 >= .80, evidence-hit >= .85, citation correctness >= .95, answerability >= .90, and p95 <= 3000 ms. Hybrid must not regress Recall@5 relative to vector-only. It does not alter thresholds, invent expected answers, or score unavailable data as a pass.

## Limitations And Troubleshooting

The deterministic fixture is a release gate, not a measure of open-domain LLM quality. Entity linking is token based, and the current graph adapter performs bounded supported-relation expansion. Alias and ambiguous cases deliberately test conservative refusal behavior. Production evaluation should retain a separately versioned, human-labeled holdout and pinned provider/model configuration.

If indexing stalls, inspect `docker compose -f deployments/docker-compose.yml logs worker dispatcher`. If graph completion stalls, inspect `graph-worker` and Neo4j logs plus `graph_extraction_jobs`. A fallback trace means Neo4j was slow or unavailable; restore Neo4j and investigate before treating vector fallback as normal operation. Query `query_logs` by `trace_id` to compare the persisted and returned trace. Do not use `down -v` outside the gate unless deleting local data is intentional.
