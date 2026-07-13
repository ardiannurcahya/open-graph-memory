import { FolderPlus, Hash, Loader2, Trash2 } from "lucide-react";
import { type FormEvent, useState } from "react";

import type { Dataset } from "../lib/types";

interface DatasetBarProps {
  datasets: Dataset[];
  selectedId: string;
  onSelect: (id: string) => void;
  onCreate: (name: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  documentCount: number;
  entityCount: number;
  relationCount: number;
  loading: boolean;
  deleting: boolean;
}

export function DatasetBar({
  datasets,
  selectedId,
  onSelect,
  onCreate,
  onDelete,
  documentCount,
  entityCount,
  relationCount,
  loading,
  deleting,
}: DatasetBarProps) {
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    try {
      await onCreate(name.trim());
      setName("");
    } finally {
      setCreating(false);
    }
  }

  return (
    <section className="dataset-bar" aria-label="Dataset selection">
      <div className="dataset-bar-select">
        <label className="field-label" htmlFor="dataset-select">
          Active Dataset
        </label>
        <div className="dataset-select-row">
          <select
            id="dataset-select"
            className="field-select"
            value={selectedId}
            onChange={(e) => onSelect(e.target.value)}
            disabled={loading && datasets.length === 0}
          >
            <option value="">{datasets.length ? "Select a dataset" : "No datasets"}</option>
            {datasets.map((ds) => (
              <option key={ds.id} value={ds.id}>
                {ds.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn btn-icon btn-danger"
            onClick={() => void onDelete(selectedId)}
            disabled={!selectedId || deleting}
            aria-label="Delete active dataset"
            title="Delete active dataset"
          >
            {deleting ? (
              <Loader2 size={15} strokeWidth={2} className="spin" />
            ) : (
              <Trash2 size={15} strokeWidth={2} />
            )}
          </button>
        </div>
      </div>

      <div className="dataset-stats">
        <Stat label="Documents" value={documentCount} />
        <Stat label="Entities" value={entityCount} />
        <Stat label="Relations" value={relationCount} />
      </div>

      <form className="dataset-create" onSubmit={handleCreate}>
        <input
          className="field-input"
          aria-label="New dataset name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New dataset name"
          maxLength={255}
        />
        <button type="submit" className="btn btn-icon" disabled={creating || !name.trim()} title="Create dataset">
          <FolderPlus size={15} strokeWidth={2} />
        </button>
      </form>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat">
      <strong>{value}</strong>
      <span>
        <Hash size={10} strokeWidth={2} />
        {label}
      </span>
    </div>
  );
}
