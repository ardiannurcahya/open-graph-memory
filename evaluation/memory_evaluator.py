from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    scope: str
    subject: str
    predicate: str
    value: str
    status: str = "active"
    supersedes_id: str | None = None

    @property
    def content(self) -> str:
        return f"{self.subject} {self.predicate}: {self.value}"


def search_memory(records: list[MemoryRecord], query: str, scopes: set[str]) -> list[MemoryRecord]:
    terms = {term.lower() for term in query.split() if len(term) > 1}
    scored = []
    for record in records:
        if record.scope not in scopes or record.status != "active":
            continue
        matched = sum(1 for term in terms if term in record.content.lower())
        if matched:
            scored.append((matched, record))
    return [record for _, record in sorted(scored, key=lambda item: item[0], reverse=True)]


def evaluate_memory_preview() -> dict[str, float]:
    records = [
        MemoryRecord("old", "user", "alice", "prefers_language", "English", "superseded"),
        MemoryRecord("new", "user", "alice", "prefers_language", "Indonesian", "active", "old"),
        MemoryRecord("agent", "agent", "support-bot", "tone", "concise and factual"),
        MemoryRecord("session", "session", "current-task", "goal", "finish memory preview"),
    ]
    language_hits = search_memory(records, "alice language Indonesian", {"user"})
    session_hits = search_memory(records, "finish memory preview", {"session"})
    agent_hits = search_memory(records, "support tone factual", {"agent"})
    return {
        "active_recall": float(bool(language_hits) and language_hits[0].id == "new"),
        "scope_precision": float(
            bool(session_hits) and all(hit.scope == "session" for hit in session_hits)
        ),
        "agent_recall": float(bool(agent_hits) and agent_hits[0].id == "agent"),
        "supersession_correctness": float(
            records[1].supersedes_id == "old" and records[0].status == "superseded"
        ),
    }


if __name__ == "__main__":
    metrics = evaluate_memory_preview()
    for name, value in metrics.items():
        print(f"{name}={value:.3f}")
    if min(metrics.values()) < 1.0:
        raise SystemExit(1)
