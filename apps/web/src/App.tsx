import { AlertCircle, Loader2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { createApiClient, errorMessage } from "./lib/api";
import type { ApiClient } from "./lib/api";
import { useCredentials } from "./lib/useCredentials";
import type {
  Dataset,
  DocumentItem,
  GraphSummary,
  QueryResponse,
  RetrievalMode,
} from "./lib/types";
import { DatasetBar } from "./components/DatasetBar";
import { DocumentManager } from "./components/DocumentManager";
import { GraphExplorer } from "./components/GraphExplorer";
import { QueryPlayground } from "./components/QueryPlayground";
import { Sidebar } from "./components/Sidebar";
import { TraceInspector } from "./components/TraceInspector";

const PROCESSING_STATES = new Set([
  "pending_upload",
  "uploaded",
  "queued",
  "parsing",
  "chunking",
  "embedding",
  "persisting",
  "deleting",
]);

export function App() {
  const { credentials, save, clear } = useCredentials();
  const connected = Boolean(credentials.projectId && credentials.apiKey);

  const apiRef = useRef<ApiClient | null>(null);
  if (connected) {
    apiRef.current = createApiClient({
      projectId: credentials.projectId,
      apiKey: credentials.apiKey,
    });
  } else {
    apiRef.current = null;
  }

  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [graph, setGraph] = useState<GraphSummary | null>(null);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [mode, setMode] = useState<RetrievalMode>("hybrid");

  const [loadingDatasets, setLoadingDatasets] = useState(false);
  const [loadingWorkspace, setLoadingWorkspace] = useState(false);
  const [querying, setQuerying] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deletingDataset, setDeletingDataset] = useState(false);
  const [error, setError] = useState("");

  const selectedDataset = useMemo(
    () => datasets.find((d) => d.id === selectedId) ?? null,
    [datasets, selectedId],
  );

  const hasProcessingDocs = documents.some((d) => PROCESSING_STATES.has(d.status));

  const loadDatasets = useCallback(async () => {
    const api = apiRef.current;
    if (!api) return;
    setLoadingDatasets(true);
    setError("");
    try {
      const rows = await api.listDatasets();
      setDatasets(rows);
      setSelectedId((current) => (rows.some((r) => r.id === current) ? current : rows[0]?.id ?? ""));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoadingDatasets(false);
    }
  }, []);

  const loadWorkspace = useCallback(
    async (datasetId: string) => {
      const api = apiRef.current;
      if (!api || !datasetId) return;
      setLoadingWorkspace(true);
      setError("");
      try {
        const [docs, graphData] = await Promise.all([
          api.listDocuments(datasetId),
          api.graph(datasetId, 100, 1).catch(() => null),
        ]);
        setDocuments(docs);
        setGraph(graphData);
      } catch (reason) {
        setError(errorMessage(reason));
      } finally {
        setLoadingWorkspace(false);
      }
    },
    [],
  );

  // Load datasets on connect.
  useEffect(() => {
    if (connected) void loadDatasets();
    else {
      setDatasets([]);
      setSelectedId("");
      setDocuments([]);
      setGraph(null);
      setResult(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected]);

  // Load workspace when dataset changes.
  useEffect(() => {
    if (connected && selectedId) void loadWorkspace(selectedId);
    else {
      setDocuments([]);
      setGraph(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, connected]);

  // Poll for document status updates while processing.
  useEffect(() => {
    if (!connected || !selectedId || !hasProcessingDocs) return;
    const timer = setInterval(() => void loadWorkspace(selectedId), 4000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected, selectedId, hasProcessingDocs]);

  const handleDisconnect = useCallback(() => {
    clear();
  }, [clear]);

  const handleCreateDataset = useCallback(
    async (name: string) => {
      const api = apiRef.current;
      if (!api) return;
      try {
        await api.createDataset({ name });
        await loadDatasets();
      } catch (reason) {
        setError(errorMessage(reason));
      }
    },
    [loadDatasets],
  );

  const handleDeleteDataset = useCallback(
    async (id: string) => {
      const api = apiRef.current;
      if (!api || !id) return;
      if (
        !window.confirm(
          "Delete this dataset and all its documents, graph projections, and query history? This cannot be undone.",
        )
      )
        return;
      setDeletingDataset(true);
      setError("");
      try {
        await api.deleteDataset(id);
        setDocuments([]);
        setGraph(null);
        setResult(null);
        await loadDatasets();
      } catch (reason) {
        setError(errorMessage(reason));
      } finally {
        setDeletingDataset(false);
      }
    },
    [loadDatasets],
  );

  const handleQuery = useCallback(
    async (query: string, queryMode: RetrievalMode) => {
      const api = apiRef.current;
      if (!api || !selectedId) return;
      setMode(queryMode);
      setQuerying(true);
      setError("");
      try {
        const response = await api.query({
          dataset_id: selectedId,
          query,
          mode: queryMode,
          top_k: 5,
          graph_depth: queryMode === "vector_only" ? undefined : 2,
        });
        setResult(response);
      } catch (reason) {
        setError(errorMessage(reason));
        setResult(null);
      } finally {
        setQuerying(false);
      }
    },
    [selectedId],
  );

  const handleUpload = useCallback(
    async (file: File) => {
      const api = apiRef.current;
      if (!api || !selectedId) return;
      setUploading(true);
      setError("");
      try {
        await api.uploadDocument(selectedId, file);
        await loadWorkspace(selectedId);
      } catch (reason) {
        setError(errorMessage(reason));
      } finally {
        setUploading(false);
      }
    },
    [selectedId, loadWorkspace],
  );

  const handleDeleteDocument = useCallback(
    async (id: string) => {
      const api = apiRef.current;
      if (!api) return;
      if (!window.confirm("Delete this document and its graph projection?")) return;
      setError("");
      try {
        await api.deleteDocument(id);
        await loadWorkspace(selectedId);
      } catch (reason) {
        setError(errorMessage(reason));
      }
    },
    [selectedId, loadWorkspace],
  );

  return (
    <div className="app-shell">
      <Sidebar
        connected={connected}
        onConnect={(next) => save(next)}
        onDisconnect={handleDisconnect}
      />

      <main className="app-main">
        <header className="app-header">
          <div>
            <p className="app-header-eyebrow">OpenGraphRAG Control Plane</p>
            <h1 className="app-header-title">Dashboard &amp; Trace Explorer</h1>
          </div>
          <div className={`app-header-status ${connected ? "is-online" : ""}`}>
            <span className="status-dot" aria-hidden="true" />
            {connected ? "Connected" : "Not connected"}
          </div>
        </header>

        {error && (
          <div className="error-banner" role="alert">
            <AlertCircle size={16} strokeWidth={2} />
            <span>{error}</span>
            <button onClick={() => setError("")} aria-label="Dismiss error">
              <X size={15} strokeWidth={2} />
            </button>
          </div>
        )}

        {!connected && (
          <div className="connect-prompt">
            <div className="connect-prompt-inner">
              <h2>Connect to your project</h2>
              <p>
                Enter your Project ID and API key in the sidebar to manage datasets, upload
                documents, run queries, and inspect retrieval traces.
              </p>
            </div>
          </div>
        )}

        {connected && (
          <>
            {loadingDatasets && datasets.length === 0 ? (
              <div className="loading-state">
                <Loader2 size={24} strokeWidth={2} className="spin" />
                <span>Loading datasets...</span>
              </div>
            ) : (
              <DatasetBar
                datasets={datasets}
                selectedId={selectedId}
                onSelect={setSelectedId}
                onCreate={handleCreateDataset}
                onDelete={handleDeleteDataset}
                documentCount={documents.length}
                entityCount={graph?.entity_count ?? 0}
                relationCount={graph?.relation_count ?? 0}
                loading={loadingDatasets}
                deleting={deletingDataset}
              />
            )}

            <div className="grid-top">
              <QueryPlayground
                datasetName={selectedDataset?.name ?? null}
                disabled={!selectedId}
                loading={querying}
                onQuery={handleQuery}
                result={result}
              />
              <TraceInspector result={result} currentMode={mode} />
            </div>

            <div className="grid-bottom">
              <DocumentManager
                documents={documents}
                loading={loadingWorkspace}
                uploading={uploading}
                onUpload={handleUpload}
                onDelete={handleDeleteDocument}
                onRefresh={() => void loadWorkspace(selectedId)}
              />
              <GraphExplorer
                graph={graph}
                loading={loadingWorkspace}
                onRefresh={() => void loadWorkspace(selectedId)}
              />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
