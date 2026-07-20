# Service and Provider Configuration

OpenGraphMemory runs as local Docker Compose stack or with selected managed dependencies. PostgreSQL and object storage are authoritative; Neo4j is rebuildable; Redis is transient.

## Service Inventory

| Capability | Local service | Replacement | Configuration |
|---|---|---|---|
| Relational authority | PostgreSQL 16 | Managed PostgreSQL | `DATABASE_URL` |
| Source-object authority | RustFS | Verified S3-compatible storage | `S3_*` |
| Queue and broker | Redis 7 | Managed Redis reachable by Celery | `REDIS_URL` |
| Graph projection | Neo4j Community | Compatible Neo4j endpoint | `NEO4J_*` |
| Graph extraction | Deterministic or local NLP extractor | OpenAI-compatible structured-output endpoint | `GRAPH_EXTRACTOR_*`, `OPENAI_*` |
| API | FastAPI | Scale behind trusted ingress | application service |
| Background work | Celery worker, graph worker, dispatcher | Scale replicas and concurrency | application service |
| Web | React/Vite behind Caddy | Deployment preserving same-origin `/api` proxy | application service |
| Bootstrap | `migrate`, `bucket-init` | Explicit migration and bucket provisioning | one-shot services |

## PostgreSQL

```dotenv
POSTGRES_DB=opengraphrag
POSTGRES_USER=opengraphrag
POSTGRES_PASSWORD=replace-with-strong-password
DATABASE_URL=postgresql+asyncpg://opengraphrag:replace-with-strong-password@postgres:5432/opengraphrag
```

`POSTGRES_*` configures local container. Application and migrations use `DATABASE_URL`. Add provider-required TLS parameters for managed PostgreSQL.

## Redis

```dotenv
REDIS_URL=redis://redis:6379/0
```

Use authenticated `rediss://` URL when required. Keep Redis private; it is queue transport, not authority.

## Object Storage

```dotenv
S3_ENDPOINT_URL=http://rustfs:9000
S3_ACCESS_KEY=opengraphrag
S3_SECRET_KEY=replace-with-secret
S3_BUCKET=opengraphrag
S3_REGION=us-east-1
S3_FORCE_PATH_STYLE=true
```

Local RustFS commonly needs path style. Cloud providers commonly need `false`; follow provider documentation. Create external bucket before deployment and grant only required object operations. Validate upload, download, delete, signatures, regions, multipart behavior, and readiness.

Start with external S3-compatible storage:

```sh
docker compose \
  -f deployments/docker-compose.yml \
  -f deployments/docker-compose.external-s3.yml \
  up -d
```

Do not enable `local-storage` profile with external storage.

## Graph Extraction

## PDF Parsing

Default PDF parsing stays on pypdf:

```dotenv
PDF_PARSER=pypdf
```

LiteParse 2.6.0 is an explicit PDF-only opt-in. CSV, JSON, HTML, Markdown, and text keep
their native parsers.

```dotenv
PDF_PARSER=liteparse
LITEPARSE_OCR_MODE=auto
LITEPARSE_DPI=150
LITEPARSE_MAX_PAGES=300
LITEPARSE_OCR_WORKERS=1
LITEPARSE_IMAGE_MODE=off
```

`auto` probes per-page complexity and enables OCR only when at least one page needs it.
`always` requests OCR-capable parsing; `disabled` never probes or enables OCR. LiteParse errors
fail ingestion explicitly; no silent pypdf fallback occurs. Initial implementation stores page
and spatial text-item bounding boxes. LiteParse does not expose semantic PDF sections in Python
2.6.0, so section labels are not fabricated.

Offline deterministic mode:

```dotenv
GRAPH_EXTRACTOR_PROVIDER=deterministic
GRAPH_EXTRACTOR_MODEL=deterministic-graph-v1
GRAPH_EXTRACTOR_VERSION=graph-extractor-v2
GRAPH_EXTRACTOR_PROMPT_VERSION=graph-v2
GRAPH_EXTRACTOR_TIMEOUT_SECONDS=300
GRAPH_EXTRACTOR_PARALLELISM=1
GRAPH_EXTRACTOR_TARGET_BATCH_SIZE=10
GRAPH_EXTRACTOR_MAX_BATCH_CHARS=100000
GRAPH_DOCUMENT_CONTEXT_PREVIOUS_CHUNKS=10
```

OpenAI-compatible extraction:

```dotenv
GRAPH_EXTRACTOR_PROVIDER=openai
OPENAI_GRAPH_EXTRACTOR_BASE_URL=https://provider.example/v1
OPENAI_API_KEY=replace-with-provider-key
GRAPH_EXTRACTOR_MODEL=replace-with-exact-model-id
GRAPH_EXTRACTOR_VERSION=graph-extractor-v2
GRAPH_EXTRACTOR_PROMPT_VERSION=graph-v2
GRAPH_EXTRACTOR_TIMEOUT_SECONDS=300
GRAPH_EXTRACTOR_PARALLELISM=1
GRAPH_EXTRACTOR_TARGET_BATCH_SIZE=10
GRAPH_EXTRACTOR_MAX_BATCH_CHARS=100000
GRAPH_DOCUMENT_CONTEXT_PREVIOUS_CHUNKS=10
```

