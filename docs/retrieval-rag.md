# Hybrid RAG Retrieval Engine

OpenGraphMemory provides a unified retrieval engine that fuses dense vector search with knowledge graph traversal using **Reciprocal Rank Fusion (RRF)**. This enables AI chatbots and agents to perform multi-hop reasoning with line-level evidence citations.

---

## 1. Why Hybrid RAG?

| Retrieval Approach | Strengths | Weaknesses |
|---|---|---|
| **Vector-only RAG** | Captures semantic similarity and paraphrased concepts. | Fails on multi-hop entity relationships and global summaries; prone to hallucination when context is fragmented. |
| **Graph-only RAG** | Navigates explicit relationships, hierarchies, and entity paths. | Fails on unstructured, descriptive queries lacking exact entity mentions. |
| **Hybrid RAG (OpenGraphMemory)** | **Combines both:** Fuses vector rank with graph traversal score via RRF. | Solves multi-hop questions while retaining semantic discovery. |

---

## 2. Retrieval Endpoint

```text
POST /v1/retrieval/query
```

All requests require authentication headers:
```text
X-Project-Id: <project-uuid>
X-Api-Key: <project-api-key>
```

### Request Parameters

```json
{
  "query": "How does the authentication service validate session tokens?",
  "dataset_id": "core-backend",
  "mode": "hybrid",
  "top_k": 10,
  "vector_weight": 0.5,
  "graph_weight": 0.5,
  "compare": false
}
```

* `mode`:
  * `"vector"`: Dense vector similarity search via `pgvector` (Cosine distance).
  * `"graph"`: Entity and relation traversal through PostgreSQL knowledge graph tables.
  * `"hybrid"`: Fuses vector and graph scores using Reciprocal Rank Fusion (default).
* `vector_weight`: Float between `0.0` and `1.0` (weight for vector rank in RRF).
* `graph_weight`: Float between `0.0` and `1.0` (weight for graph rank in RRF).
* `top_k`: Maximum number of chunks to return (1 to 50, default `10`).
* `compare`: When `true`, executes `vector`, `graph`, and `hybrid` in parallel and returns side-by-side comparison metrics.

---

### Response Structure

```json
{
  "query": "How does the authentication service validate session tokens?",
  "dataset_id": "core-backend",
  "mode": "hybrid",
  "latency_ms": 18.4,
  "result": {
    "mode": "hybrid",
    "total_chunks": 3,
    "latency_ms": 18.4,
    "entities_found": ["AuthService", "SessionToken", "validate_token"],
    "relations_found": ["calls", "validates"],
    "chunks": [
      {
        "chunk_id": "chunk_doc_1_hash_v1_0",
        "document_id": "doc_auth_spec",
        "content": "The AuthService validates incoming session tokens against the Redis cache...",
        "score": 0.0327,
        "source": "hybrid",
        "vector_score": 0.842,
        "graph_score": 0.915,
        "entities": ["AuthService", "SessionToken"],
        "relations": ["validates"],
        "source_location": {
          "page_number": 3,
          "start_line": 45,
          "end_line": 62
        }
      }
    ]
  }
}
```

---

## 3. Evidence-Backed Citations

Every retrieved chunk includes:
* `source_location`: Page number, start line, and end line from the original document.
* `entities`: Key entities mentioned in the chunk.
* `relations`: Extracted relation assertions connecting this chunk to the broader graph.

Chatbots can use `source_location` to provide footnote citations directly to the user (e.g. *"According to Authentication Specs, page 3, lines 45–62"*).

---

## 4. Calibrating RAG with Agent Memory

To build a **Self-Correcting RAG Chatbot**, integrate `/v1/retrieval/query` with `/v1/agent-memory`:

1. **User asks question**:
   - Check `GET /v1/agent-memory/search?q={query}` for prior verified corrections or solutions.
   - If an approved pattern exists, return the calibrated answer immediately (1-shot recall).
2. **Standard RAG execution**:
   - Call `POST /v1/retrieval/query` in `hybrid` mode.
   - Inject retrieved chunks and evidence citations into the LLM prompt.
3. **Feedback loop**:
   - If the user/admin clicks 👍 (Helpful), call `POST /v1/agent-memory/episodes/{id}/feedback` with `score: 1`.
   - If the answer is incorrect or corrected by an admin, record an episode with `score: -1` and supersede outdated information.
