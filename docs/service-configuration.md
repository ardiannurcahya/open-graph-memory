# Service and Provider Configuration

OpenGraphMemory can run as a full local Docker Compose stack or use selected managed services. This guide lists every runtime dependency, supported replacement boundary, and environment variable needed before deployment.

## Support labels

- **Built in:** configured through existing environment variables; no application code change.
- **OpenAI-compatible:** works through the built-in `openai` adapter only when provider implements compatible `/v1/embeddings` or `/v1/chat/completions` request and response shapes.
- **Plugin required:** contract exists, but replacing implementation requires explicit plugin registration and conformance testing. Dynamic package discovery is not enabled.

Provider names are capability names, not vendor names. Current runtime accepts only `deterministic` and `openai` for embedding, chat, and graph extraction. Use `openai` for any verified OpenAI-compatible endpoint.

## Service inventory

| Capability | Default local service | Replaceable with | Support | Authority/lifecycle |
|---|---|---|---|---|
| Relational data | PostgreSQL 16 | Managed PostgreSQL with asyncpg-compatible TLS connection | Built in through `DATABASE_URL` | Authoritative; back up |
| Object storage | RustFS | AWS S3, Tencent Cloud COS, MinIO, or another verified S3-compatible service | Built in through `S3_*` | Authoritative; enable versioning/backup |
| Queue/broker | Redis 7 | Local Redis or managed Redis reachable by Celery | Built in through `REDIS_URL` | Transient; private network recommended |
| Vector projection | Qdrant | Self-hosted or Qdrant Cloud | Built in through `QDRANT_*` | Rebuildable projection |
| Graph projection | Neo4j Community | Self-hosted Neo4j or compatible managed Neo4j endpoint | Built in through `NEO4J_*`; other graph engines need plugin/code | Rebuildable projection |
| Embedding inference | Deterministic test provider | Verified OpenAI-compatible local gateway or cloud API | Built in/OpenAI-compatible | Output dimension must match Qdrant collection |
| Chat inference | Deterministic test provider | Verified OpenAI-compatible local inference server or cloud API | Built in/OpenAI-compatible | Used for grounded answers |
| Graph extraction | Deterministic development extractor | Verified OpenAI-compatible chat endpoint with structured JSON support | Built in/OpenAI-compatible | Production requires `openai` provider |
| API | FastAPI container | Scale behind trusted ingress after load testing | Application service | Stateless except dependencies |
| Background processing | Celery worker, graph worker, dispatcher | Scale worker replicas/concurrency | Application service | Uses Redis and PostgreSQL outboxes |
| Web | React/Vite served by Caddy | Any deployment preserving same-origin `/api` proxy | Application service | Stateless |
| Bootstrap | `migrate`, `bucket-init` | Explicit migration job; provider-side bucket provisioning | One-shot services | Must complete before application start |

Default Compose defines 12 services. Full local mode leaves 10 long-running containers and runs `migrate` plus `bucket-init` once. External S3 mode disables `rustfs` and `bucket-init`, leaving 9 long-running containers and one migration job.

## Environment variables by service

### PostgreSQL

```dotenv
POSTGRES_DB=opengraphrag
POSTGRES_USER=opengraphrag
POSTGRES_PASSWORD=replace-with-strong-password
DATABASE_URL=postgresql+asyncpg://opengraphrag:replace-with-strong-password@postgres:5432/opengraphrag
```

For managed PostgreSQL, replace hostname, port, database, credentials, and TLS query parameters in `DATABASE_URL`. `POSTGRES_*` variables configure only local Compose container. Application and migration use `DATABASE_URL`.

### Redis

```dotenv
REDIS_URL=redis://redis:6379/0
```

For authenticated/TLS Redis, use provider URL, for example `rediss://user:password@host:6380/0`. Keep Redis private. Redis is queue transport, not authoritative data store.

### S3-compatible object storage

```dotenv
S3_ENDPOINT_URL=http://rustfs:9000
S3_ACCESS_KEY=opengraphrag
S3_SECRET_KEY=replace-with-secret
S3_BUCKET=opengraphrag
S3_REGION=us-east-1
S3_FORCE_PATH_STYLE=true
```

Common profiles:

| Provider | Endpoint guidance | Path style |
|---|---|---|
| RustFS local | `http://rustfs:9000` | `true` |
| MinIO local | MinIO API endpoint, not console endpoint | usually `true` |
| AWS S3 | Regional S3 endpoint | `false` |
| Tencent Cloud COS | Bucket region endpoint from Tencent console | `false` |
| Other S3-compatible cloud | Provider API endpoint | follow provider documentation |

Create bucket before starting external-storage deployment. Grant only required bucket/object operations. Test upload, download, delete, and readiness against chosen provider. “S3-compatible” does not guarantee identical behavior for addressing, signatures, regions, multipart upload, or consistency.

Start with external storage:

```sh
docker compose \
  -f deployments/docker-compose.yml \
  -f deployments/docker-compose.external-s3.yml \
  up -d
```

Do not enable `local-storage` profile when using cloud storage.

### Embedding provider

Deterministic mode supports offline development and reproducible tests:

```dotenv
EMBEDDING_PROVIDER=deterministic
EMBEDDING_MODEL=deterministic-embedding-v1
EMBEDDING_DIMENSIONS=64
```

OpenAI-compatible cloud or local gateway:

```dotenv
EMBEDDING_PROVIDER=openai
OPENAI_EMBEDDING_BASE_URL=https://provider.example/v1
OPENAI_API_KEY=replace-with-provider-key
EMBEDDING_MODEL=replace-with-exact-model-id
EMBEDDING_DIMENSIONS=replace-with-exact-output-dimension
```

