import { useCallback, useEffect, useRef, useState } from "react";
import { datasetsApi, documentsApi } from "../api/endpoints";
import { ApiError } from "../api/client";
import type { Dataset, Document } from "../api/types";
import { ACCEPTED_EXTENSIONS, hasActiveDocuments } from "../lib/documentStatus";
import { StatusBadge } from "../components/StatusBadge";

const POLL_INTERVAL_MS = 2000;

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const loadDatasets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDatasets(await datasetsApi.list());
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "failed to load datasets");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDatasets();
  }, [loadDatasets]);

  const loadDocuments = useCallback(async (datasetId: string) => {
    try {
      setDocuments(await documentsApi.list(datasetId));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "failed to load documents");
    }
  }, []);

  useEffect(() => {
    if (selectedId) void loadDocuments(selectedId);
    else setDocuments([]);
  }, [selectedId, loadDocuments]);

  // Poll while any document is still processing.
  useEffect(() => {
    if (!selectedId || !hasActiveDocuments(documents.map((d) => d.status))) return;
    const timer = setInterval(() => void loadDocuments(selectedId), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [selectedId, documents, loadDocuments]);

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const created = await datasetsApi.create({
        name: newName.trim(),
        description: newDescription.trim() || null,
      });
      setDatasets((prev) => [...prev, created]);
      setNewName("");
      setNewDescription("");
      setSelectedId(created.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "failed to create dataset");
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteDataset = async (datasetId: string) => {
    if (!confirm("Delete this dataset and all its documents?")) return;
    try {
      await datasetsApi.delete(datasetId);
      setDatasets((prev) => prev.filter((d) => d.id !== datasetId));
      if (selectedId === datasetId) setSelectedId(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "failed to delete dataset");
    }
  };

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !selectedId) return;
    setUploading(true);
    setError(null);
    try {
      await documentsApi.upload(selectedId, file);
      await loadDocuments(selectedId);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "upload failed");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const handleDeleteDocument = async (documentId: string) => {
    if (!confirm("Delete this document?")) return;
    try {
      await documentsApi.delete(documentId);
      if (selectedId) await loadDocuments(selectedId);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "failed to delete document");
    }
  };

  const selected = datasets.find((d) => d.id === selectedId) ?? null;

  return (
    <div className="px-8 py-6">
      <h2 className="text-xl font-semibold text-stone-900">Datasets</h2>
      {error && (
        <div className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      )}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-4">
          <form onSubmit={handleCreate} className="space-y-3 rounded-lg border border-stone-200 bg-white p-4">
            <h3 className="font-semibold text-stone-900">New Dataset</h3>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Dataset name"
              className="block w-full rounded-md border border-stone-300 px-3 py-2 text-sm focus:border-stone-900 focus:outline-none"
            />
            <textarea
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              placeholder="Description (optional)"
              rows={2}
              className="block w-full rounded-md border border-stone-300 px-3 py-2 text-sm focus:border-stone-900 focus:outline-none"
            />
            <button
              type="submit"
              disabled={creating || !newName.trim()}
              className="w-full rounded-md bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-700 disabled:opacity-50"
            >
              {creating ? "Creating…" : "Create Dataset"}
            </button>
          </form>

          <div className="rounded-lg border border-stone-200 bg-white">
            <div className="border-b border-stone-200 px-4 py-2 text-sm font-semibold text-stone-700">
              Datasets {loading && "· loading…"}
            </div>
            <ul className="divide-y divide-stone-100">
              {datasets.map((d) => (
                <li key={d.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(d.id)}
                    className={`flex w-full items-center justify-between px-4 py-2 text-left text-sm hover:bg-stone-50 ${
                      selectedId === d.id ? "bg-stone-100" : ""
                    }`}
                  >
                    <span className="truncate font-medium text-stone-900">{d.name}</span>
                    <span
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void handleDeleteDataset(d.id);
                      }}
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleDeleteDataset(d.id);
                      }}
                      className="ml-2 text-xs text-red-600 hover:underline"
                    >
                      delete
                    </span>
                  </button>
                </li>
              ))}
              {!loading && datasets.length === 0 && (
                <li className="px-4 py-3 text-sm text-stone-400">No datasets yet.</li>
              )}
            </ul>
          </div>
        </div>

        <div className="lg:col-span-2">
          {selected ? (
            <div className="rounded-lg border border-stone-200 bg-white">
              <div className="flex items-center justify-between border-b border-stone-200 px-4 py-3">
                <div>
                  <h3 className="font-semibold text-stone-900">{selected.name}</h3>
                  {selected.description && (
                    <p className="text-sm text-stone-500">{selected.description}</p>
                  )}
                </div>
                <label className="cursor-pointer rounded-md bg-stone-900 px-3 py-1.5 text-sm font-semibold text-white hover:bg-stone-700">
                  {uploading ? "Uploading…" : "Upload"}
                  <input
                    ref={fileInput}
                    type="file"
                    accept={ACCEPTED_EXTENSIONS.join(",")}
                    onChange={handleUpload}
                    disabled={uploading}
                    className="hidden"
                  />
                </label>
              </div>
              <ul className="divide-y divide-stone-100">
                {documents.map((doc) => (
                  <li key={doc.id} className="px-4 py-3">
                    <div className="flex items-center justify-between">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-stone-900">
                          {doc.filename}
                          {doc.duplicate && (
                            <span className="ml-2 text-xs text-stone-400">duplicate</span>
                          )}
                        </p>
                        <p className="text-xs text-stone-500">
                          {(doc.size_bytes / 1024).toFixed(1)} KB · {doc.mime_type}
                        </p>
                        {doc.error_message && (
                          <p className="mt-1 text-xs text-red-600">{doc.error_message}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-3">
                        <StatusBadge status={doc.status} />
                        <button
                          type="button"
                          onClick={() => void handleDeleteDocument(doc.id)}
                          className="text-xs text-red-600 hover:underline"
                        >
                          delete
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
                {documents.length === 0 && (
                  <li className="px-4 py-6 text-sm text-stone-400">
                    No documents. Upload a supported file ({ACCEPTED_EXTENSIONS.join(", ")}).
                  </li>
                )}
              </ul>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-stone-300 p-12 text-sm text-stone-400">
              Select or create a dataset to manage documents.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
