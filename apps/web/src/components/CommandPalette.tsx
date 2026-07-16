import { useState, useEffect, useRef, useCallback } from "react";
import type { GraphState, GraphNode } from "../lib/graphTypes";
import { hexRgba } from "../lib/colorPalette";

interface CommandPaletteProps {
  state: GraphState;
  onSelectNode: (node: GraphNode) => void;
  onClose: () => void;
}

export function CommandPalette({ state, onSelectNode, onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [selection, setSelection] = useState(0);
  const [searchMode, setSearchMode] = useState<"local" | "global">("local");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const filtered = state.nodes.filter((n) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    const tokens = q.split(/\s+/).filter((t) => t.length > 1);
    if (tokens.length === 0) return true;
    const txt = `${n.label} ${n.description} ${n.type}`.toLowerCase();
    return tokens.some((t) => txt.includes(t));
  });
  const items = filtered.slice(0, 15);

  const selectCurrent = useCallback(() => {
    const node = items[selection];
    if (node) {
      onSelectNode(node);
      onClose();
    }
  }, [items, selection, onSelectNode, onClose]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelection((s) => Math.min(s + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelection((s) => Math.max(s - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      selectCurrent();
    } else if (e.key === "Tab") {
      e.preventDefault();
      setSearchMode((m) => (m === "local" ? "global" : "local"));
    }
  };

  return (
    <div
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className="absolute inset-0 z-30 flex items-start justify-center bg-stone-900/30 pt-[15vh] backdrop-blur-sm"
    >
      <div className="w-[560px] max-w-[90vw] overflow-hidden rounded-xl border border-stone-200 bg-white shadow-xl">
        <div className="flex items-center gap-2.5 border-b border-stone-200 px-4 py-3">
          <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="#78716c" strokeWidth={2} strokeLinecap="round">
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelection(0);
            }}
            onKeyDown={handleKeyDown}
            placeholder="Search entities, topics, or type a query..."
            autoComplete="off"
            className="flex-1 border-none bg-transparent text-sm text-stone-800 outline-none"
          />
        </div>

        <div className="max-h-[320px] overflow-y-auto p-1.5">
          {items.length === 0 ? (
            <div className="px-3 py-4 text-sm text-stone-400">No results found.</div>
          ) : (
            items.map((n, i) => {
              const col = state.communities.get(n.community)?.color ?? "#78716c";
              const commName = state.communities.get(n.community)?.name ?? n.community;
              const isSel = i === selection;
              return (
                <div
                  key={n.id}
                  onClick={() => {
                    onSelectNode(n);
                    onClose();
                  }}
                  onMouseEnter={() => setSelection(i)}
                  className={`flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 transition-colors ${
                    isSel ? "bg-stone-100" : ""
                  }`}
                >
                  <div
                    className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md font-mono text-[10px] font-semibold"
                    style={{ background: hexRgba(col, 0.15), color: col }}
                  >
                    {n.type[0].toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-xs font-semibold text-stone-800">{n.label}</div>
                    <div className="mt-0.5 truncate text-[9px] text-stone-400">
                      {commName} · {n.type}
                    </div>
                  </div>
                  <span className="flex-shrink-0 rounded bg-stone-100 px-1.5 py-0.5 font-mono text-[9px] text-stone-500">
                    d{n.degree}
                  </span>
                </div>
              );
            })
          )}
        </div>

        <div className="flex gap-4 border-t border-stone-200 px-4 py-2 font-mono text-[9px] text-stone-400">
          <span>
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> Navigate
          </span>
          <span>
            <Kbd>↵</Kbd> Select
          </span>
          <span>
            <Kbd>Esc</Kbd> Close
          </span>
          <span>
            <Kbd>Tab</Kbd> Mode: {searchMode}
          </span>
        </div>
      </div>
    </div>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="mr-1 inline-block rounded border border-stone-200 bg-stone-50 px-1.5 py-0.5 text-[9px] text-stone-500">
      {children}
    </kbd>
  );
}
