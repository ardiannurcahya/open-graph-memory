#!/bin/sh
set -eu

GOLDEN=${M2_GOLDEN:-evaluation/golden/v1.0.json}
PREDICTIONS=${M2_PREDICTIONS:-artifacts/m2-results.jsonl}
REPORT=${M2_REPORT:-artifacts/m2-report.json}
K=${M2_K:-5}
COMPOSE='docker compose --env-file .env -f deployments/docker-compose.yml'
export WEB_PORT="${M2_RUNTIME_PORT:-39093}"

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    $COMPOSE logs --no-color api worker dispatcher >&2 || true
  fi
  $COMPOSE down -v --remove-orphans
  exit "$status"
}
trap cleanup EXIT INT TERM
[ -f .env ] || cp .env.example .env
# The host-side gate must authenticate with the same key supplied to Compose.
if [ -z "${ADMIN_API_KEY:-}" ]; then
  ADMIN_API_KEY=$(awk -F= '$1 == "ADMIN_API_KEY" {sub(/^[^=]*=/, ""); print; exit}' .env)
  export ADMIN_API_KEY
fi
[ -n "$ADMIN_API_KEY" ] || { echo "ADMIN_API_KEY is required" >&2; exit 1; }
$COMPOSE down -v --remove-orphans
$COMPOSE up -d --build

uv run python evaluation/runtime_gate.py \
  --base-url "http://localhost:$WEB_PORT/api" \
  --golden "$GOLDEN" --predictions "$PREDICTIONS" \
  --compose-file deployments/docker-compose.yml

uv run python evaluation/evaluator.py --golden "$GOLDEN" --predictions "$PREDICTIONS" --output "$REPORT" -k "$K"
uv run python - "$REPORT" <<'PY'
import json, os, sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
metrics = report["metrics"]
limits = {
    "recall_at_k": float(os.getenv("M2_MIN_RECALL", ".80")),
    "evidence_hit_rate": float(os.getenv("M2_MIN_EVIDENCE_HIT", ".85")),
    "citation_correctness": float(os.getenv("M2_MIN_CITATION_CORRECTNESS", ".95")),
    "unanswerable_accuracy": float(os.getenv("M2_MIN_UNANSWERABLE", ".90")),
}
failures = [f"{name}={metrics[name]:.3f} < {minimum:.3f}" for name, minimum in limits.items()
            if metrics[name] < minimum]
if metrics["missing_predictions"] or metrics["extra_predictions"]:
    failures.append(
        f"prediction coverage missing={metrics['missing_predictions']} extra={metrics['extra_predictions']}"
    )
p95_limit = float(os.getenv("M2_MAX_P95_MS", "3000"))
if metrics["latency_ms"]["p95"] > p95_limit:
    failures.append(f"latency p95={metrics['latency_ms']['p95']:.1f}ms > {p95_limit:.1f}ms")
cost_limit = float(os.getenv("M2_MAX_COST_USD", "1.00"))
if metrics["estimated_cost_usd"] > cost_limit:
    failures.append(f"cost=${metrics['estimated_cost_usd']:.6f} > ${cost_limit:.6f}")
print(json.dumps(metrics, indent=2, sort_keys=True))
if failures:
    print("M2 gate failed: " + "; ".join(failures), file=sys.stderr)
    raise SystemExit(1)
PY
