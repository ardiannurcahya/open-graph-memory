# Agent Memory Preview

Agent Memory Preview adds a scoped memory layer on top of the GraphRAG foundation. PostgreSQL is authoritative for users, agents, sessions, messages, and facts; Neo4j/vector projections remain rebuildable and are not required for the preview path.

## Scope and Lifecycle

Memory facts are stored with one of three scopes:

- `user`: durable preference or profile facts for one user.
- `agent`: durable behavior or capability facts for one agent.
- `session`: short-lived facts tied to a user-agent session.

Facts move through `active`, `superseded`, and `deleted` states. Writing a fact with the same scoped `subject` + `predicate` and a different value automatically marks the old active fact as `superseded`, sets `valid_until`, and links the new fact through `supersedes_id`. Deleting a fact marks it `deleted` and preserves provenance for auditability.

## Provenance

Every fact stores:

- `source_message_id` when derived from a session message batch.
- `provenance.source` as `message` or `api`.
- scope keys (`user_id`, `agent_id`, `session_id`) according to the fact scope.
- `valid_from`, `valid_until`, `created_at`, and `updated_at` timestamps.

## API Preview

```http
POST /v1/memory/users
POST /v1/memory/agents
POST /v1/memory/sessions
POST /v1/memory/sessions/{session_id}/messages
GET  /v1/memory/sessions/{session_id}/memory
GET  /v1/memory/users/{user_id}/context
POST /v1/memory/search
DELETE /v1/memory/{memory_id}
```

`POST /v1/query` can include `memory_user_id`, `memory_agent_id`, `memory_session_id`, and `memory_top_k`. Matching active facts are injected as personalization context and recorded in `retrieval_trace.memory`; they are explicitly not treated as citation evidence.

## Evaluation

The preview evaluator checks retrieval quality and lifecycle behavior without requiring external LLMs or Docker services. It verifies active-fact recall, scoped filtering, and supersession correctness.
