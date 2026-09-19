# Agent Memory

OpenGraphMemory provides a project-scoped, persistent operational memory system for AI agents. Rather than hoarding raw conversational history, it implements a **Failure-Driven Memory** paradigm that records verified problem-solving experiences, tested hypotheses, feedback scores, and promoted solution patterns.

---

## 1. Why Failure-Driven Memory?

Conventional conversational agent memory suffers from two critical failure modes in production:
1. **Memory Landfill**: Storing every chat turn ("Hello", "Thank you", trivial chit-chat) pollutes the vector space with noise, increases token costs, and degrades retrieval precision.
2. **Compounded Hallucinations**: If an agent produces an incorrect answer, storing that bad trace without verification can cause the agent to retrieve its own hallucination as a verified "fact" in subsequent sessions.

OpenGraphMemory solves this by selectively capturing structured operational units:
- **Problem Signatures**: Canonical identifiers or fingerprints of specific errors, bug incidents, or user tasks.
- **Hypotheses & Attempts**: Step-by-step actions and trial outcomes (success, partial, or failed).
- **Verified Outcomes**: Final verified solutions backed by automated verifiers (CI, unit tests, build checks) or human feedback.
- **Patterns**: Abstracted, reusable solution keys that aggregate multiple verified outcomes.

---

## 2. Core Concepts & Data Model

```text
Project
  └── Episode (Problem Signature, Goal, Scope)
        ├── Attempt (Hypothesis, Actions, Result, Notes)
        ├── Outcome (Status, Summary, Lesson, Verifiers)
        │     └── Pattern Member ──> Pattern (Confidence, Promoted)
        └── Evidence (Raw observations, tool inputs/outputs, logs)
```

### Entities

| Entity | Purpose |
|---|---|
| **Episode** | An individual problem-solving session with domain, title, goal, problem signature, and scope. |
| **Attempt** | A hypothesis-driven action taken within an episode, with `success`, `partial`, or `failed` results. |
| **Outcome** | Final verified resolution with status, summary, lesson learned, metrics, and associated verifiers. |
| **Verifier** | Proof of verification (e.g. `test`, `ci`, `build`, `runtime`) with command, status, and artifact URI. |
| **Pattern** | Aggregated experience key derived from problem signatures, with Bayesian confidence scoring. |

---

## 3. Bayesian Confidence & Pattern Promotion

Patterns aggregate outcomes across episodes to build long-term confidence. The confidence score is calculated using Bayesian updating:

$$\text{Confidence} = \frac{\text{weighted\_successes} + \alpha}{\text{weighted\_total} + \alpha + \beta}$$

* Default prior: $\alpha = 1.0, \beta = 1.0$ (starts at neutral $0.5$ confidence).
* Verifiers scale quality weight: outcomes verified by automated test suites or CI carry higher weight than unverified assertions.
* **Pattern Promotion**: When a pattern accumulates sufficient verified outcomes and passes the confidence threshold ($> 0.8$), it is marked as `promoted = True` and prioritized during retrieval.

---

## 4. Closed-Loop Feedback & Temporal Supersession

### Feedback Scoring
Client applications and human reviewers can submit feedback scores (`+1` for upvote/helpful, `-1` for downvote/unhelpful):
* `POST /v1/agent-memory/episodes/{episode_id}/feedback`: Updates the episode's `feedback_score`.
* `POST /v1/agent-memory/patterns/{pattern_key}/feedback`: Updates the pattern's Bayesian confidence score directly.

### Temporal Supersession
When a better fix or updated standard operating procedure (SOP) is discovered, older episodes can be superseded:
* `POST /v1/agent-memory/episodes/{episode_id}/supersede`: Links the older episode to `superseding_episode_id`.
* The system enforces **cycle prevention** and **row-level locking** (`with_for_update`) to prevent race conditions.
* Superseded episodes are excluded from default search results while preserving complete historical audit trails.

---

## 5. API Endpoints

All requests require authentication headers:
```text
X-Project-Id: <project-uuid>
X-Api-Key: <project-api-key>
```

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/agent-memory/episodes` | Create a new problem-solving episode |
| `GET` | `/v1/agent-memory/episodes` | List project episodes (filterable by status, domain) |
| `GET` | `/v1/agent-memory/episodes/{episode_id}` | Get episode details with attempts and outcomes |
| `POST` | `/v1/agent-memory/episodes/{episode_id}/attempts` | Append an attempt to an active episode |
| `POST` | `/v1/agent-memory/episodes/{episode_id}/outcomes` | Record a verified outcome and update patterns |
| `GET` | `/v1/agent-memory/search?q={query}` | Search episodes via hybrid semantic and full-text search |
| `POST` | `/v1/agent-memory/episodes/{episode_id}/feedback` | Score an episode (+1 / -1) |
| `POST` | `/v1/agent-memory/episodes/{episode_id}/supersede` | Supersede an outdated episode |
| `POST` | `/v1/agent-memory/patterns/{pattern_key}/feedback` | Score a pattern |
| `POST` | `/v1/agent-memory/patterns/{pattern_key}/supersede` | Supersede an outdated pattern |

---

## 6. MCP Integration (Model Context Protocol)

OpenGraphMemory exposes Agent Memory to AI coding agents (Claude Code, Cursor, OpenCode, Hermes) via the Model Context Protocol:

* `ogm_recall_code_memory`: Retrieve past bugfixes and refactoring solutions matching a problem signature.
* `ogm_record_code_fix`: Record an episode, attempt, and verified outcome after fixing an issue.
* `memory_observe`: Record an immutable, redacted evidence item during an agent session.
* `memory_commit`: Commit a durable typed memory backed by episode evidence.
