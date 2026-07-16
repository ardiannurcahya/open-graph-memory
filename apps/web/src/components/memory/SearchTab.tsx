import { useState } from "react";
import { memoryApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { useMemoryStore } from "../../store/memory";
import type { MemoryScope, MemorySearchHit } from "../../api/types";

const SCOPES: MemoryScope[] = ["user", "agent", "session"];

export function SearchTab() {
  const { users, agents, sessions } = useMemoryStore();
  const [query, setQuery] = useState("");
  const [userId, setUserId] = useState("");
  const [agentId, setAgentId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [scopes, setScopes] = useState<MemoryScope[]>(["user", "agent", "session"]);
  const [limit, setLimit] = useState(10);
  const [results, setResults] = useState<MemorySearchHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleScope = (scope: MemoryScope) => {
    setScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    );
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || scopes.length === 0) return;
    setSearching(true);
    setError(null);
    try {
      setResults(
        await memoryApi.search({
          query: query.trim(),
          user_id: userId || null,
          agent_id: agentId || null,
          session_id: sessionId || null,
          scopes,
          limit,
        }),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "search failed");
      setResults([]);
    } finally {
      setSearching(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await memoryApi.delete(id);
      setResults((prev) => prev.filter((r) => r.id !== id));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "failed to delete fact");
    }
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <div className="rounded-lg border border-stone-200 bg-white p-4">
        <h3 className="mb-3 font-semibold text-stone-900">Search Memory</h3>
        {error && (
          <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
        )}
        <form onSubmit={handleSearch} className="space-y-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search query"
            className="block w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
          />
          <div className="grid grid-cols-3 gap-2">
            <select value={userId} onChange={(e) => setUserId(e.target.value)} className="rounded-md border border-stone-300 px-2 py-1.5 text-sm">
              <option value="">any user</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.external_id}</option>
              ))}
            </select>
            <select value={agentId} onChange={(e) => setAgentId(e.target.value)} className="rounded-md border border-stone-300 px-2 py-1.5 text-sm">
              <option value="">any agent</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
            <select value={sessionId} onChange={(e) => setSessionId(e.target.value)} className="rounded-md border border-stone-300 px-2 py-1.5 text-sm">
              <option value="">any session</option>
              {sessions.map((s) => (
                <option key={s.id} value={s.id}>{s.title ?? s.id}</option>
              ))}
            </select>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            {SCOPES.map((s) => (
              <label key={s} className="flex items-center gap-1 text-sm text-stone-700">
                <input type="checkbox" checked={scopes.includes(s)} onChange={() => toggleScope(s)} />
                {s}
              </label>
            ))}
          </div>
          <label className="block text-sm text-stone-700">
            Limit: {limit}
            <input type="range" min={1} max={50} value={limit} onChange={(e) => setLimit(Number(e.target.value))} className="ml-2" />
          </label>
          <button
            type="submit"
            disabled={searching || !query.trim() || scopes.length === 0}
            className="w-full rounded-md bg-stone-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {searching ? "Searching…" : "Run Search"}
          </button>
        </form>
      </div>

      <div className="rounded-lg border border-stone-200 bg-white p-4">
        <h3 className="mb-3 font-semibold text-stone-900">Results ({results.length})</h3>
        <SearchResults results={results} onDelete={handleDelete} />
      </div>
    </div>
  );
}

function SearchResults({
  results,
  onDelete,
}: {
  results: MemorySearchHit[];
  onDelete: (id: string) => void;
}) {
  if (results.length === 0) {
    return <p className="text-sm text-stone-400">No results yet.</p>;
  }
  return (
    <ul className="space-y-2">
      {results.map((hit) => (
        <li key={hit.id} className="rounded-md border border-stone-200 bg-white px-3 py-2 text-sm">
          <div className="flex items-center justify-between">
            <span className="font-medium text-stone-800">
              {hit.subject} {hit.predicate}: {hit.value}
            </span>
            <div className="flex items-center gap-2">
              <span className="text-xs text-stone-400">score {hit.score.toFixed(2)}</span>
              <button type="button" onClick={() => onDelete(hit.id)} className="text-xs text-red-600 hover:underline">
                delete
              </button>
            </div>
          </div>
          <p className="mt-1 text-xs text-stone-400">
            scope: {hit.scope} · matched: {hit.matched_terms.join(", ")}
          </p>
        </li>
      ))}
    </ul>
  );
}
