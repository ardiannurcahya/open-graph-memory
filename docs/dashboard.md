# Dashboard and Graph Playground

Dashboard runs at `http://localhost:3000`. Enter project ID and project API key; UI uses same project-scoped API authorization as direct clients.

## Workflow

1. Create or select dataset.
2. Upload supported document and monitor ingestion/graph state.
3. Open Graph Playground and select dataset.
4. Inspect force-directed nodes, relations, labels, and community colors.
5. Switch detail, thematic, or overview community level.
6. Search entities or run neighbors, path, subgraph, and relation-evidence tools.
7. Inspect node details or raw JSON and refresh analytics after graph changes.

Playground bounds requests through Structured Graph API. It is demo and operations UI, not replacement for authorization, monitoring, backups, or independent source-data review.

Validate web app:

```sh
cd apps/web
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```
