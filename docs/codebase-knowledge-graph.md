# Codebase Knowledge Graph

OpenGraphMemory integrates continuous codebase AST symbol parsing, call graph traversal, and real-time file synchronization into a unified Knowledge Graph backed by PostgreSQL.

---

## 1. Overview

Traditional AI coding assistants rely on brute-force "context dumping"—loading entire folders or files into the LLM context window to answer questions about code structure. This burns tens of thousands of tokens per query and degrades reasoning performance.

The Codebase Knowledge Graph solves this by parsing source code into structured **AST entities** and **explicit relation assertions** using native **Tree-Sitter** bindings:
- **Functions, Classes, Structs, Interfaces, Enums, and Modules** are stored as canonical entities.
- **Calls, Callers, Inheritance, Implementation, and Containment** are stored as authoritative relation edges.
- **Structural AST Chunks** preserve exact line and byte boundaries for surgical retrieval.

---

## 2. Supported Languages

Tree-Sitter parsers are natively compiled for:
- **Python** (`.py`, `.pyi`)
- **TypeScript** (`.ts`, `.tsx`)
- **JavaScript** (`.js`, `.jsx`, `.mjs`, `.cjs`)
- **Go** (`.go`)
- **Rust** (`.rs`)
- **C** (`.c`, `.h`)
- **C++** (`.cpp`, `.hpp`, `.cc`, `.cxx`)

Unsupported languages fall back to conservative regex-based symbol and function detection without failing ingestion.

---

## 3. Canonical Symbol Identifiers

Symbols are assigned deterministic, canonical identifiers:
```text
code_{language}_{symbol_name}_{hash}
```
* Example (Python class): `code_python_UserService_a8f3b2c1d4e5`
* Example (TypeScript function): `code_typescript_fetchUserData_7e2b1a9f0c3d`

This naming convention ensures consistent identity across multi-file refactors and incremental file edits.

---

## 4. Call Graph & Relations

The extractor discovers and asserts directed relationships between code entities:
* `contains`: A file contains a class; a class contains a method.
* `calls`: A function invokes another function or method.
* `inherits`: A class subclasses another class.
* `implements`: A class or struct implements an interface.
* `imports`: A module imports a symbol from another file.

---

## 5. Real-Time Incremental Sync (<15ms)

When an AI agent modifies code, re-parsing the entire codebase would be too slow. OpenGraphMemory provides an incremental single-file sync endpoint:

```text
POST /v1/codebase/sync-file
```

* Computes AST delta for the modified file in **under 15 milliseconds**.
* Upserts modified entities and removes stale relation assertions using PostgreSQL atomic transactions.
* AI agents always query the latest code graph state without downtime or batch re-indexing.

---

## 6. Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/codebase/ingest` | Batch ingest files into Knowledge Graph with Louvain community analytics |
| `POST` | `/v1/codebase/sync-file` | Real-time single file AST sync for live agent editing |
| `POST` | `/v1/codebase/index-directory` | Index an entire local filesystem directory into a dataset |

### Example: Batch Ingest
```bash
curl -X POST http://localhost:3000/api/v1/codebase/ingest \
  -H "X-Project-Id: <project-id>" \
  -H "X-Api-Key: <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "core-service",
    "files": [
      {
        "file_path": "services/auth.py",
        "code": "class AuthService:\n    def login(self, user):\n        pass"
      }
    ]
  }'
```

---

## 7. MCP Tools for Codebase

OpenGraphMemory exposes codebase tools via the Model Context Protocol:
* `ogm_search_code_symbols`: Search functions, classes, interfaces, and structs across the codebase.
* `ogm_get_code_call_graph`: Inspect callers, calls, and inheritance hierarchies for a given symbol.
* `ogm_get_code_chunks`: Retrieve precise AST structural chunks with exact line numbers.
* `ogm_sync_code_file`: Sync a single edited file into the Knowledge Graph in real-time.
