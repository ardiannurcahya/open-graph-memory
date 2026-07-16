import { useCallback, useEffect, useRef, useState } from "react";
import { datasetsApi, queryApi } from "../api/endpoints";
import { ApiError } from "../api/client";
import { streamQuery } from "../api/stream";
import { TraceExplorer } from "../components/TraceExplorer";
import type { Citation, Dataset, QueryMode, QueryResponse, QueryRequest } from "../api/types";

const MODES: QueryMode[] = [
  "vector_only",
  "graph_only",
  "graph_local",
  "graph_global",
  "hybrid",
];

export default function QueryPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<QueryMode>("hybrid");
  const [topK, setTopK] = useState(5);
  const [graphDepth, setGraphDepth] = useState(1);
  const [includeCommunities, setIncludeCommunities] = useState(true);
  const [communityLevel, setCommunityLevel] = useState(0);
  const [useStream, setUseStream] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [streamingText, setStreamingText] = useState("");
  const [stage, setStage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    void datasetsApi.list().then(setDatasets).catch(() => undefined);
  }, []);

  const buildRequest = useCallback((): QueryRequest => {
    const req: QueryRequest = {
      dataset_id: datasetId,
      query,
      mode,
      top_k: topK,
      graph_depth: graphDepth,
      include_communities: mode === "vector_only" ? false : includeCommunities,
      community_level: communityLevel,
    };
    return req;
  }, [datasetId, query, mode, topK, graphDepth, includeCommunities, communityLevel]);

  const runSync = useCallback(async () => {
    setError(null);
    setResult(null);
    setStreamingText("");
    setLoading(true);
    try {
      const response = await queryApi.query(buildRequest());
      setResult(response);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "query failed");
    } finally {
      setLoading(false);
    }
  }, [buildRequest]);

  const runStream = useCallback(async () => {
    setError(null);
    setResult(null);
    setStreamingText("");
    setStage("retrieving");
    setLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      for await (const event of streamQuery(buildRequest(), controller.signal)) {
        if (event.event === "status") {
          setStage((event.data as { stage?: string }).stage ?? null);
        } else if (event.event === "token") {
          setStreamingText((prev) => prev + (event.data as { text?: string }).text);
        } else if (event.event === "complete") {
          setResult(event.data as QueryResponse);
          setStage(null);
        } else if (event.event === "error") {
          const data = event.data as { message?: string };
          setError(data.message ?? "stream error");
          setStage(null);
          break;
        }
      }
    } catch (err) {
      if (err instanceof ApiError) setError(err.detail);
      else if (!(err instanceof DOMException && err.name === "AbortError")) {
        setError("stream failed");
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  }, [buildRequest]);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!datasetId || !query.trim()) return;
    abortRef.current?.abort();
    if (useStream) void runStream();
    else void runSync();
  };

  useEffect(() => () => abortRef.current?.abort(), []);

  const answer = result?.answer ?? streamingText;

  return (
    <div className="px-8 py-6">
      <h2 className="text-xl font-semibold text-stone-900">Query Playground</h2>
      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="text-sm font-medium text-stone-700">Dataset</span>
            <select
              value={datasetId}
              onChange={(e) => setDatasetId(e.target.value)}
              className="mt-1 block w-full rounded-md border border-stone-300 px-3 py-2 text-sm focus:border-stone-900 focus:outline-none"
            >
              <option value="">Select dataset…</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-sm font-medium text-stone-700">Mode</span>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as QueryMode)}
              className="mt-1 block w-full rounded-md border border-stone-300 px-3 py-2 text-sm focus:border-stone-900 focus:outline-none"
            >
              {MODES.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="block">
          <span className="text-sm font-medium text-stone-700">Query</span>
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            rows={3}
            placeholder="Ask a question grounded in the dataset…"
            className="mt-1 block w-full rounded-md border border-stone-300 px-3 py-2 text-sm focus:border-stone-900 focus:outline-none"
          />
        </label>

        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-stone-700">
            <input
              type="checkbox"
              checked={useStream}
              onChange={(e) => setUseStream(e.target.checked)}
            />
            Stream tokens
          </label>
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="text-sm text-stone-600 underline"
          >
            {showAdvanced ? "Hide" : "Advanced"} options
          </button>
          <button
            type="submit"
            disabled={loading || !datasetId || !query.trim()}
            className="ml-auto rounded-md bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-700 disabled:opacity-50"
          >
            {loading ? "Running…" : "Run Query"}
          </button>
        </div>

        {showAdvanced && (
          <div className="grid grid-cols-2 gap-4 rounded-md bg-stone-50 p-4 sm:grid-cols-4">
            <NumberField label="Top K" value={topK} onChange={setTopK} min={1} max={50} />
            <NumberField label="Graph Depth" value={graphDepth} onChange={setGraphDepth} min={1} max={2} />
            <NumberField label="Community Level" value={communityLevel} onChange={setCommunityLevel} min={0} max={2} />
            <label className="flex items-end gap-2 text-sm text-stone-700">
              <input
                type="checkbox"
                checked={includeCommunities}
                onChange={(e) => setIncludeCommunities(e.target.checked)}
              />
              Include communities
            </label>
          </div>
        )}
      </form>

      {error && (
        <div className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      )}
      {stage && (
        <div className="mt-4 text-sm text-stone-500">Stage: {stage}…</div>
      )}

      {(answer || result) && (
        <div className="mt-6 space-y-6">
          <div className="rounded-lg border border-stone-200 bg-white p-4">
            <h3 className="mb-2 font-semibold text-stone-900">Answer</h3>
            <p className="whitespace-pre-wrap text-sm text-stone-800">{answer}</p>
            {result && (
              <p className="mt-3 text-xs text-stone-500">
                Latency {result.retrieval_trace.latency_ms}ms · Tokens{" "}
                {result.usage.total_tokens}
              </p>
            )}
          </div>
          {result && <CitationList citations={result.citations} />}
          {result && <TraceExplorer response={result} />}
        </div>
      )}
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-stone-700">{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 block w-full rounded-md border border-stone-300 px-3 py-2 text-sm focus:border-stone-900 focus:outline-none"
      />
    </label>
  );
}

export function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return <p className="text-sm text-stone-400">No citations.</p>;
  }
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4">
      <h3 className="mb-3 font-semibold text-stone-900">Citations</h3>
      <ol className="space-y-3">
        {citations.map((c) => (
          <li key={c.index} className="text-sm">
            <div className="flex items-center gap-2">
              <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-stone-900 text-xs font-semibold text-white">
                {c.index}
              </span>
              <span className="font-mono text-xs text-stone-500">{c.document_id}</span>
              <span className="text-xs text-stone-400">score {c.score.toFixed(3)}</span>
              {c.source_location && (
                <span className="text-xs text-stone-400">
                  · {Object.entries(c.source_location)
                    .map(([k, v]) => `${k}=${v}`)
                    .join(", ")}
                </span>
              )}
            </div>
            <p className="mt-1 border-l-2 border-stone-200 pl-3 text-stone-700">{c.text}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
