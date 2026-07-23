#!/bin/sh
set -eu

target=${1:-/opt/open-graph-memory/.env}
image_tag=${2:?usage: remote-generate-multihost-env.sh [target] sha-<commit> [worker-node]}
worker_node=${3:-$(hostname | tr '[:upper:]' '[:lower:]')}

printf '%s\n' "$image_tag" | grep -Eq '^sha-[0-9a-f]{7,40}$' || {
    echo "IMAGE_TAG must use sha-<commit>" >&2
    exit 1
}
[ ! -e "$target" ] || {
    echo "refusing to overwrite existing environment: $target" >&2
    exit 1
}

: "${S3_ENDPOINT_URL:?set S3_ENDPOINT_URL}"
: "${S3_ACCESS_KEY:?set S3_ACCESS_KEY}"
: "${S3_SECRET_KEY:?set S3_SECRET_KEY}"
: "${S3_BUCKET:?set S3_BUCKET}"
: "${S3_REGION:?set S3_REGION}"
: "${GRAPH_EXTRACTOR_MODEL:?set GRAPH_EXTRACTOR_MODEL}"
: "${OPENAI_GRAPH_EXTRACTOR_BASE_URL:?set OPENAI_GRAPH_EXTRACTOR_BASE_URL}"
: "${OPENAI_API_KEY:?set OPENAI_API_KEY}"
umask 077

postgres_password=$(openssl rand -hex 24)
redis_password=$(openssl rand -hex 24)
neo4j_password=$(openssl rand -hex 24)
admin_api_key=$(openssl rand -hex 24)

cat >"$target" <<EOF
APP_ENV=production
GHCR_NAMESPACE=ardiannurcahya
IMAGE_TAG=$image_tag

POSTGRES_DB=opengraphrag
POSTGRES_USER=opengraphrag
POSTGRES_PASSWORD=$postgres_password
POSTGRES_BIND_IP=10.77.0.3
DATABASE_URL=postgresql+asyncpg://opengraphrag:$postgres_password@10.77.0.3:5432/opengraphrag

REDIS_PASSWORD=$redis_password
REDIS_BIND_IP=10.77.0.7
REDIS_URL=redis://:$redis_password@10.77.0.7:6379/0

NEO4J_BIND_IP=10.77.0.5
NEO4J_AUTH=neo4j/$neo4j_password
NEO4J_URL=http://10.77.0.5:7474

ADMIN_API_KEY=$admin_api_key

S3_ENDPOINT_URL=$S3_ENDPOINT_URL
S3_ACCESS_KEY=$S3_ACCESS_KEY
S3_SECRET_KEY=$S3_SECRET_KEY
S3_BUCKET=$S3_BUCKET
S3_REGION=$S3_REGION
S3_FORCE_PATH_STYLE=false

GRAPH_EXTRACTOR_PROVIDER=openai
GRAPH_EXTRACTOR_MODEL=$GRAPH_EXTRACTOR_MODEL
GRAPH_EXTRACTOR_VERSION=graph-extractor-v1
GRAPH_EXTRACTOR_PROMPT_VERSION=graph-v1
PROVIDER_VERSION=v1
OPENAI_GRAPH_EXTRACTOR_BASE_URL=$OPENAI_GRAPH_EXTRACTOR_BASE_URL
OPENAI_API_KEY=$OPENAI_API_KEY

PDF_PARSER=pypdf
LITEPARSE_OCR_MODE=auto
LITEPARSE_DPI=150
LITEPARSE_MAX_PAGES=300
LITEPARSE_OCR_WORKERS=1
LITEPARSE_IMAGE_MODE=off
GRAPH_EXTRACTOR_TIMEOUT_SECONDS=300
GRAPH_EXTRACTOR_PARALLELISM=4
GRAPH_DOCUMENT_CONTEXT_EXCERPT_CHARS=500
GRAPH_DOCUMENT_CONSOLIDATION_ENABLED=false
GRAPH_DOCUMENT_CONSOLIDATION_VERSION=graph-consolidation-v1
GRAPH_DOCUMENT_CONSOLIDATION_PROMPT_VERSION=graph-consolidation-prompt-v1
GRAPH_DOCUMENT_CONSOLIDATION_MAX_CHARS=100000
GRAPH_DOCUMENT_CONSOLIDATION_BATCH_CHARS=30000
READINESS_TIMEOUT_SECONDS=5
WEB_BIND_IP=10.77.0.9
WEB_PORT=3000
WORKER_NODE=$worker_node
WORKER_CONCURRENCY=1
GRAPH_WORKER_CONCURRENCY=1
EOF

chmod 600 "$target"
