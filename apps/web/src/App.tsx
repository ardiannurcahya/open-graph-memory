import { AlertCircle, Loader2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { createApiClient, errorMessage } from "./lib/api";
import type { ApiClient } from "./lib/api";
import { useCredentials } from "./lib/useCredentials";
import type {
  Dataset,
  DocumentItem,
  GraphExplorerView,
  GraphSummary,
  QueryResponse,
  RetrievalMode,
} from "./lib/types";
import { DatasetBar } from "./components/DatasetBar";
import { DocumentManager } from "./components/DocumentManager";
import { GraphExplorer } from "./components/GraphExplorer";
import type { CommunityLevel } from "./components/semanticZoom";
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
const UPLOAD_CONCURRENCY = 3;

function isEmptyGraph(value: GraphSummary) {
  return value.entity_count === 0 && value.relation_count === 0 && value.nodes.length === 0 && value.relations.length === 0;
}

function graphStillBuilding(docs: DocumentItem[]) {
  return docs.some((doc) => doc.graph_stage && doc.graph_stage !== "complete");
}

function explorerFromGraph(graph: GraphSummary): GraphExplorerView {
  const degree = new Map(graph.nodes.map((node) => [node.id, 0]));
  for (const relation of graph.relations) {
    degree.set(relation.source_entity_id, (degree.get(relation.source_entity_id) ?? 0) + 1);
    degree.set(relation.target_entity_id, (degree.get(relation.target_entity_id) ?? 0) + 1);
  }
  return {
    dataset_id: graph.dataset_id,
    community_level: 0,
    available_levels: [],
    analytics: null,
    refresh_required: true,
    stats: { entity_count: graph.entity_count, relation_count: graph.relation_count, density: 0 },
    nodes: graph.nodes.map((node) => ({
      id: node.id, canonical_name: node.canonical_name, entity_type: node.entity_type,
      community_id: null, degree: degree.get(node.id) ?? 0, weighted_degree: 0, importance: 0,
    })),
    relations: graph.relations.map((relation) => ({
      id: relation.id, source: relation.source_entity_id, target: relation.target_entity_id,
      type: relation.relation_type, weight: relation.confidence, confidence: relation.confidence,
    })),
    communities: [],
  };
}

function isExplorer(value: unknown): value is GraphExplorerView {
  return Boolean(value && typeof value === "object" && "stats" in value && "communities" in value);
}

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
  const [explorer, setExplorer] = useState<GraphExplorerView | null>(null);
  const [communityLevel, setCommunityLevel] = useState<CommunityLevel>(0);
  const [communityLevelLocked, setCommunityLevelLocked] = useState(false);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [mode, setMode] = useState<RetrievalMode>("hybrid");
  const [streamingStatus, setStreamingStatus] = useState("");

  const [loadingDatasets, setLoadingDatasets] = useState(false);
  const [loadingWorkspace, setLoadingWorkspace] = useState(false);
  const [querying, setQuerying] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deletingDataset, setDeletingDataset] = useState(false);
  const [refreshingAnalytics, setRefreshingAnalytics] = useState(false);
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
    async (datasetId: string, level = communityLevel) => {
      const api = apiRef.current;
      if (!api || !datasetId) return;
      setLoadingWorkspace(true);
      setError("");
      try {
        const [docs, graphResult, explorerResult] = await Promise.all([
          api.listDocuments(datasetId),
          api.graph(datasetId, 100, 1).then(
            (value) => ({ ok: true as const, value }),
            (reason: unknown) => ({ ok: false as const, reason }),
          ),
          api.explorer(datasetId, 100, 200, level).then(
            (value) => ({ ok: true as const, value }),
            (reason: unknown) => ({ ok: false as const, reason }),
          ),
        ]);
        setDocuments(docs);
        if (graphResult.ok) {
          const preserveCurrentGraph = Boolean(
            graph?.dataset_id === datasetId &&
              !isEmptyGraph(graph) &&
              isEmptyGraph(graphResult.value) &&
              docs.length > 0 &&
              graphStillBuilding(docs),
          );
          setGraph(preserveCurrentGraph ? graph : graphResult.value);
          if (preserveCurrentGraph) {
            setError("Knowledge graph: extraction still running or failed; showing last available graph.");
          }
        } else {
          setGraph((current) => (current?.dataset_id === datasetId ? current : null));
          setError(`Knowledge graph: ${errorMessage(graphResult.reason)}`);
        }
        if (explorerResult.ok && isExplorer(explorerResult.value)) {
          setExplorer((current) =>
            current?.dataset_id === datasetId && current.nodes.length > 0 && explorerResult.value.nodes.length === 0 &&
            docs.length > 0 && graphStillBuilding(docs) ? current : explorerResult.value,
          );
        } else if (graphResult.ok) {
          setExplorer((current) =>
            current?.dataset_id === datasetId && current.nodes.length > 0 && isEmptyGraph(graphResult.value) &&
            docs.length > 0 && graphStillBuilding(docs) ? current : explorerFromGraph(graphResult.value),
          );
        } else setExplorer((current) => (current?.dataset_id === datasetId ? current : null));
      } catch (reason) {
        setError(errorMessage(reason));
      } finally {
        setLoadingWorkspace(false);
      }
    },
    [graph, communityLevel],
  );

  // Load datasets on connect.
  useEffect(() => {
    if (connected) void loadDatasets();
    else {
      setDatasets([]);
      setSelectedId("");
      setDocuments([]);
      setGraph(null);
      setExplorer(null);
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
      setExplorer(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, connected]);

  const handleCommunityLevel = useCallback((level: CommunityLevel, manual = true) => {
    if (manual) setCommunityLevelLocked(true);
    setCommunityLevel((current) => current === level ? current : level);
  }, []);

  useEffect(() => {
    if (connected && selectedId) void loadWorkspace(selectedId, communityLevel);
  }, [communityLevel]); // fetch selected membership level

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
      setStreamingStatus("Retrieving evidence...");
      const startedAt = performance.now();
      let firstTokenLatency: number | null = null;
      const streamingResult: QueryResponse = {
        answer: "",
        citations: [],
        retrieval_trace: {
          trace_id: "streaming",
          mode: queryMode,
          channel_candidates: { vector: [], graph: [] },
          fusion: [],
          graph: { status: "streaming", paths: [] },
          chunk_ids: [],
          scores: [],
          latency_ms: 0,
        },
        usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, estimated_cost_usd: 0 },
      };
      setResult(streamingResult);
      const request = {
        dataset_id: selectedId,
        query,
        mode: queryMode,
        top_k: 5,
        graph_depth: queryMode === "vector_only" ? undefined : 2,
      };
      try {
        await api.streamQuery(request, (event) => {
          if (event.event === "status") {
            setStreamingStatus(event.data.stage === "generating" ? "Generating answer..." : "Retrieving evidence...");
          }
          if (event.event === "token") {
            if (firstTokenLatency === null) firstTokenLatency = performance.now() - startedAt;
            setResult((current) =>
              current
                ? {
                    ...current,
                    answer: current.answer + event.data.text,
                    retrieval_trace: {
                      ...current.retrieval_trace,
                      latency_ms: firstTokenLatency ?? current.retrieval_trace.latency_ms,
                    },
                  }
                : current,
            );
          }
          if (event.event === "complete") {
            setResult({
              ...event.data,
              retrieval_trace: {
                ...event.data.retrieval_trace,
                latency_ms: firstTokenLatency ?? event.data.retrieval_trace.latency_ms,
              },
            });
            setStreamingStatus("");
          }
          if (event.event === "error") {
            throw new Error(event.data.message);
          }
        });
      } catch (reason) {
        try {
          const response = await api.query(request);
          setResult(response);
        } catch (fallbackReason) {
          setError(errorMessage(fallbackReason || reason));
          setResult(null);
        }
      } finally {
        setStreamingStatus("");
        setQuerying(false);
      }
    },
    [selectedId],
  );

  const handleUpload = useCallback(
    async (files: File[]) => {
      const api = apiRef.current;
      if (!api || !selectedId || files.length === 0) return;
      const uploadApi = api;
      setUploading(true);
      setError("");
      try {
        const failures: string[] = [];
        let nextIndex = 0;
        async function uploadNext() {
          while (nextIndex < files.length) {
            const file = files[nextIndex];
            nextIndex += 1;
            try {
              await uploadApi.uploadDocument(selectedId, file);
            } catch (reason) {
              failures.push(`${file.name}: ${errorMessage(reason)}`);
            }
          }
        }
        await Promise.all(
          Array.from({ length: Math.min(UPLOAD_CONCURRENCY, files.length) }, uploadNext),
        );
        await loadWorkspace(selectedId);
        if (failures.length > 0) {
          setError(`${files.length - failures.length} of ${files.length} files uploaded. ${failures.join("; ")}`);
        }
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

  const handleRefreshAnalytics = useCallback(async () => {
    const api = apiRef.current;
    if (!api || !selectedId) return;
    setRefreshingAnalytics(true);
    setError("");
    try {
      await api.refreshGraphAnalytics(selectedId);
      await loadWorkspace(selectedId);
    } catch (reason) {
      setError(`Graph analytics: ${errorMessage(reason)}`);
    } finally {
      setRefreshingAnalytics(false);
    }
  }, [loadWorkspace, selectedId]);

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
              streamingStatus={streamingStatus}
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
                graph={explorer}
                loading={loadingWorkspace}
                levelLocked={communityLevelLocked}
                refreshingAnalytics={refreshingAnalytics}
                onRefresh={() => void loadWorkspace(selectedId)}
                onCommunityLevelChange={handleCommunityLevel}
                onCommunityLevelLockChange={setCommunityLevelLocked}
                onRefreshAnalytics={() => void handleRefreshAnalytics()}
              />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
