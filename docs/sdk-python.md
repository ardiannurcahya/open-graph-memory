# Python SDK

M6 adds `open_graph_sdk`, an async-first Python client for the OpenGraphMemory API.

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
    dataset = await client.create_dataset("research")
    document = await client.upload_document(
        dataset.id,
        filename="note.txt",
        content=b"OpenGraphMemory extracts entities and evidence-backed relations.",
        content_type="text/plain",
    )
    graph = await client.get_graph(dataset.id)
    matches = await client.search_graph(dataset.id, "OpenGraphMemory", limit=10)
    print(document.status, graph.entity_count, matches)
```

Structured graph methods are `get_entity`, `get_neighbors`, `get_graph`, `search_graph`, `find_graph_path`, `get_subgraph`, and `get_evidence`.

## Environment

`AsyncOGMClient.from_env()` reads:

- `OGM_BASE_URL`
- `OGM_API_KEY`
- `OGM_PROJECT_ID`
- `OGM_ADMIN_KEY`

## Authentication

Project-scoped calls send `X-API-Key` and `X-Project-Id`. Admin project creation sends only `X-API-Key` using `admin_key` when present.

## Error Handling

HTTP errors are mapped to typed SDK exceptions:

- `ValidationError` for 400
- `AuthenticationError` for 401
- `NotFoundError` for 404
- `ConflictError` for 409
- `PayloadTooLargeError` for 413
- `UnsupportedMediaTypeError` for 415
- `BadGatewayError` for 502
- `ServiceUnavailableError` for 503
- `ServerError` for other 5xx responses
- `TransportError` for network/client failures