Extractor calls OpenAI-compatible chat completions and expects JSON matching extraction schema. Test structured output, malformed responses, timeout, retries, and representative documents. Production requires `GRAPH_EXTRACTOR_PROVIDER=openai`, HTTPS endpoint, and non-placeholder key.

OpenAI-compatible extraction sends one request per target batch. Batches hold up to
`GRAPH_EXTRACTOR_TARGET_BATCH_SIZE` targets. `GRAPH_EXTRACTOR_PARALLELISM` limits concurrent
requests independently. Each target receives its fixed preceding
`GRAPH_DOCUMENT_CONTEXT_PREVIOUS_CHUNKS` chunks as reference-only context; target text remains
sole evidence source. Provider output must contain one explicit `chunk_id` result per target.
Malformed or incomplete batch output falls back to deterministic extraction per target. Legacy
extract-only plugins also run per target. `GRAPH_EXTRACTOR_MAX_BATCH_CHARS` bounds deterministic
request payload construction: oldest references trim first, then target count reduces; no target
chunk is dropped. Retries retain fixed document windows and skip successful chunk runs.

Document consolidation is opt-in and initially restricted to OpenAI-compatible extraction:

```dotenv
GRAPH_DOCUMENT_CONSOLIDATION_ENABLED=false
GRAPH_DOCUMENT_CONSOLIDATION_VERSION=graph-consolidation-v1
GRAPH_DOCUMENT_CONSOLIDATION_PROMPT_VERSION=graph-consolidation-prompt-v1
GRAPH_DOCUMENT_CONSOLIDATION_MAX_CHARS=100000
```

Enable only after setting `GRAPH_EXTRACTOR_PROVIDER=openai` and bumping extractor/consolidation
versions for semantic changes. PostgreSQL stores raw chunk extraction and snapshot-scoped
consolidation output. Neo4j remains rebuildable projection. Apply Alembic migration `0018` before
enabling updated workers.

`OPENAI_GRAPH_EXTRACTOR_BASE_URL` falls back to `OPENAI_BASE_URL` when blank.

Local NLP extraction:

```dotenv
GRAPH_EXTRACTOR_PROVIDER=nlp
GRAPH_EXTRACTOR_MODEL=nlp-graph-v1
GRAPH_EXTRACTOR_VERSION=graph-extractor-v2
GRAPH_EXTRACTOR_PROMPT_VERSION=graph-v2
GRAPH_EXTRACTOR_TIMEOUT_SECONDS=300
GRAPH_EXTRACTOR_PARALLELISM=1
```

NLP mode has no external dependency or credential. It recognizes conservative explicit active relations including employment, acquisition, creation, and technology use. It emits no relation for entity co-occurrence or unmatched grammar. Model value is provenance metadata and can be user-selected. Production still requires OpenAI-compatible extraction.

## Neo4j

```dotenv
NEO4J_URL=http://neo4j:7474
NEO4J_AUTH=neo4j/replace-with-strong-password
```

Adapter uses Neo4j HTTP transactional API and `username/password` auth. Test managed offerings for endpoint and authentication compatibility. Different graph engines require explicit `GraphStore` and `GraphRetriever` registration plus conformance and lifecycle tests.

## Application

```dotenv
APP_ENV=development
ADMIN_API_KEY=replace-with-admin-secret
READINESS_TIMEOUT_SECONDS=2
WEB_PORT=3000
CADDY_SITE_ADDRESS=:80
WORKER_CONCURRENCY=1
GRAPH_WORKER_CONCURRENCY=1
GRAPH_WORKER_REPLICAS=1
```

Production also needs immutable `IMAGE_TAG`, `GHCR_NAMESPACE`, TLS, backups, monitoring, and non-placeholder secrets.

## Deployment Profiles

Full local:

```sh
docker compose -f deployments/docker-compose.yml up -d
```

External object storage:

```sh
docker compose \
  -f deployments/docker-compose.yml \
  -f deployments/docker-compose.external-s3.yml \
  up -d
```

Managed PostgreSQL, Redis, object storage, Neo4j, or extraction endpoint can reduce host load. Compose bundles only external S3 override; other substitutions need reviewed overrides that disable replaced containers and update dependencies.

## Preflight

1. Copy `.env.example` to untracked `.env`; replace every placeholder.
2. Define PostgreSQL and object-storage backup strategy.
3. Validate external object CRUD when applicable.
4. Verify migration connectivity through `DATABASE_URL`.
5. Verify Redis from worker network context.
6. Test extraction schema and timeout against representative documents.
7. Verify Neo4j bootstrap, projection, traversal, cleanup, and reconciliation.
8. Render Compose configuration with selected overrides.
9. Run readiness, upload, graph extraction, evidence, and Graph Playground smoke tests.

Never commit `.env`, keys, secret-bearing database URLs, provider responses, or private document content.
