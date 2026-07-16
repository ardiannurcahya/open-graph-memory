import { useEffect, useState } from "react";
import { memoryApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { useMemoryStore } from "../../store/memory";
import type { MemoryFact, MemoryScope, MessageRole } from "../../api/types";
import { FactList } from "./FactList";

const ROLES: MessageRole[] = ["user", "assistant", "system", "tool"];
const SCOPES: MemoryScope[] = ["user", "agent", "session"];

export function SessionTab() {
  const sessions = useMemoryStore((s) => s.sessions);
  const [sessionId, setSessionId] = useState("");
  const [role, setRole] = useState<MessageRole>("user");
  const [content, setContent] = useState("");
  const [addFact, setAddFact] = useState(false);
  const [scope, setScope] = useState<MemoryScope>("user");
  const [subject, setSubject] = useState("");
  const [predicate, setPredicate] = useState("");
  const [value, setValue] = useState("");
  const [confidence, setConfidence] = useState(100);
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadMemory = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      setFacts(await memoryApi.getSessionMemory(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "failed to load memory");
      setFacts([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (sessionId) void loadMemory(sessionId);
    else setFacts([]);
  }, [sessionId]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sessionId || !content.trim()) return;
    setSending(true);
    setError(null);
    const body = {
      messages: [{ role, content: content.trim() }],
      facts: addFact && subject.trim() && predicate.trim() && value.trim()
        ? [{ scope, subject: subject.trim(), predicate: predicate.trim(), value: value.trim(), confidence }]
        : [],
    };
    try {
      await memoryApi.addMessages(sessionId, body);
      setContent("");
      setSubject("");
      setPredicate("");
      setValue("");
      setAddFact(false);
      await loadMemory(sessionId);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "failed to add message");
    } finally {
      setSending(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await memoryApi.delete(id);
      if (sessionId) await loadMemory(sessionId);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "failed to delete fact");
    }
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <div className="rounded-lg border border-stone-200 bg-white p-4">
        <h3 className="mb-3 font-semibold text-stone-900">Add Message</h3>
        {error && (
          <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
        )}
        <select
          value={sessionId}
          onChange={(e) => setSessionId(e.target.value)}
          className="mb-3 block w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
        >
          <option value="">Select session…</option>
          {sessions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title ?? s.id}
            </option>
          ))}
        </select>
        <form onSubmit={handleSend} className="space-y-3">
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as MessageRole)}
            className="block w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={3}
            placeholder="Message content"
            className="block w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
          />
          <label className="flex items-center gap-2 text-sm text-stone-700">
            <input type="checkbox" checked={addFact} onChange={(e) => setAddFact(e.target.checked)} />
            Attach a fact
          </label>
          {addFact && (
            <div className="space-y-2 rounded-md bg-stone-50 p-3">
              <select
                value={scope}
                onChange={(e) => setScope(e.target.value as MemoryScope)}
                className="block w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
              >
                {SCOPES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <div className="grid grid-cols-3 gap-2">
                <input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="subject" className="rounded-md border border-stone-300 px-2 py-1.5 text-sm" />
                <input value={predicate} onChange={(e) => setPredicate(e.target.value)} placeholder="predicate" className="rounded-md border border-stone-300 px-2 py-1.5 text-sm" />
                <input value={value} onChange={(e) => setValue(e.target.value)} placeholder="value" className="rounded-md border border-stone-300 px-2 py-1.5 text-sm" />
              </div>
              <label className="block text-sm text-stone-700">
                Confidence: {confidence}
                <input type="range" min={0} max={100} value={confidence} onChange={(e) => setConfidence(Number(e.target.value))} className="ml-2" />
              </label>
            </div>
          )}
          <button
            type="submit"
            disabled={sending || !sessionId || !content.trim()}
            className="w-full rounded-md bg-stone-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {sending ? "Sending…" : "Send Message"}
          </button>
        </form>
      </div>

      <div className="rounded-lg border border-stone-200 bg-white p-4">
        <h3 className="mb-3 font-semibold text-stone-900">Session Memory</h3>
        {!sessionId ? (
          <p className="text-sm text-stone-400">Select a session to view its facts.</p>
        ) : loading ? (
          <p className="text-sm text-stone-400">Loading…</p>
        ) : (
          <FactList facts={facts} onDelete={handleDelete} emptyMessage="No active facts." />
        )}
      </div>
    </div>
  );
}
