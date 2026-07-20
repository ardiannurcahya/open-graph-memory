# Multi-host Production Deployment

Role map uses existing WireGuard mesh. Application traffic stays on `10.77.0.0/24`.
No Compose file binds or changes host ports 22, 80, or 443. Web binds port 3000.

| Host | WireGuard IP | Role | Compose file |
|---|---|---|---|
| 3gcalh | 10.77.0.3 | PostgreSQL | postgres.yml |
| 436lh | 10.77.0.5 | Neo4j | neo4j.yml |
| 4gcalh | 10.77.0.7 | Redis + dispatcher | redis.yml, dispatcher.yml |
| 8gcalh | 10.77.0.9 | API + web + migration + edge routing | app.yml, edge.yml |
| 3gcacvm | 10.77.0.2 | default worker | worker.yml |
| 436cvm | 10.77.0.4 | default worker | worker.yml |
| 4gcacvm | 10.77.0.6 | default worker | worker.yml |
| 8gcacvm | 10.77.0.8 | default worker | worker.yml |
| Geocvm | 10.77.0.10 | graph worker | graph-worker.yml |
| Geolh | 10.77.0.11 | graph worker | graph-worker.yml |
| Workcvm | 10.77.0.12 | default worker | worker.yml |
| Worklh | 10.77.0.1 | default worker | worker.yml |

Each host stores role files under `/opt/open-graph-memory/` using repository filenames:
`postgres.yml`, `neo4j.yml`, `redis.yml`, `dispatcher.yml`, `app.yml`, `edge.yml`,
`worker.yml`, or `graph-worker.yml`. Secrets stay in `/opt/open-graph-memory/.env` mode
`0600`. Use one immutable `sha-<commit>` image tag across every application service.

Tencent COS uses endpoint `https://cos.<region>.myqcloud.com`, bucket name including
AppID, and `S3_FORCE_PATH_STYLE=false`. RustFS and bucket-init are not deployed.

Start stateful services first. Record current image digests and Alembic revision, verify
the latest PostgreSQL backup and restore path, then run `migrate` exactly once. Start
API/web with `--no-deps`, followed by edge routing, dispatcher, and workers. Never run
migration concurrently from multiple hosts.

Edge routing binds only host ports 80 and 443 and proxies the public hostname to the
existing web service at `10.77.0.9:3000`. Public firewall rules must expose only 80/443,
not 3000. SSH port 22 is not managed by Compose.
