#!/bin/sh
set -eu

GOLDEN=${M4_GOLDEN:-evaluation/m4_golden/v1.0.json}
PREDICTIONS=${M4_PREDICTIONS:-artifacts/m4-results.jsonl}
REPORT=${M4_REPORT:-artifacts/m4-report.json}
COMPOSE='docker compose --env-file .env -f deployments/docker-compose.yml'
export WEB_PORT="${M4_RUNTIME_PORT:-39095}"

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    $COMPOSE logs --no-color api worker graph-worker dispatcher neo4j >&2 || true
  fi
  $COMPOSE down -v --remove-orphans
  exit "$status"
}
trap cleanup EXIT INT TERM
[ -f .env ] || cp .env.example .env
if [ -z "${ADMIN_API_KEY:-}" ]; then
  ADMIN_API_KEY=$(awk -F= '$1 == "ADMIN_API_KEY" {sub(/^[^=]*=/, ""); print; exit}' .env)
  export ADMIN_API_KEY
fi
[ -n "$ADMIN_API_KEY" ] || { echo "ADMIN_API_KEY is required" >&2; exit 1; }
$COMPOSE down -v --remove-orphans
$COMPOSE up -d --build
uv run python evaluation/m4_runtime_gate.py --base-url "http://localhost:$WEB_PORT/api" --compose-file deployments/docker-compose.yml --golden "$GOLDEN" --predictions "$PREDICTIONS"
uv run python evaluation/m4_evaluator.py --golden "$GOLDEN" --predictions "$PREDICTIONS" --output "$REPORT" -k 5
uv run python - "$REPORT" <<'PY'
import json, sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
limits = {"recall_at_k": .80, "evidence_hit_rate": .85, "citation_correctness": .95, "answerability_accuracy": .90}
failures = []
for mode, metrics in report["modes"].items():
    for name, minimum in limits.items():
        if metrics[name] < minimum:
            failures.append(f"{mode} {name}={metrics[name]:.3f} < {minimum:.3f}")
    if metrics["latency_ms"]["p95"] > 3000:
        failures.append(f"{mode} p95={metrics['latency_ms']['p95']:.1f}ms > 3000ms")
    if metrics["graph_traversal"]["max_paths"] > 6:
        failures.append(f"{mode} graph paths exceed budget")
if report["hybrid_delta_vs_vector"]["recall_at_k"] < 0:
    failures.append("hybrid recall regresses vector_only")
if failures:
    raise SystemExit("M4 evaluation failed: " + "; ".join(failures))
PY
