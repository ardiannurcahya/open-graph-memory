import {
  Activity,
  Database,
  FileText,
  Link2,
  Link2Off,
  Network,
  Search,
} from "lucide-react";
import { type FormEvent, useState } from "react";

import type { Credentials } from "../lib/types";

interface SidebarProps {
  connected: boolean;
  onConnect: (credentials: Credentials) => void;
  onDisconnect: () => void;
}

const NAV_ITEMS = [
  { id: "playground", label: "Query Playground", icon: Search },
  { id: "trace", label: "Trace Inspector", icon: Activity },
  { id: "documents", label: "Documents", icon: FileText },
  { id: "graph", label: "Graph Explorer", icon: Network },
];

export function Sidebar({ connected, onConnect, onDisconnect }: SidebarProps) {
  const [draft, setDraft] = useState<Credentials>({ projectId: "", apiKey: "" });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!draft.projectId.trim() || !draft.apiKey.trim()) return;
    onConnect({ projectId: draft.projectId.trim(), apiKey: draft.apiKey.trim() });
  }

  function handleDisconnect() {
    setDraft({ projectId: "", apiKey: "" });
    onDisconnect();
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-logo" aria-hidden="true">
          <Network size={18} strokeWidth={2} />
        </div>
        <div className="sidebar-brand-text">
          <strong>OpenGraphRAG</strong>
          <span>Dashboard &amp; Trace Explorer</span>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Sections">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
          <a key={id} href={`#${id}`} className="sidebar-nav-item">
            <Icon size={15} strokeWidth={2} />
            {label}
          </a>
        ))}
      </nav>

      <form className="sidebar-connection" onSubmit={handleSubmit}>
        <p className="sidebar-section-label">Project Connection</p>
        <label className="field-label" htmlFor="project-id-input">
          Project ID
        </label>
        <input
          id="project-id-input"
          className="field-input"
          value={draft.projectId}
          onChange={(e) => setDraft({ ...draft, projectId: e.target.value })}
          placeholder="UUID"
          autoComplete="off"
          spellCheck={false}
          disabled={connected}
        />
        <label className="field-label" htmlFor="api-key-input">
          API Key
        </label>
        <input
          id="api-key-input"
          className="field-input"
          type="password"
          value={draft.apiKey}
          onChange={(e) => setDraft({ ...draft, apiKey: e.target.value })}
          placeholder="ogm_..."
          autoComplete="off"
          spellCheck={false}
          disabled={connected}
        />
        {connected ? (
          <button type="button" className="btn btn-disconnect" onClick={handleDisconnect}>
            <Link2Off size={14} strokeWidth={2} />
            Disconnect
          </button>
        ) : (
          <button
            type="submit"
            className="btn btn-connect"
            disabled={!draft.projectId.trim() || !draft.apiKey.trim()}
          >
            <Link2 size={14} strokeWidth={2} />
            Connect
          </button>
        )}
      </form>

      <div className={`sidebar-status ${connected ? "is-connected" : ""}`}>
        <span className="sidebar-status-dot" aria-hidden="true" />
        {connected ? "Connected" : "Not connected"}
      </div>

      <div className="sidebar-footer">
        <Database size={13} strokeWidth={2} />
        <span>M5 Dashboard MVP</span>
      </div>
    </aside>
  );
}
