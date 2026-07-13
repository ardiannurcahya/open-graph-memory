# Dashboard and Trace Explorer

Dashboard runs at `http://localhost:3000` by default. Credentials remain project-scoped: enter `X-Project-Id` and project API key; UI never bypasses API authorization or tenant isolation.

## Workflow

1. Create/select dataset and inspect document lifecycle.
2. Upload supported document through streaming API.
3. Wait for indexing and graph projection state.
4. Open Query Playground; choose `vector_only`, `graph_only`, or `hybrid`.
5. Inspect answer citations and source evidence.
6. Inspect graph paths, relation evidence, fusion candidates, fallback state, and latency in Trace Explorer.

Dashboard is responsive demo/operations UI, not replacement for authorization, monitoring, or backup tools. Query traces may contain user queries and evidence excerpts; restrict access and apply retention/privacy policy.

Validate M5 with:

```sh
cd apps/web
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```
