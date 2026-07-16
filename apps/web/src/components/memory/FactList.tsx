import type { MemoryFact } from "../../api/types";
import { StatusBadge } from "../StatusBadge";

interface FactListProps {
  facts: MemoryFact[];
  onDelete?: (id: string) => void;
  emptyMessage?: string;
}

export function FactList({ facts, onDelete, emptyMessage = "No facts." }: FactListProps) {
  if (facts.length === 0) {
    return <p className="text-sm text-stone-400">{emptyMessage}</p>;
  }
  return (
    <ul className="space-y-2">
      {facts.map((fact) => (
        <li
          key={fact.id}
          className="rounded-md border border-stone-200 bg-white px-3 py-2 text-sm"
        >
          <div className="flex items-center justify-between">
            <span className="font-medium text-stone-800">
              {fact.subject} {fact.predicate}: {fact.value}
            </span>
            <div className="flex items-center gap-2">
              <StatusBadge status={fact.status} />
              {onDelete && (
                <button
                  type="button"
                  onClick={() => onDelete(fact.id)}
                  className="text-xs text-red-600 hover:underline"
                >
                  delete
                </button>
              )}
            </div>
          </div>
          <div className="mt-1 flex gap-3 text-xs text-stone-400">
            <span>scope: {fact.scope}</span>
            <span>confidence: {fact.confidence}</span>
            <span>from: {fact.valid_from.slice(0, 10)}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
