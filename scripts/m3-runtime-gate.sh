#!/bin/sh
set -eu

GOLDEN=${M3_GOLDEN:-evaluation/m3_golden/v1.0.json}
REPORT=${M3_REPORT:-artifacts/m3-report.json}
COMPOSE='docker compose --env-file .env -f deployments/docker-compose.yml'
export WEB_PORT="${M3_RUNTIME_PORT:-39094}"

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    $COMPOSE logs --no-color api worker >&2 || true
    $COMPOSE exec -T postgres psql -U "${POSTGRES_USER:-opengraphrag}" -d "${POSTGRES_DB:-opengraphrag}" \
      -c "select id, document_id, status, attempt, error_message from graph_extraction_jobs order by created_at;" >&2 || true
    $COMPOSE exec -T postgres psql -U "${POSTGRES_USER:-opengraphrag}" -d "${POSTGRES_DB:-opengraphrag}" \
      -c "select id, document_id, chunk_id, status, error_message from graph_extraction_runs order by created_at;" >&2 || true
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
uv run python evaluation/m3_runtime_gate.py --base-url "http://localhost:$WEB_PORT/api" --compose-file deployments/docker-compose.yml --fixtures "$GOLDEN"
uv run python evaluation/m3_evaluator.py --golden "$GOLDEN" --output "$REPORT"
uv run python - "$GOLDEN" "$REPORT" <<'PY'
import json, sys
golden = json.load(open(sys.argv[1], encoding="utf-8"))
metrics = json.load(open(sys.argv[2], encoding="utf-8"))["metrics"]
limits = golden["thresholds"]
checks = {
    "entity_precision": metrics["entity"]["precision"],
    "entity_recall": metrics["entity"]["recall"],
    "relation_precision": metrics["relation"]["precision"],
    "relation_recall": metrics["relation"]["recall"],
    "provenance_completeness": metrics["provenance_completeness"],
    "idempotency": metrics["idempotency"],
}
failures = [f"{name}={value:.3f} < {limits[name]:.3f}" for name, value in checks.items() if value < limits[name]]
if metrics["resolution_duplicate_rate"] > limits["resolution_duplicate_rate_max"]:
    failures.append("resolution duplicate rate exceeds fixture maximum")
if failures:
    raise SystemExit("M3 evaluation failed: " + "; ".join(failures))
PY
