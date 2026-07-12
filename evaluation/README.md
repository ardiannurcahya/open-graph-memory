# Evaluation

## Milestone 3 graph extraction

`m3_golden/v1.0.json` is a versioned, human-labeled graph fixture. It covers entities, an explicit alias, supported relations, ambiguous same-name entities, unsupported relation grammar, shared multi-document provenance, and a separate tenant. The golden labels deliberately exclude the ambiguous and unsupported relations: a deterministic extractor must not invent either.

Run `uv run python evaluation/m3_evaluator.py --output artifacts/m3-report.json` to score the deterministic fixture, or pass `--predictions` with an object containing `entities`, `relations`, entity `documents`, `resolution_duplicate_rate`, and `idempotency`. It reports entity and relation precision/recall/F1, provenance completeness, resolution duplicate rate, and idempotency. `scripts/m3-runtime-gate.sh` executes both evaluation and a fresh Compose API/worker/Neo4j gate, enforcing frozen fixture thresholds.

## Milestone 2 Evaluation

The versioned golden set (`golden/v1.0.json`) has 24 representative questions: 20 answerable questions spanning product, deployment, storage, isolation, ingestion and retrieval, plus four unanswerable questions. Stable fixture evidence IDs intentionally decouple evaluation from database-generated IDs.

The evaluator never calls a model or store. A runner invokes the current query path and writes one JSON object per line, making scoring repeatable and allowing the exact result artifact to be retained.

```json
{"id":"q01","answer":"...","retrieved":["quickstart-health"],"citations":["quickstart-health"],"unanswerable":false,"latency_ms":42.1,"usage":{"prompt_tokens":120,"completion_tokens":18,"estimated_cost_usd":0.0002}}
```

Run it from the repository root:

```sh
python evaluation/evaluator.py --golden evaluation/golden/v1.0.json --predictions artifacts/m2-results.jsonl --output artifacts/m2-report.json -k 5
pytest -q evaluation/test_evaluator.py
```

## Milestone 4 hybrid retrieval

`m4_golden/v1.0.json` is a versioned 20-case question suite over the real M3 uploaded/indexed/extracted fixture. It covers multi-hop graph answers, vector-only and graph-only answers, hybrid evidence, aliases, ambiguous entities, unsupported and unanswerable questions, cross-tenant isolation, cycle behavior, and fanout bounds.

Run the complete vertical slice with:

```sh
scripts/m4-runtime-gate.sh
pytest -q evaluation/test_m4_evaluator.py
```

The gate invokes `POST /api/v1/query` for `vector_only`, `graph_only`, and `hybrid`, maps returned chunk IDs to stable fixture evidence IDs, confirms persisted `query_logs` traces, and scores Recall@5, evidence hits, citation correctness, answerability, fallback correctness, p50/p95 latency, and graph path budget. It also stops Neo4j and requires graph modes to return scoped vector fallback evidence. Generated JSONL and reports remain under ignored `artifacts/`. See [hybrid retrieval](../docs/hybrid-retrieval.md) for configuration and operations.

## Metric contract

- `Recall@k`: fraction of expected evidence IDs present in the first `k` retrieved IDs, macro-averaged. Empty expected evidence scores 1 by definition.
- Evidence hit: answerable case has at least one expected ID in the first `k`; negative cases pass by definition.
- Citation correctness: every citation resolves to retrieved evidence and answerable responses cite at least once; unanswerable responses cite nothing.
- Unanswerable accuracy: negative cases refuse (`unanswerable` or a documented refusal phrase), while positive cases do not.
- Latency: nearest-rank p50/p95 over reported end-to-end milliseconds.
- Usage/cost: sums provider-reported prompt/completion tokens and USD estimates. Missing values are zero, never inferred.

Case order, nearest-rank percentiles, exact evidence-ID matching, and no model judge make scoring deterministic. Reports include case details for diagnosis. Add or correct questions only in a new golden version; do not mutate a version after publishing a baseline.
