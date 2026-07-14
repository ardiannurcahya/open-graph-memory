import { Loader2, Play, Quote, Search } from "lucide-react";
import { type FormEvent, useState } from "react";

import type { Citation, QueryResponse, RetrievalMode } from "../lib/types";

interface QueryPlaygroundProps {
  datasetName: string | null;
  disabled: boolean;
  loading: boolean;
  onQuery: (query: string, mode: RetrievalMode) => Promise<void>;
  result: QueryResponse | null;
  streamingStatus?: string;
}

const MODES: { value: RetrievalMode; label: string; description: string }[] = [
  { value: "vector_only", label: "Vector", description: "Qdrant cosine search only" },
  { value: "graph_only", label: "Graph", description: "Neo4j traversal evidence only" },
  { value: "hybrid", label: "Hybrid", description: "Vector + graph with RRF fusion" },
];

export function QueryPlayground({
  datasetName,
  disabled,
  loading,
  onQuery,
  result,
  streamingStatus,
}: QueryPlaygroundProps) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<RetrievalMode>("hybrid");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!query.trim() || disabled) return;
    await onQuery(query.trim(), mode);
  }

  return (
    <section className="panel" id="playground" aria-labelledby="playground-heading">
      <div className="panel-header">
        <div>
          <span className="panel-eyebrow">Query Playground</span>
          <h2 id="playground-heading" className="panel-title">
            Ask the corpus
          </h2>
        </div>
        {datasetName && <span className="badge">{datasetName}</span>}
      </div>

      <form className="query-form" onSubmit={handleSubmit}>
        <label className="field-label" htmlFor="query-input">
          Question
        </label>
        <textarea
          id="query-input"
          className="query-textarea"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask a question that demands evidence from the indexed documents..."
          rows={3}
          maxLength={10_000}
          disabled={disabled}
        />

        <div className="query-controls">
          <div className="mode-selector" role="radiogroup" aria-label="Retrieval mode">
            {MODES.map(({ value, label, description }) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={mode === value}
                className={`mode-button ${mode === value ? "is-active" : ""}`}
                onClick={() => setMode(value)}
                title={description}
              >
                {label}
              </button>
            ))}
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={disabled || loading || !query.trim()}
          >
            {loading ? (
              <>
                <Loader2 size={15} strokeWidth={2} className="spin" />
                Tracing...
              </>
            ) : (
              <>
                <Play size={15} strokeWidth={2} />
                Run Query
              </>
            )}
          </button>
        </div>
      </form>

      <div className="answer-zone">
        {streamingStatus && <p className="answer-stream-status">{streamingStatus}</p>}
        {result ? <AnswerBlock result={result} /> : <EmptyAnswer />}
      </div>
    </section>
  );
}

function AnswerBlock({ result }: { result: QueryResponse }) {
  return (
    <>
      <div className="answer-header">
        <span className="answer-label">
          <Search size={12} strokeWidth={2} />
          Grounded Answer
        </span>
        <span className="answer-citation-count">{result.citations.length} citations</span>
      </div>
      <FormattedAnswer answer={result.answer} />
      {result.citations.length > 0 && (
        <div className="citations">
          <p className="citations-label">Evidence</p>
          {result.citations.map((c) => (
            <CitationCard key={`${c.chunk_id}-${c.index}`} citation={c} />
          ))}
        </div>
      )}
    </>
  );
}

function FormattedAnswer({ answer }: { answer: string }) {
  const blocks = answer.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);
  return <div className="answer-text">{blocks.map((block, index) => renderBlock(block, index))}</div>;
}

function renderBlock(block: string, index: number) {
  const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
  if (lines.every((line) => /^[-*•]\s+/.test(line))) {
    return <ul key={index}>{lines.map((line) => <li key={line}>{renderInline(line.replace(/^[-*•]\s+/, ""))}</li>)}</ul>;
  }
  if (lines.every((line) => /^\d+[.)]\s+/.test(line))) {
    return <ol key={index}>{lines.map((line) => <li key={line}>{renderInline(line.replace(/^\d+[.)]\s+/, ""))}</li>)}</ol>;
  }
  return <p key={index}>{renderInline(lines.join(" "))}</p>;
}

function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*|\[\d+])/g).filter(Boolean);
  return parts.map((part, index) => {
    if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    if (/^\[\d+]$/.test(part)) return <span key={`${part}-${index}`} className="answer-citation-chip">{part}</span>;
    return <span key={`${part}-${index}`}>{part}</span>;
  });
}

function CitationCard({ citation }: { citation: Citation }) {
  return (
    <details className="citation">
      <summary className="citation-summary">
        <span className="citation-index">[{citation.index}]</span>
        <span className="citation-doc">{citation.document_id.slice(0, 16)}</span>
        <span className="citation-score">{citation.score.toFixed(4)}</span>
      </summary>
      <div className="citation-body">
        <Quote size={14} strokeWidth={2} className="citation-icon" />
        <p className="citation-text">{citation.text}</p>
        <code className="citation-chunk">{citation.chunk_id}</code>
      </div>
    </details>
  );
}

function EmptyAnswer() {
  return (
    <div className="empty-state">
      <Search size={28} strokeWidth={1.5} />
      <p>Your grounded answer and source citations will appear here after running a query.</p>
    </div>
  );
}
