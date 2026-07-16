# Hierarchical Community Analytics

Hierarchical analytics provides deterministic community snapshots and semantic zoom.

## Authority and hierarchy

PostgreSQL is authority for entities, non-rejected relations, analytics snapshots, and memberships. Neo4j is rebuildable graph projection.

Analytics uses deterministic Louvain partitioning. Level 0 runs on entity graph. Levels 1 and 2 run Louvain over quotient graphs from prior partition, so parent groups cannot split child groups. Levels mean:

- `0`: detailed communities.
- `1`: thematic communities.
- `2`: overview communities.

Refresh analytics after graph changes:

```text
POST /v1/datasets/{dataset_id}/analytics/refresh
```

Synchronous refresh limit: 5,000 entities and 20,000 relations per dataset.

Migration `0014` adds three-level hierarchy, membership levels, parent links, metrics, algorithm version, and config. Migration `0015` removes obsolete community-report tables while preserving analytics tables. Migration `0016` removes obsolete embedding states. Create and verify an external PostgreSQL backup before running Alembic through `0016`.

Explorer endpoints:

```text
POST /v1/datasets/{dataset_id}/analytics/refresh
GET  /v1/datasets/{dataset_id}/graph/explorer?node_limit=100&relation_limit=200&community_level=0|1|2
```

Explorer bounds: `node_limit` and `relation_limit` are 1–200. It remains PostgreSQL-backed when analytics is unavailable.

## Dashboard semantic zoom

Graph Explorer exposes detail, thematic, and overview levels. Automatic semantic zoom chooses level from viewport density. Manual level choice locks zoom until unlocked. Explorer refresh loads selected membership level; analytics refresh rebuilds hierarchy.

## Operational checks

1. Back up PostgreSQL, then run migration job through revision `0016`.
2. Check API readiness: `curl -fsS http://localhost:3000/api/ready`.
3. Refresh analytics for test dataset. Confirm level 0–2 in explorer response.
4. Verify community counts, memberships, and parent links match selected level.
5. Back up PostgreSQL and object storage. Rebuildable projections do not replace authoritative backups.
