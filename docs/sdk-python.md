# Python SDK (`open_graph_sdk`)

`open_graph_sdk` is an async-first Python client for the OpenGraphMemory API, providing native support for dataset management, graph exploration, evidence citation, and failure-driven agent memory.

## Installation

```bash
pip install ./packages/sdk
# or with uv
uv add ./packages/sdk
```

## Quick Start

```python
from open_graph_sdk import AsyncOGMClient, ClientConfig

async with AsyncOGMClient(
    ClientConfig(
        base_url="http://localhost:8000",
        api_key="ogm_project_key",
        project_id="project-uuid",
    )
) as client:
    # 1. Dataset & Document Ingestion
    dataset = await client.create_dataset("research")
    document = await client.upload_document(
        dataset.id,
        filename="note.txt",
        content=b"OpenGraphMemory extracts entities and evidence-backed relations.",
        content_type="text/plain",
    )

    # 2. Graph Exploration
    graph = await client.get_graph(dataset.id)
    matches = await client.search_graph(dataset.id, "OpenGraphMemory", limit=10)
    print(document.status, graph.entity_count, matches)
```

## Agent Memory API

The SDK provides first-class methods for recording and querying agent execution episodes, attempts, outcomes, and Bayesian confidence feedback:

```python
# 1. Create an episodic memory
episode = await client.create_agent_memory_episode(
    domain="backend-engineering",
    title="Database Deadlock on Batch Insertion",
    goal="Resolve concurrent lock escalation in PostgreSQL",
    problem_signature="err_pg_deadlock_detected",
    scope={"repo": "payments-service", "env": "staging"},
    tags=["database", "postgresql", "deadlock"],
)

# 2. Append an attempt (hypothesis & action)
attempt = await client.append_agent_memory_attempt(
    episode_id=episode.id,
    hypothesis="Acquire row-level advisory locks before batch processing",
    actions=[{"tool": "run_migration", "args": {"file": "0042_advisory_locks.sql"}}],
    result="Deadlocks eliminated under 100 concurrent workers",
)

# 3. Record final outcome with verified lesson
outcome = await client.record_agent_memory_outcome(
    episode_id=episode.id,
    status="success",
    summary="Resolved deadlocks using advisory locks ordered by entity ID",
    lesson="Sort batch payloads by primary key before bulk UPSERT to avoid lock crossing",
    pattern_key="pg_batch_lock_ordering",
    verifiers=[{"type": "stress_test", "passed": True}],
)

# 4. Search agent memory before executing new tasks
results = await client.search_agent_memory(
    query="Postgres deadlock during bulk insert",
    problem_signature="err_pg_deadlock_detected",
    repository="payments-service",
)

# 5. Closed-loop feedback (adjusts Bayesian confidence)
await client.feedback_agent_memory_episode(episode.id, score=1)

# 6. Supersession (invalidate obsolete lessons)
await client.supersede_agent_memory_episode(
    episode_id="old-episode-id",
    superseding_episode_id=episode.id,
)
```

## Available Client Methods

### Knowledge Graph
- `get_entity(entity_id: str)`: Fetch entity details.
- `get_neighbors(entity_id: str, limit: int = 25)`: Retrieve 1-hop connected neighbors.
- `get_graph(dataset_id: str, limit: int = 100, depth: int = 1)`: Summarize dataset knowledge graph.
- `search_graph(dataset_id: str, query: str, entity_type: str | None = None, limit: int = 25)`: Semantic and exact entity search.
- `find_graph_path(dataset_id: str, source_entity_id: str, target_entity_id: str, max_depth: int = 3, relation_limit: int = 100)`: Discover relationship paths between entities.
- `get_subgraph(dataset_id: str, entity_id: str, depth: int = 1, node_limit: int = 100, relation_limit: int = 200)`: Extract subgraph neighborhood.
- `get_evidence(evidence_id: str)`: Inspect verbatim source text, bounding boxes, and document provenance.
- `get_relation_evidence(dataset_id: str, relation_id: str, limit: int = 25)`: Retrieve evidence passages for a specific relation.
- `review_relation(relation_id: str, review_state: str)`: Update human/agent review status (`approved`, `rejected`).

### Agent Memory
- `create_agent_memory_episode(...)`: Register a new problem-solving episode.
- `list_agent_memory_episodes(status: str | None = None, limit: int = 25)`: List recent episodes.
- `get_agent_memory_episode(episode_id: str)`: Retrieve full episode details.
- `append_agent_memory_attempt(episode_id: str, hypothesis: str, actions: list, result: str, ...)`: Append an action attempt.
- `record_agent_memory_outcome(episode_id: str, status: str, summary: str, lesson: str | None, ...)`: Record episode outcome and lesson learned.
- `search_agent_memory(query: str, problem_signature: str | None, repository: str | None, ...)`: Query past memories with similarity filtering.
- `feedback_agent_memory_episode(episode_id: str, score: int)`: Submit feedback (+1 / -1) to calibrate Bayesian confidence score.
- `supersede_agent_memory_episode(episode_id: str, superseding_episode_id: str)`: Mark an old memory superseded by a newer resolution.

### Datasets & Documents
- `create_dataset(name: str, description: str | None = None, metadata: dict | None = None)`: Create a new dataset.
- `list_datasets()`: List all datasets in the project.
- `get_dataset(dataset_id: str)`: Get dataset metadata and statistics.
- `update_dataset(dataset_id: str, ...)`: Update dataset details.
- `delete_dataset(dataset_id: str)`: Delete dataset and associated graph data.
- `upload_document(dataset_id: str, filename: str, content: bytes, content_type: str)`: Upload and schedule document for parsing and graph extraction.
- `list_documents(dataset_id: str)`: List documents in a dataset.
- `get_document(dataset_id: str, document_id: str)`: Get document metadata and status.
- `get_document_by_id(document_id: str)`: Get document by UUID across datasets.
- `delete_document(document_id: str)`: Delete document and its extracted entities/relations.

## Configuration & Environment

`AsyncOGMClient.from_env()` automatically reads:

- `OGM_BASE_URL`: API root URL (e.g. `http://localhost:8000`)
- `OGM_API_KEY`: Project API key
- `OGM_PROJECT_ID`: Project UUID
- `OGM_ADMIN_KEY`: Admin key (required only for `create_project`)

## Authentication

Project-scoped calls send `X-API-Key` and `X-Project-Id`. Admin project creation sends `X-API-Key` using `admin_key`.

## Error Handling

HTTP errors are mapped to typed SDK exceptions in `open_graph_sdk.errors`:

- `ValidationError` (400)
- `AuthenticationError` (401)
- `NotFoundError` (404)
- `ConflictError` (409)
- `PayloadTooLargeError` (413)
- `UnsupportedMediaTypeError` (415)
- `BadGatewayError` (502)
- `ServiceUnavailableError` (503)
- `ServerError` (Other 5xx)
- `TransportError` (Network/client failures)