Verified project example using Alibaba DashScope through APIProxy v1:

```dotenv
EMBEDDING_PROVIDER=openai
OPENAI_EMBEDDING_BASE_URL=http://host.docker.internal:29080/v1
OPENAI_API_KEY=proxy-client-key
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_DIMENSIONS=1024
```

`text-embedding-v3` returned 1024-dimensional vectors in project testing. For Linux Docker, `host.docker.internal` may require `extra_hosts`; production validation also requires HTTPS, so expose proxy through trusted TLS or use provider HTTPS endpoint directly.

Ollama can be used only through an OpenAI-compatible endpoint/version that implements expected `POST /v1/embeddings` response shape. Native Ollama-only endpoints are not handled by current adapter. Verify model, endpoint, batch input, returned `data[index].embedding`, and dimension before indexing.

Changing embedding model or dimensions invalidates existing vector compatibility. Use new Qdrant collection or rebuild all vectors; do not mix dimensions in one collection.

### Chat provider

Deterministic mode:

```dotenv
CHAT_PROVIDER=deterministic
CHAT_MODEL=deterministic-chat-v1
```

OpenAI-compatible local or cloud inference:

```dotenv
CHAT_PROVIDER=openai
OPENAI_CHAT_BASE_URL=https://provider.example/v1
OPENAI_API_KEY=replace-with-provider-key
CHAT_MODEL=replace-with-exact-model-id
```

Compatible candidates include OpenAI-compatible gateways for cloud providers and local servers such as Ollama, vLLM, or llama.cpp **only after endpoint compatibility is tested**. Required endpoint is `POST /v1/chat/completions`; streaming must emit OpenAI-style SSE `data:` events when streaming UI is used.

Embedding and chat may use different endpoints:

```dotenv
OPENAI_EMBEDDING_BASE_URL=https://embedding-provider.example/v1
OPENAI_CHAT_BASE_URL=http://local-inference:11434/v1
```

Current configuration uses one shared `OPENAI_API_KEY` for all OpenAI-compatible capabilities. Providers requiring different credentials need a gateway that normalizes authentication or a configuration/code extension.

### Graph extractor

```dotenv
GRAPH_EXTRACTOR_PROVIDER=openai
OPENAI_GRAPH_EXTRACTOR_BASE_URL=https://provider.example/v1
OPENAI_API_KEY=replace-with-provider-key
GRAPH_EXTRACTOR_MODEL=replace-with-exact-model-id
GRAPH_EXTRACTOR_VERSION=v1
GRAPH_EXTRACTOR_PROMPT_VERSION=v1
GRAPH_EXTRACTOR_TIMEOUT_SECONDS=300
GRAPH_EXTRACTOR_PARALLELISM=1
```

Extractor calls OpenAI-compatible `/chat/completions` and expects valid JSON matching extraction schema. A chat model working for normal answers may still fail extraction conformance. Test structured output, timeout, malformed JSON, and retry behavior. Production settings require `GRAPH_EXTRACTOR_PROVIDER=openai` and HTTPS provider URLs.

### Qdrant

```dotenv
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=opengraphrag_chunks
```

Use HTTPS URL and API key for Qdrant Cloud. Keep collection dimension aligned with `EMBEDDING_DIMENSIONS`. Qdrant is rebuildable from authoritative metadata and source documents.

### Neo4j

```dotenv
NEO4J_URL=http://neo4j:7474
NEO4J_AUTH=neo4j/replace-with-strong-password
```

Current adapter uses Neo4j HTTP transactional API and `username/password` auth format. Managed Neo4j must expose compatible HTTPS HTTP endpoint. Aura or another managed offering must be tested against endpoint and authentication behavior. Replacing Neo4j with a different graph database is not an environment-only change; register a `GraphStore`/`GraphRetriever` implementation and run conformance plus lifecycle tests.

### Application and deployment

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

## Deployment profiles

### Full local

Use local PostgreSQL, Redis, RustFS, Qdrant, Neo4j, deterministic providers or a local OpenAI-compatible inference server.

```sh
docker compose -f deployments/docker-compose.yml up -d
```

### Hybrid cloud

Typical small-host profile:

- application, Redis, Qdrant, and Neo4j run locally;
- Tencent Cloud COS or another S3-compatible cloud stores source documents;
- Alibaba DashScope/APIProxy supplies embedding and optionally chat/extraction;
- PostgreSQL runs locally or as managed PostgreSQL.

```sh
docker compose \
  -f deployments/docker-compose.yml \
  -f deployments/docker-compose.external-s3.yml \
  up -d
```

### Mostly managed

Managed PostgreSQL, Redis, S3-compatible storage, Qdrant, Neo4j, and inference endpoints can reduce host load. Compose currently still defines local dependency services; create a reviewed override that profile-disables each replaced container and removes corresponding `depends_on` entries. External S3 override is included; equivalent overrides for database, Redis, Qdrant, and Neo4j are not bundled yet.

## Preflight checklist

1. Copy `.env.example` to untracked `.env` and replace every placeholder.
2. Decide authoritative-store backup strategy for PostgreSQL and object storage.
3. Create external bucket and validate object CRUD.
4. Verify PostgreSQL migration connectivity using `DATABASE_URL`.
5. Verify Redis URL from API and worker network context.
6. Test one embedding batch and confirm exact dimension.
7. Test chat non-streaming and streaming responses.
8. Test extraction JSON against representative documents.
9. Verify Qdrant collection dimension and API key.
10. Verify Neo4j write, traversal, cleanup, and reconciliation.
11. Render Compose configuration with all selected override files.
12. Run readiness and upload/query/graph smoke tests before exposing traffic.

Never commit `.env`, API keys, database URLs containing secrets, or provider responses containing private document content.
