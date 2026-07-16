import { useState } from "react";
import { memoryApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { useMemoryStore } from "../../store/memory";

export function EntitiesTab() {
  const { users, agents, sessions, addUser, addAgent, addSession } = useMemoryStore();
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      )}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <CreateCard title="Create User">
          <UserForm onCreated={addUser} onError={setError} />
        </CreateCard>
        <CreateCard title="Create Agent">
          <AgentForm onCreated={addAgent} onError={setError} />
        </CreateCard>
        <CreateCard title="Create Session">
          <SessionForm users={users} agents={agents} onCreated={addSession} onError={setError} />
        </CreateCard>
      </div>

      <div className="space-y-4">
        <RefList title="Users" items={users.map((u) => ({ id: u.id, label: u.external_id, sub: u.display_name }))} />
        <RefList title="Agents" items={agents.map((a) => ({ id: a.id, label: a.name, sub: null }))} />
        <RefList
          title="Sessions"
          items={sessions.map((s) => ({ id: s.id, label: s.title ?? s.id, sub: `${s.user_id} / ${s.agent_id}` }))}
        />
      </div>
    </div>
  );
}

function CreateCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4">
      <h3 className="mb-3 font-semibold text-stone-900">{title}</h3>
      {children}
    </div>
  );
}

function UserForm({
  onCreated,
  onError,
}: {
  onCreated: (u: { id: string; external_id: string; display_name: string | null }) => void;
  onError: (e: string) => void;
}) {
  const [externalId, setExternalId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!externalId.trim()) return;
    setBusy(true);
    try {
      const user = await memoryApi.createUser(externalId.trim(), displayName.trim() || undefined);
      onCreated(user);
      setExternalId("");
      setDisplayName("");
    } catch (err) {
      onError(err instanceof ApiError ? err.detail : "failed to create user");
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="space-y-2">
      <input
        value={externalId}
        onChange={(e) => setExternalId(e.target.value)}
        placeholder="External ID"
        className="block w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
      />
      <input
        value={displayName}
        onChange={(e) => setDisplayName(e.target.value)}
        placeholder="Display name (optional)"
        className="block w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
      />
      <button
        type="submit"
        disabled={busy || !externalId.trim()}
        className="w-full rounded-md bg-stone-900 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
      >
        {busy ? "Creating…" : "Create"}
      </button>
    </form>
  );
}

function AgentForm({
  onCreated,
  onError,
}: {
  onCreated: (a: { id: string; name: string }) => void;
  onError: (e: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      const agent = await memoryApi.createAgent(name.trim(), description.trim() || undefined);
      onCreated(agent);
      setName("");
      setDescription("");
    } catch (err) {
      onError(err instanceof ApiError ? err.detail : "failed to create agent");
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="space-y-2">
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Agent name"
        className="block w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
      />
      <input
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Description (optional)"
        className="block w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
      />
      <button
        type="submit"
        disabled={busy || !name.trim()}
        className="w-full rounded-md bg-stone-900 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
      >
        {busy ? "Creating…" : "Create"}
      </button>
    </form>
  );
}

function SessionForm({
  users,
  agents,
  onCreated,
  onError,
}: {
  users: { id: string; external_id: string }[];
  agents: { id: string; name: string }[];
  onCreated: (s: { id: string; user_id: string; agent_id: string; title: string | null }) => void;
  onError: (e: string) => void;
}) {
  const [userId, setUserId] = useState("");
  const [agentId, setAgentId] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!userId || !agentId) return;
    setBusy(true);
    try {
      const session = await memoryApi.createSession(userId, agentId, title.trim() || undefined);
      onCreated(session);
      setTitle("");
    } catch (err) {
      onError(err instanceof ApiError ? err.detail : "failed to create session");
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="space-y-2">
      <select
        value={userId}
        onChange={(e) => setUserId(e.target.value)}
        className="block w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
      >
        <option value="">Select user…</option>
        {users.map((u) => (
          <option key={u.id} value={u.id}>
            {u.external_id}
          </option>
        ))}
      </select>
      <select
        value={agentId}
        onChange={(e) => setAgentId(e.target.value)}
        className="block w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
      >
        <option value="">Select agent…</option>
        {agents.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name}
          </option>
        ))}
      </select>
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Title (optional)"
        className="block w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
      />
      <button
        type="submit"
        disabled={busy || !userId || !agentId}
        className="w-full rounded-md bg-stone-900 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
      >
        {busy ? "Creating…" : "Create"}
      </button>
    </form>
  );
}

function RefList({
  title,
  items,
}: {
  title: string;
  items: { id: string; label: string; sub: string | null }[];
}) {
  return (
    <div className="rounded-lg border border-stone-200 bg-white">
      <div className="border-b border-stone-200 px-4 py-2 text-sm font-semibold text-stone-700">
        {title} ({items.length})
      </div>
      {items.length === 0 ? (
        <p className="px-4 py-3 text-sm text-stone-400">None created yet.</p>
      ) : (
        <ul className="divide-y divide-stone-100">
          {items.map((item) => (
            <li key={item.id} className="px-4 py-2 text-sm">
              <span className="font-medium text-stone-800">{item.label}</span>
              {item.sub && <span className="ml-2 text-xs text-stone-400">{item.sub}</span>}
              <span className="ml-2 font-mono text-xs text-stone-400">{item.id}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
