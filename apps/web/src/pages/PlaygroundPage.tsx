import { useEffect, useState } from "react";
import {
  Search,
  Sparkles,
  SlidersHorizontal,
  Clock,
  Layers,
  Network,
  Binary,
  GitFork,
  FileText,
  AlertCircle,
  Loader2,
  ChevronDown,
  ChevronUp,
  Tag,
  CheckCircle2,
} from "lucide-react";
import { datasetsApi, retrievalApi } from "../api/endpoints";
import type {
  ChunkEvidenceView,
  Dataset,
  ModeRetrievalResult,
  RetrievalMode,
  RetrievalResponse,
} from "../api/types";

const EXAMPLE_QUERIES = [
  "How does pgvector dense semantic search work?",
  "Who are the core entities and their relation paths?",
  "What is the token authentication and refresh flow?",
  "Show database schema migrations and indexing",
];

export default function PlaygroundPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("");
  const [query, setQuery] = useState("");
  const [activeTab, setActiveTab] = useState<"compare" | RetrievalMode>("compare");
  const [topK, setTopK] = useState(8);
  const [vectorWeight, setVectorWeight] = useState(0.5);
  const [graphWeight, setGraphWeight] = useState(0.5);
  const [showSettings, setShowSettings] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<RetrievalResponse | null>(null);

  // Load datasets on mount
  useEffect(() => {
    let cancelled = false;
    datasetsApi
      .list()
      .then((data) => {
        if (!cancelled && data.length > 0) {
          setDatasets(data);
          const active = data.find((d) => d.status === "active") ?? data[0];
          setSelectedDatasetId(active.id);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          console.error("Failed to load datasets:", err);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSearch = async (overrideQuery?: string) => {
    const q = (overrideQuery ?? query).trim();
    if (!q) {
      setError("Please enter a query string.");
      return;
    }
    if (!selectedDatasetId) {
      setError("Please select or create a dataset first.");
      return;
    }

    setError(null);
    setLoading(true);

    try {
      const isCompare = activeTab === "compare";
      const mode: RetrievalMode = isCompare ? "hybrid" : activeTab;

      const res = await retrievalApi.query({
        query: q,
        dataset_id: selectedDatasetId,
        mode,
        top_k: topK,
        vector_weight: vectorWeight,
        graph_weight: graphWeight,
        compare: isCompare,
      });

      setResponse(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Retrieval query failed";
      setError(msg);
      setResponse(null);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSearch();
    }
  };

  const handlePresetClick = (preset: string) => {
    setQuery(preset);
    void handleSearch(preset);
  };

  return (
    <div className="px-6 py-8 sm:px-10 max-w-7xl mx-auto space-y-8">
      {/* Title & Description */}
      <div className="border-b border-mac pb-6 space-y-2">
        <div className="inline-flex items-center gap-1.5 rounded-full bg-muted text-main px-3 py-1 text-xs font-semibold border border-mac">
          <Sparkles className="h-3.5 w-3.5 text-mac-accent" />
          <span>PostgreSQL pgvector + GraphRAG Fusion</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-main">
          RAG Comparison Playground
        </h1>
        <p className="text-sm text-subdued max-w-3xl">
          Test and compare retrieval strategies side-by-side using unified PostgreSQL storage:
          Dense Semantic Search (<code className="font-mono text-xs text-mac-accent">pgvector</code>),
          Entity Knowledge Graph Traversal (<code className="font-mono text-xs text-mac-accent">GraphRAG</code>),
          and Reciprocal Rank Fusion (<code className="font-mono text-xs text-mac-accent">Hybrid RAG</code>).
        </p>
      </div>

      {/* Controls Bar */}
      <div className="rounded-xl border border-mac bg-surface p-5 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center">
          {/* Dataset Selector */}
          <div className="sm:w-64 flex-shrink-0">
            <label className="block text-xs font-semibold text-subdued mb-1">
              Target Dataset
            </label>
            <select
              value={selectedDatasetId}
              onChange={(e) => setSelectedDatasetId(e.target.value)}
              className="w-full rounded-lg border border-mac bg-canvas px-3 py-2 text-xs font-medium text-main focus:outline-none focus:ring-2 focus:ring-mac-accent"
              disabled={loading || datasets.length === 0}
            >
              {datasets.length === 0 ? (
                <option value="">No datasets found</option>
              ) : (
                datasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.id})
                  </option>
                ))
              )}
            </select>
          </div>

          {/* Search Query Input */}
          <div className="flex-1">
            <label className="block text-xs font-semibold text-subdued mb-1">
              Search Query
            </label>
            <div className="relative flex items-center">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Enter prompt or technical question..."
                className="w-full rounded-lg border border-mac bg-canvas pl-9 pr-24 py-2 text-xs font-medium text-main placeholder:text-subdued focus:outline-none focus:ring-2 focus:ring-mac-accent"
                disabled={loading}
              />
              <Search className="absolute left-3 h-4 w-4 text-subdued pointer-events-none" />
              <button
                type="button"
                onClick={() => void handleSearch()}
                disabled={loading || !query.trim() || !selectedDatasetId}
                className="absolute right-1.5 flex items-center gap-1.5 rounded-md bg-mac-accent px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {loading ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>Searching</span>
                  </>
                ) : (
                  <span>Retrieve</span>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Quick Example Query Pills */}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="text-[11px] font-semibold text-subdued">Examples:</span>
          {EXAMPLE_QUERIES.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => handlePresetClick(q)}
              className="rounded-md border border-mac bg-muted/60 hover:bg-muted px-2 py-1 text-[11px] font-medium text-main transition-colors text-left"
            >
              {q}
            </button>
          ))}
        </div>

        {/* Mode Toggle & Settings Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-mac">
          {/* Mode Switcher */}
          <div className="inline-flex rounded-lg border border-mac bg-muted/40 p-0.5 text-xs font-medium">
            <button
              type="button"
              onClick={() => setActiveTab("compare")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition-all ${
                activeTab === "compare"
                  ? "bg-surface text-main font-bold shadow-sm"
                  : "text-subdued hover:text-main"
              }`}
            >
              <Sparkles className="h-3.5 w-3.5 text-mac-accent" />
              <span>Compare All</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("vector")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition-all ${
                activeTab === "vector"
                  ? "bg-surface text-main font-bold shadow-sm"
                  : "text-subdued hover:text-main"
              }`}
            >
              <Binary className="h-3.5 w-3.5 text-blue-500" />
              <span>Vector RAG</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("graph")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition-all ${
                activeTab === "graph"
                  ? "bg-surface text-main font-bold shadow-sm"
                  : "text-subdued hover:text-main"
              }`}
            >
              <Network className="h-3.5 w-3.5 text-emerald-500" />
              <span>GraphRAG</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("hybrid")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition-all ${
                activeTab === "hybrid"
                  ? "bg-surface text-main font-bold shadow-sm"
                  : "text-subdued hover:text-main"
              }`}
            >
              <Layers className="h-3.5 w-3.5 text-purple-500" />
              <span>Hybrid RAG</span>
            </button>
          </div>

          {/* Toggle Parameters Slider */}
          <button
            type="button"
            onClick={() => setShowSettings(!showSettings)}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-subdued hover:text-main transition-colors"
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
            <span>Parameters & Weights</span>
            {showSettings ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>
        </div>

        {/* Collapsible Tuning Drawer */}
        {showSettings && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-3 border-t border-mac bg-canvas/60 p-3 rounded-lg">
            <div>
              <div className="flex justify-between text-xs font-semibold text-subdued mb-1">
                <span>Top K Chunks</span>
                <span className="font-mono text-main">{topK}</span>
              </div>
              <input
                type="range"
                min={1}
                max={20}
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
                className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-mac-accent"
              />
            </div>
            <div>
              <div className="flex justify-between text-xs font-semibold text-subdued mb-1">
                <span>Vector Weight (w_vec)</span>
                <span className="font-mono text-main">{vectorWeight.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={vectorWeight}
                onChange={(e) => setVectorWeight(Number(e.target.value))}
                className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-blue-500"
              />
            </div>
            <div>
              <div className="flex justify-between text-xs font-semibold text-subdued mb-1">
                <span>Graph Weight (w_graph)</span>
                <span className="font-mono text-main">{graphWeight.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={graphWeight}
                onChange={(e) => setGraphWeight(Number(e.target.value))}
                className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-emerald-500"
              />
            </div>
          </div>
        )}
      </div>

      {/* Error Alert */}
      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-xs font-semibold text-red-600 dark:text-red-400 flex items-center gap-2">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Latency Summary Bar if response available */}
      {response && (
        <div className="rounded-xl border border-mac bg-surface px-5 py-3 shadow-sm flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-xs font-semibold text-main">
            <Clock className="h-4 w-4 text-mac-accent" />
            <span>Overall Execution Latency:</span>
            <span className="font-mono font-bold text-mac-accent">{response.latency_ms} ms</span>
          </div>

          {response.comparison && (
            <div className="flex items-center gap-4 text-xs font-medium">
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-blue-500"></span>
                <span className="text-subdued">Vector:</span>
                <span className="font-mono font-semibold text-main">
                  {response.comparison.vector.latency_ms} ms
                </span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
                <span className="text-subdued">Graph:</span>
                <span className="font-mono font-semibold text-main">
                  {response.comparison.graph.latency_ms} ms
                </span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-purple-500"></span>
                <span className="text-subdued">Hybrid Fusion:</span>
                <span className="font-mono font-semibold text-main">
                  {response.comparison.hybrid.latency_ms} ms
                </span>
              </span>
            </div>
          )}
        </div>
      )}

      {/* Comparison Grid or Single Mode Results */}
      {response?.comparison ? (
        /* 3-Column Side-by-Side Comparison */
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <ResultColumn
            title="Vector RAG"
            subtitle="Dense Cosine Similarity (pgvector)"
            icon={Binary}
            badgeColor="text-blue-500 bg-blue-500/10 border-blue-500/30"
            result={response.comparison.vector}
          />
          <ResultColumn
            title="GraphRAG"
            subtitle="Entity & Relation Graph Traversal"
            icon={Network}
            badgeColor="text-emerald-500 bg-emerald-500/10 border-emerald-500/30"
            result={response.comparison.graph}
          />
          <ResultColumn
            title="Hybrid RAG"
            subtitle="Reciprocal Rank Fusion (RRF)"
            icon={Layers}
            badgeColor="text-purple-500 bg-purple-500/10 border-purple-500/30"
            result={response.comparison.hybrid}
            isHybrid
          />
        </div>
      ) : response ? (
        /* Single Mode View */
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b border-mac pb-2">
            <h2 className="text-sm font-bold text-main uppercase tracking-wider flex items-center gap-2">
              <span>{response.mode.toUpperCase()} Retrieval Results</span>
            </h2>
            <span className="text-xs font-semibold text-subdued font-mono">
              {response.result.total_chunks} chunks ({response.result.latency_ms} ms)
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {response.result.chunks.map((chunk) => (
              <ChunkCard key={chunk.chunk_id} chunk={chunk} isHybrid={response.mode === "hybrid"} />
            ))}
          </div>
        </div>
      ) : (
        /* Empty / Welcome State */
        <div className="rounded-xl border border-dashed border-mac bg-surface/50 p-12 text-center space-y-6">
          <div className="flex justify-center items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-500/10 text-blue-500 border border-blue-500/20">
              <Binary className="h-6 w-6" />
            </div>
            <span className="text-subdued font-bold">+</span>
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
              <Network className="h-6 w-6" />
            </div>
            <span className="text-subdued font-bold">=</span>
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-purple-500/10 text-purple-500 border border-purple-500/20">
              <Layers className="h-6 w-6" />
            </div>
          </div>
          <div className="max-w-md mx-auto space-y-2">
            <h3 className="text-base font-bold text-main">
              Explore the Power of Hybrid Retrieval
            </h3>
            <p className="text-xs text-subdued leading-relaxed">
              Vector search captures broad semantic similarity, while Graph traversal provides
              precise relational dependencies. Enter a query or select an example above to run
              all three strategies simultaneously.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function ResultColumn({
  title,
  subtitle,
  icon: Icon,
  badgeColor,
  result,
  isHybrid = false,
}: {
  title: string;
  subtitle: string;
  icon: React.ComponentType<{ className?: string }>;
  badgeColor: string;
  result: ModeRetrievalResult;
  isHybrid?: boolean;
}) {
  return (
    <div className="flex flex-col rounded-xl border border-mac bg-surface shadow-sm overflow-hidden">
      {/* Column Header */}
      <div className="border-b border-mac p-4 bg-muted/20 space-y-1.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className="h-4 w-4 text-mac-accent" />
            <h3 className="text-sm font-bold text-main">{title}</h3>
          </div>
          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold font-mono ${badgeColor}`}>
            {result.latency_ms} ms
          </span>
        </div>
        <p className="text-[11px] text-subdued">{subtitle}</p>

        {/* Entities / Relations Discovery Bar */}
        {(result.entities_found.length > 0 || result.relations_found.length > 0) && (
          <div className="pt-2 space-y-1.5 border-t border-mac/50">
            {result.entities_found.length > 0 && (
              <div className="flex flex-wrap items-center gap-1">
                <span className="text-[10px] font-semibold text-subdued">Nodes:</span>
                {result.entities_found.slice(0, 4).map((ent) => (
                  <span
                    key={ent}
                    className="inline-flex items-center gap-1 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 px-1.5 py-0.5 text-[10px] font-medium"
                  >
                    <Tag className="h-2.5 w-2.5" />
                    {ent}
                  </span>
                ))}
              </div>
            )}
            {result.relations_found.length > 0 && (
              <div className="flex flex-wrap items-center gap-1">
                <span className="text-[10px] font-semibold text-subdued">Hops:</span>
                {result.relations_found.slice(0, 2).map((rel) => (
                  <span
                    key={rel}
                    className="inline-flex items-center gap-1 rounded bg-muted text-main border border-mac px-1.5 py-0.5 text-[10px] font-mono"
                  >
                    <GitFork className="h-2.5 w-2.5 text-mac-accent" />
                    {rel}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Column Content */}
      <div className="flex-1 p-3 space-y-3 overflow-y-auto max-h-[700px]">
        {result.chunks.length === 0 ? (
          <div className="py-12 text-center text-xs text-subdued font-medium">
            No matching chunks retrieved
          </div>
        ) : (
          result.chunks.map((chunk) => (
            <ChunkCard key={chunk.chunk_id} chunk={chunk} isHybrid={isHybrid} />
          ))
        )}
      </div>
    </div>
  );
}

function ChunkCard({ chunk, isHybrid = false }: { chunk: ChunkEvidenceView; isHybrid?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const scorePct = Math.round(chunk.score * 100);

  const getSourceBadge = () => {
    if (chunk.source === "hybrid") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-purple-500/15 text-purple-600 dark:text-purple-400 border border-purple-500/30 px-2 py-0.5 text-[10px] font-bold">
          <CheckCircle2 className="h-3 w-3" />
          Fused (Both)
        </span>
      );
    }
    if (chunk.source === "vector") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-500/30 px-2 py-0.5 text-[10px] font-bold">
          <Binary className="h-3 w-3" />
          Vector Match
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-bold">
        <Network className="h-3 w-3" />
        Graph Walk
      </span>
    );
  };

  return (
    <div className="rounded-lg border border-mac bg-surface p-3.5 shadow-sm space-y-2 hover:border-mac-accent/40 transition-colors">
      {/* Card Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 truncate">
          <FileText className="h-3.5 w-3.5 text-subdued flex-shrink-0" />
          <span className="font-mono text-[11px] font-semibold text-main truncate" title={chunk.chunk_id}>
            {chunk.chunk_id.slice(0, 14)}…
          </span>
        </div>
        {isHybrid ? (
          getSourceBadge()
        ) : (
          <span className="font-mono text-[11px] font-bold text-main">
            {scorePct}%
          </span>
        )}
      </div>

      {/* Score Meter */}
      <div className="space-y-1">
        <div className="flex justify-between text-[10px] font-medium text-subdued">
          <span>Relevance Score</span>
          <span className="font-mono font-bold text-main">{chunk.score.toFixed(4)}</span>
        </div>
        <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${
              chunk.source === "hybrid"
                ? "bg-purple-500"
                : chunk.source === "graph"
                ? "bg-emerald-500"
                : "bg-blue-500"
            }`}
            style={{ width: `${Math.min(100, Math.max(5, scorePct))}%` }}
          />
        </div>
      </div>

      {/* Chunk Content Text */}
      <div className="relative">
        <p
          className={`text-xs text-main leading-relaxed font-normal ${
            !expanded ? "line-clamp-3" : ""
          }`}
        >
          {chunk.content}
        </p>
        {chunk.content.length > 140 && (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="mt-1 text-[10px] font-semibold text-mac-accent hover:underline inline-block"
          >
            {expanded ? "Show less" : "Read full chunk"}
          </button>
        )}
      </div>

      {/* Metadata Tags (Entities, Relations, Source Location) */}
      {(chunk.entities.length > 0 || chunk.source_location) && (
        <div className="pt-2 border-t border-mac/50 flex flex-wrap items-center gap-1.5">
          {chunk.source_location && chunk.source_location.page_number && (
            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-subdued">
              Page {chunk.source_location.page_number}
            </span>
          )}
          {chunk.entities.slice(0, 3).map((e) => (
            <span
              key={e}
              className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-subdued"
            >
              #{e}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
