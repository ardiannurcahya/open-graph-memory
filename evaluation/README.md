# Evaluation

## Milestone 3 graph extraction

`m3_golden/v1.0.json` is a versioned, human-labeled graph fixture. It covers entities, an explicit alias, supported relations, ambiguous same-name entities, unsupported relation grammar, shared multi-document provenance, and a separate tenant. The golden labels deliberately exclude the ambiguous and unsupported relations: a deterministic extractor must not invent either.

Run `uv run python evaluation/m3_evaluator.py --output artifacts/m3-report.json` to score the deterministic fixture, or pass `--predictions` with an object containing `entities`, `relations`, entity `documents`, `resolution_duplicate_rate`, and `idempotency`. It reports entity and relation precision/recall/F1, provenance completeness, resolution duplicate rate, and idempotency. `scripts/m3-runtime-gate.sh` executes both evaluation and a fresh Compose API/worker/Neo4j gate, enforcing frozen fixture thresholds.

## Milestone 2 Evaluation

The versioned golden set (`golden/v1.0.json`) has 24 representative questions: 20 answerable questions spanning product, deployment, storage, isolation, ingestion and retrieval, plus four unanswerable questions. Stable fixture evidence IDs intentionally decouple evaluation from database-generated IDs.

The evaluator never calls a model or store. It scores retained JSONL artifacts from the retired retrieval API, keeping published baselines reproducible without presenting those metrics as a current runtime check.

```json
{"id":"q01","answer":"...","retrieved":["quickstart-health"],"citations":["quickstart-health"],"unanswerable":false,"latency_ms":42.1,"usage":{"prompt_tokens":120,"completion_tokens":18,"estimated_cost_usd":0.0002}}
```

Run it from the repository root:

```sh
python evaluation/evaluator.py --golden evaluation/golden/v1.0.json --predictions artifacts/m2-results.jsonl --output artifacts/m2-report.json -k 5
pytest -q evaluation/test_evaluator.py
```

`scripts/m2-runtime-gate.sh` and its `/v1/query` runner were removed. `evaluation/runtime_gate.py` now contains shared HTTP and Compose helpers only.

## Milestone 4 structured graph runtime

`m4_golden/v1.0.json` remains an immutable published baseline for the retired hybrid retrieval API. Its evaluator and executable gate were removed when `/v1/query` was removed; structured graph endpoints cannot honestly reproduce answer, citation, retrieval-mode, or fallback metrics.

The current M4 runtime gate uploads `m4_golden/fixture-v1.1.json` and checks canonical and alias entity search, an exact two-hop path, bounded depth-two subgraph expansion, relation evidence, direct evidence lookup, validation bounds, and project/dataset isolation through public graph routes.

Run the complete vertical slice with:

```sh
scripts/m4-runtime-gate.sh
```

The gate invokes `GET /api/v1/datasets/{dataset_id}/entities/search`, `/graph/path`, `/graph/subgraph`, `/relations/{relation_id}/evidence`, and `GET /api/v1/evidence/{evidence_id}`. PostgreSQL-authoritative graph reads must continue to work independently of projection-specific assumptions.

## Metric contract

- `Recall@k`: fraction of expected evidence IDs present in the first `k` retrieved IDs, macro-averaged. Empty expected evidence scores 1 by definition.
- Evidence hit: answerable case has at least one expected ID in the first `k`; negative cases pass by definition.
- Citation correctness: every citation resolves to retrieved evidence and answerable responses cite at least once; unanswerable responses cite nothing.
- Unanswerable accuracy: negative cases refuse (`unanswerable` or a documented refusal phrase), while positive cases do not.
- Latency: nearest-rank p50/p95 over reported end-to-end milliseconds.
- Usage/cost: sums provider-reported prompt/completion tokens and USD estimates. Missing values are zero, never inferred.

Case order, nearest-rank percentiles, exact evidence-ID matching, and no model judge make scoring deterministic. Reports include case details for diagnosis. Add or correct questions only in a new golden version; do not mutate a version after publishing a baseline.
