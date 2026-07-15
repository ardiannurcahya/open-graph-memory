# Community GraphRAG

Community GraphRAG completes Phase 3–5: hierarchical analytics, grounded community reports, global retrieval, and semantic zoom.

## Authority and hierarchy

PostgreSQL is authority for entities, non-rejected relations, analytics snapshots, memberships, reports, jobs, outbox rows, and report evidence. Neo4j is rebuildable graph projection. Qdrant stores chunk vectors only; no vector report index exists.

Analytics uses deterministic Louvain partitioning. Level 0 runs on entity graph. Levels 1 and 2 run Louvain over quotient graphs from prior partition, so parent groups cannot split child groups. Levels mean:

- `0`: detailed communities.
- `1`: thematic communities.
- `2`: overview communities.

Refresh analytics after graph changes:

```text
POST /v1/datasets/{dataset_id}/analytics/refresh
```

Synchronous refresh limit: 5,000 entities and 20,000 relations per dataset.

Migrations `0013` add durable community-report lifecycle tables: jobs, outbox, reports, and report evidence. Migration `0014` adds three-level hierarchy, membership/report levels, parent links, metrics, algorithm version, and config. Run Alembic through `0014` before worker/API rollout.

## Reports and durability

Analytics refresh queues report work through PostgreSQL outbox. `community-worker` consumes `community` queue. Jobs carry attempts, next-attempt time, lease expiry, max attempts, status, provider/model/version, prompt version, and input hash. Dispatcher/outbox delivery plus leased retries make report work durable across worker restarts.

Reports ground title, summary, and key points in selected community members, relations, and backing chunks. Report prose is retrieval metadata, not citable evidence. Answers cite hydrated source chunks only. If backing chunks are absent, report claims must not appear as citations or answer evidence.

Report endpoints:

```text
GET /v1/datasets/{dataset_id}/community-reports?community_level=0|1|2
GET /v1/datasets/{dataset_id}/community-reports/{report_id}
GET /v1/datasets/{dataset_id}/community-report-jobs
GET /v1/datasets/{dataset_id}/community-report-jobs/{job_id}
```

Explorer endpoints:

```text
POST /v1/datasets/{dataset_id}/analytics/refresh
GET  /v1/datasets/{dataset_id}/graph/explorer?node_limit=100&relation_limit=200&community_level=0|1|2
```

Explorer bounds: `node_limit` and `relation_limit` are 1–200. It remains PostgreSQL-backed when analytics is unavailable.

## Query modes

Query endpoints:

```text
POST /v1/query
POST /v1/query/stream
```

Query request accepts:

```text
vector_only
graph_only
graph_local
graph_global
hybrid
```

`graph_only` is alias for `graph_local`. `graph_local` uses graph retrieval. `graph_global` selects community reports and defaults to level 2. `hybrid` combines retrieval; global-summary intent enables communities unless caller overrides it. `vector_only` does not use graph retrieval.

Optional fields:

```json
{
  "include_communities": true,
  "community_level": 0
}
```

`community_level` ranges 0–2. `include_communities` overrides automatic community selection.

Current report selection is deterministic lexical term overlap against report title, summary, and key points. It is not vector similarity search and does not use a vector report index. Selected reports hydrate backing chunks before generation.

## Limits and configuration

```dotenv
COMMUNITY_REPORT_PROVIDER=
COMMUNITY_REPORT_MODEL=
COMMUNITY_REPORT_VERSION=community-report-v1
COMMUNITY_REPORT_PROMPT_VERSION=community-report-v1
COMMUNITY_REPORT_MAX_MEMBERS=100
COMMUNITY_REPORT_MAX_RELATIONS=200
COMMUNITY_REPORT_MAX_CHUNKS=20
COMMUNITY_REPORT_TIMEOUT_SECONDS=300
COMMUNITY_REPORT_LEASE_SECONDS=300
COMMUNITY_REPORT_MAX_ATTEMPTS=5
COMMUNITY_WORKER_CONCURRENCY=1
```

Blank report provider/model use normal runtime defaults. Keep report input bounds aligned with provider context and latency budgets. Increase worker concurrency only after database, provider, and queue capacity checks.

## Dashboard semantic zoom

Graph Explorer exposes detail, thematic, and overview levels. Automatic semantic zoom chooses level from viewport density. Manual level choice locks zoom until unlocked. Explorer refresh loads selected membership level; analytics refresh rebuilds hierarchy then queues reports.

## Operational checks

1. Run migration job through revision `0014`.
2. Check API readiness: `curl -fsS http://localhost:3000/api/ready`.
3. Refresh analytics for test dataset. Confirm level 0–2 in explorer response.
4. Check report jobs reach `succeeded`; inspect `failed`, attempts, lease, and error fields when not.
5. Verify `community-worker` and dispatcher logs/health plus Redis queue reachability.
6. Query `graph_global` with `include_communities: true`; verify answer citations point only to source chunks.
7. Back up PostgreSQL and object storage. Rebuildable projections do not replace authoritative backups.
