import { useState, useEffect, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { Database, Network, UploadCloud, Trash2, CheckCircle2, Clock, AlertCircle } from "lucide-react";
import { datasetsApi, documentsApi } from "../api/endpoints";
import { ApiError } from "../api/client";
import type { Dataset, Document } from "../api/types";

const ACCEPTED_EXTENSIONS = [".txt", ".md", ".html", ".json", ".pdf", ".csv"];
const POLL_INTERVAL_MS = 2000;

function hasActiveDocuments(statuses: string[]) {
  return statuses.some((status) => ["queued", "uploaded", "processing", "indexing"].includes(status));
}

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deletingDocId, setDeletingDocId] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const selectedIdRef = useRef<string | null>(null);
  selectedIdRef.current = selectedId;

  const loadDatasets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await datasetsApi.list();
      setDatasets(list);
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

  // Poll while any document is still processing
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
      setError(err instanceof ApiError ? err.detail : "dataset creation failed");
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteDataset = async (datasetId: string) => {
    if (!confirm("Delete this dataset and all its documents?")) return;
    setDeletingId(datasetId);
    setError(null);
    try {
      await datasetsApi.delete(datasetId);
      setDatasets((prev) => prev.filter((d) => d.id !== datasetId));
      if (selectedId === datasetId) {
        setSelectedId(null);
        setDocuments([]);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "failed to delete dataset");
    } finally {
      setDeletingId(null);
    }
  };

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    const datasetId = selectedIdRef.current;
    if (!file || !datasetId) return;
    setUploading(true);
    setError(null);
    try {
      await documentsApi.upload(datasetId, file);
      await loadDocuments(datasetId);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "upload failed");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const handleDeleteDocument = async (documentId: string) => {
    if (!confirm("Delete this document?")) return;
    const datasetId = selectedIdRef.current;
    setDeletingDocId(documentId);
    setError(null);
    try {
      await documentsApi.delete(documentId);
      if (datasetId) await loadDocuments(datasetId);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "failed to delete document");
    } finally {
      setDeletingDocId(null);
    }
  };

  const selected = datasets.find((d) => d.id === selectedId) ?? null;

  return (
    <div className="px-6 py-8 sm:px-10 max-w-6xl mx-auto space-y-6 text-main antialiased selection:bg-mac-accent selection:text-white">
      {/* Header */}
      <div className="border-b border-mac pb-4">
        <h1 className="text-2xl font-bold tracking-tight text-main flex items-center gap-2">
          Datasets
        </h1>
        <p className="text-xs text-subdued mt-0.5">
          Manage codebase datasets, documents, and trigger AST knowledge graph ingestion.
        </p>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="rounded-xl border border-rose-300 bg-rose-50 dark:bg-rose-950/40 p-3 text-xs font-medium text-rose-700 dark:text-rose-300">
          {error}
        </div>
      )}

      {/* Main Workspace Layout (Sidebar + Finder Panel) */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left Sidebar: New Dataset Form + Dataset List */}
        <div className="space-y-4">
          <form onSubmit={handleCreate} className="space-y-3 rounded-2xl border border-mac bg-surface p-4 shadow-sm">
            <h3 className="font-semibold text-main text-xs uppercase tracking-wider">New Dataset</h3>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Dataset name"
              className="block w-full rounded-lg border border-mac bg-canvas px-3 py-2 text-xs text-main placeholder-subdued focus:border-mac-accent focus:outline-none"
            />
            <textarea
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              placeholder="Description (optional)"
              rows={2}
              className="block w-full rounded-lg border border-mac bg-canvas px-3 py-2 text-xs text-main placeholder-subdued focus:border-mac-accent focus:outline-none resize-none"
            />
            <button
              type="submit"
              disabled={creating || !newName.trim()}
              className="w-full rounded-lg bg-mac-accent px-4 py-2 text-xs font-bold text-white shadow-sm hover:opacity-90 disabled:opacity-40 active:scale-95 transition-all"
            >
              {creating ? "Creating…" : "Create Dataset"}
            </button>
          </form>

          <div className="rounded-2xl border border-mac bg-surface shadow-sm overflow-hidden">
            <div className="border-b border-mac bg-muted px-4 py-3 text-xs font-bold uppercase tracking-wider text-subdued flex items-center justify-between">
              <span>Datasets {loading && "· loading…"}</span>
            </div>

            <ul className="divide-y divide-mac">
              {datasets.map((d) => (
                <li
                  key={d.id}
                  className={`transition-colors flex items-center justify-between group ${
                    selected?.id === d.id
                      ? "bg-mac-accent/10 border-l-4 border-mac-accent"
                      : "hover:bg-muted/60"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => setSelectedId(d.id)}
                    className="w-full px-4 py-3 text-left min-w-0 flex-1"
                  >
                    <p className="text-xs font-bold text-main truncate">{d.name}</p>
                    <p className="text-[10px] text-subdued font-mono truncate">{d.id}</p>
                  </button>

                  <button
                    type="button"
                    aria-label="Delete dataset"
                    disabled={deletingId === d.id}
                    onClick={() => void handleDeleteDataset(d.id)}
                    className="mr-3 p-1 rounded hover:bg-rose-500/20 text-subdued hover:text-rose-500 transition-colors opacity-0 group-hover:opacity-100 disabled:opacity-40"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}

              {!loading && datasets.length === 0 && (
                <li className="px-4 py-6 text-center text-xs text-subdued italic">
                  No datasets yet.
                </li>
              )}
            </ul>
          </div>
        </div>

        {/* Right Panel: Document Manager */}
        <div className="lg:col-span-2">
          {selected ? (
            <div className="rounded-2xl border border-mac bg-surface shadow-sm overflow-hidden space-y-0">
              {/* Dataset Header Bar */}
              <div className="flex flex-wrap items-center justify-between border-b border-mac bg-muted px-5 py-4 gap-3">
                <div>
                  <h3 className="text-base font-bold text-main flex items-center gap-2">
                    <Database className="h-4 w-4 text-mac-accent" />
                    {selected.name}
                  </h3>
                  <p className="text-xs text-subdued mt-0.5 font-mono">
                    ID: {selected.id}
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <Link
                    to="/graph"
                    className="inline-flex items-center gap-1.5 rounded-lg border border-mac bg-surface px-3 py-1.5 text-xs font-bold text-main hover:bg-muted transition-colors shadow-sm"
                  >
                    <Network className="h-3.5 w-3.5 text-mac-accent" />
                    <span>View Graph Explorer</span>
                  </Link>

                  <button
                    type="button"
                    onClick={() => fileInput.current?.click()}
                    disabled={uploading}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-mac-accent px-3.5 py-1.5 text-xs font-bold text-white shadow-sm hover:opacity-90 disabled:opacity-50 active:scale-95 transition-all"
                  >
                    <UploadCloud className="h-4 w-4" />
                    <span>{uploading ? "Uploading…" : "Upload"}</span>
                  </button>
                  <input
                    ref={fileInput}
                    type="file"
                    aria-label="Select document to upload"
                    accept={ACCEPTED_EXTENSIONS.join(",")}
                    onChange={handleUpload}
                    disabled={uploading}
                    className="sr-only"
                  />
                </div>
              </div>

              {/* Documents Table List */}
              <div className="divide-y divide-mac">
                {documents.map((doc) => (
                  <div key={doc.id} className="flex items-center justify-between px-5 py-3.5 hover:bg-muted/50 transition-colors">
                    <div className="flex items-center gap-3 min-w-0 flex-1 pr-4">
                      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted border border-mac text-mac-accent flex-shrink-0">
                        <UploadCloud className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-xs font-bold text-main truncate flex items-center gap-1.5">
                          <span>{doc.filename}</span>
                          {doc.duplicate && (
                            <span className="rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 px-1.5 py-0.2 text-[10px] font-semibold">
                              duplicate
                            </span>
                          )}
                        </p>
                        <p className="text-[11px] text-subdued mt-0.5">
                          {(doc.size_bytes / 1024).toFixed(1)} KB · <span className="font-mono">{doc.mime_type}</span>
                        </p>
                        {doc.error_message && (
                          <p className="text-xs text-rose-500 mt-1">{doc.error_message}</p>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <StatusBadge status={doc.status} />
                      <button
                        type="button"
                        onClick={() => void handleDeleteDocument(doc.id)}
                        disabled={deletingDocId === doc.id}
                        className="p-1.5 rounded-lg hover:bg-rose-500/20 text-subdued hover:text-rose-500 transition-colors"
                        title="Delete Document"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                ))}

                {documents.length === 0 && (
                  <div className="p-10 text-center space-y-3">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted border border-mac text-subdued mx-auto">
                      <UploadCloud className="h-6 w-6 text-mac-accent" />
                    </div>
                    <div>
                      <p className="text-xs font-bold text-main">No documents uploaded yet</p>
                      <p className="text-xs text-subdued mt-1 max-w-sm mx-auto">
                        Upload code files or documents ({ACCEPTED_EXTENSIONS.join(", ")}) to start AST ingestion.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-80 rounded-2xl border border-dashed border-mac bg-surface p-8 text-center space-y-3">
              <Database className="h-10 w-10 text-subdued" />
              <div>
                <p className="text-sm font-bold text-main">Select or Create a Dataset</p>
                <p className="text-xs text-subdued mt-1">
                  Choose a dataset from the left sidebar to manage code files and AST graph documents.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "indexed" || status === "active" || status === "complete") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-bold text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
        <CheckCircle2 className="h-3 w-3" />
        indexed
      </span>
    );
  }
  if (status === "failed" || status === "error") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/10 px-2.5 py-0.5 text-[11px] font-bold text-rose-600 dark:text-rose-400 border border-rose-500/20">
        <AlertCircle className="h-3 w-3" />
        failed
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-sky-500/10 px-2.5 py-0.5 text-[11px] font-bold text-sky-600 dark:text-sky-400 border border-sky-500/20">
      <Clock className="h-3 w-3 animate-spin" />
      {status}
    </span>
  );
}
