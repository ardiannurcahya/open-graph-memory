---
name: ogm-agent-bridge
description: >-
  Guide for AI agents to interact with Open Graph Memory (OGM) and Codebase Knowledge Graph via the ogm-agent-bridge MCP server.
  Use this skill when searching codebase AST symbols, inspecting call graphs, reading structural code chunks, recalling past bugfixes/refactors, or recording new agent memory episodes.
---

# Open Graph Memory (OGM) Agent Bridge Skill

This skill provides step-by-step instructions and best practices for AI agents to interact with the `ogm-agent-bridge` MCP tools for Codebase Knowledge Graph navigation and Agent Memory retrieval.

## Tool Capabilities & Reference

### 1. Codebase Knowledge Graph Navigation
- `ogm_search_code_symbols`: Search functions, classes, methods, structs, and interfaces by name or language across a codebase dataset.
  - Parameters: `dataset_id` (required), `q` (search string), `kind` (function|class|method|struct|interface), `file_path`.
- `ogm_get_code_call_graph`: Trace caller/callee graphs and inheritance (`INHERITS`, `CALLS`, `CONTAINS`) for a target code entity.
  - Parameters: `entity_id` (required), `limit` (max relations).
- `ogm_get_code_chunks`: Retrieve AST structural code chunks with exact `start_line` and `end_line` bounds without splitting functions mid-way.
  - Parameters: `dataset_id` (required), `file_path`, `limit`.
- `ogm_sync_code_file`: Real-time incremental AST extraction when a code file is edited.
  - Parameters: `dataset_id` (required), `file_path` (required), `code` (required), `language`.

### 2. Agent Memory & Experience Management
- `ogm_recall_code_memory`: Search past bugfixes, architectural decisions, and refactoring experiences for a specific file or function before attempting a fix.
  - Parameters: `file_path`, `function_name`, `q`, `limit`.
- `ogm_record_code_fix`: Record an engineering episode detailing `root_cause`, `solution`, `goal`, and problem signature after resolving a bug.
  - Parameters: `file_path` (required), `title` (required), `goal` (required), `root_cause` (required), `solution` (required), `function_name`, `idempotency_key`.
- `ogm_memory_search`: Perform semantic and keyword search over recorded agent memory episodes.
- `ogm_memory_create_episode`: Save a new structured agent memory episode.

---

## Standard AI Agent Workflows

### Workflow 1: Investigating and Fixing Code Bugs
1. **Recall Prior Experience**: Call `ogm_recall_code_memory` with `file_path` or `function_name` to check if a similar issue was previously solved.
2. **Explore Symbol Graph**: Call `ogm_search_code_symbols` and `ogm_get_code_call_graph` to map caller and callee dependencies.
3. **Fetch AST Chunks**: Call `ogm_get_code_chunks` to read clean structural blocks without breaking function boundaries.
4. **Sync Edited Code**: After modifying a file, call `ogm_sync_code_file` to keep the Knowledge Graph updated.
5. **Record Fix Memory**: Once tests pass, call `ogm_record_code_fix` to store the problem, root cause, and solution for future retrieval.

### Workflow 2: Onboarding & Understanding New Codebases
1. **List Datasets**: Call `ogm_list_datasets` to discover indexed codebase datasets.
2. **Find High-Centrality Symbols**: Call `ogm_get_graph` or `ogm_search_code_symbols` to locate core entrypoints and classes.
3. **Inspect Call Hierarchies**: Call `ogm_get_code_call_graph` to visualize how functions interact across files.
