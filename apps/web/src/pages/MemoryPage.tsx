import { useState } from "react";
import { EntitiesTab } from "../components/memory/EntitiesTab";
import { SessionTab } from "../components/memory/SessionTab";
import { SearchTab } from "../components/memory/SearchTab";

type Tab = "entities" | "session" | "search";

const TABS: { id: Tab; label: string }[] = [
  { id: "entities", label: "Entities" },
  { id: "session", label: "Session" },
  { id: "search", label: "Search" },
];

export default function MemoryPage() {
  const [tab, setTab] = useState<Tab>("entities");
  return (
    <div className="px-8 py-6">
      <h2 className="text-xl font-semibold text-stone-900">Memory</h2>
      <div className="mt-4 flex gap-2 border-b border-stone-200">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
              tab === t.id
                ? "border-stone-900 text-stone-900"
                : "border-transparent text-stone-500 hover:text-stone-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="mt-6">
        {tab === "entities" && <EntitiesTab />}
        {tab === "session" && <SessionTab />}
        {tab === "search" && <SearchTab />}
      </div>
    </div>
  );
}
