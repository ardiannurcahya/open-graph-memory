import { useState } from "react";
import type { QueryResponse, RetrievalTrace } from "../api/types";

export function TraceExplorer({ response }: { response: QueryResponse }) {
  const [open, setOpen] = useState(false);
  const trace = response.retrieval_trace;
  return (
    <div className="rounded-lg border border-stone-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <span className="font-semibold text-stone-900">Retrieval Trace</span>
        <span className="text-xs text-stone-500">
          {trace.resolved_mode} · {trace.latency_ms}ms · {open ? "hide" : "show"}
        </span>
      </button>
      {open && (
        <div className="space-y-4 border-t border-stone-200 px-4 py-4 text-sm">
          <Summary trace={trace} />
          <Timings trace={trace} />
          <Channels trace={trace} />
          <GraphPaths trace={trace} />
          <Community trace={trace} />
          <MemorySection trace={trace} />
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">{title}</h4>
      {children}
    </div>
  );
}

function Summary({ trace }: { trace: RetrievalTrace }) {
  return (
    <Section title="Summary">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-stone-700 sm:grid-cols-4">
        <Field label="trace_id" value={trace.trace_id} mono />
        <Field label="mode" value={trace.mode} />
        <Field label="resolved_mode" value={trace.resolved_mode} />
        <Field label="intent" value={trace.intent} />
      </dl>
    </Section>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs text-stone-400">{label}</dt>
      <dd className={`truncate text-stone-800 ${mono ? "font-mono text-xs" : ""}`} title={value}>
        {value}
      </dd>
    </div>
  );
}

function Timings({ trace }: { trace: RetrievalTrace }) {
  const t = trace.timings_ms;
  return (
    <Section title="Timings (ms)">
      <div className="flex flex-wrap gap-4 text-stone-700">
        <span>vector {t.vector}</span>
        <span>graph {t.graph}</span>
        <span>hydrate {t.hydrate}</span>
        <span>generation {t.generation}</span>
        <span className="font-semibold">total {trace.latency_ms}</span>
      </div>
    </Section>
  );
}

function Channels({ trace }: { trace: RetrievalTrace }) {
  const c = trace.channel_candidates;
  return (
    <Section title="Channel candidates">
      <div className="space-y-1 text-stone-700">
        <CandidateRow label="vector" items={c.vector} />
        <CandidateRow label="graph" items={c.graph} />
        <CandidateRow label="community" items={c.community} />
      </div>
      {trace.fusion.length > 0 && (
        <p className="mt-2 text-xs text-stone-500">
          fusion: {trace.fusion.length} entr{trace.fusion.length === 1 ? "y" : "ies"}
        </p>
      )}
    </Section>
  );
}

function CandidateRow({
  label,
  items,
}: {
  label: string;
  items: { chunk_id: string; score: number }[];
}) {
  return (
    <div>
      <span className="font-medium">{label}</span>{" "}
      <span className="text-xs text-stone-500">({items.length})</span>
      {items.length > 0 && (
        <span className="ml-2 font-mono text-xs text-stone-600">
          {items.map((i) => `${i.chunk_id}:${i.score.toFixed(2)}`).join(", ")}
        </span>
      )}
    </div>
  );
}

function GraphPaths({ trace }: { trace: RetrievalTrace }) {
  const g = trace.graph;
  if (g.paths.length === 0) {
    return (
      <Section title="Graph paths">
        <p className="text-stone-500">status: {g.status} · {g.paths_found} paths</p>
      </Section>
    );
  }
  return (
    <Section title={`Graph paths (${g.paths.length})`}>
      <ul className="space-y-2">
        {g.paths.map((p, i) => (
          <li key={i} className="rounded border border-stone-100 bg-stone-50 p-2 text-xs">
            <div className="font-mono text-stone-700">seed: {p.chunk_id}</div>
            <div className="mt-1 text-stone-600">path: {p.path.join(" → ")}</div>
            {p.relation_ids.length > 0 && (
              <div className="mt-1 text-stone-500">relations: {p.relation_ids.join(", ")}</div>
            )}
            {p.evidence_chunk_ids.length > 0 && (
              <div className="mt-1 text-stone-500">evidence: {p.evidence_chunk_ids.join(", ")}</div>
            )}
          </li>
        ))}
      </ul>
    </Section>
  );
}

function Community({ trace }: { trace: RetrievalTrace }) {
  const c = trace.community;
  return (
    <Section title="Community">
      <p className="text-stone-700">
        status: {c.status} · {c.report_ids.length} report{c.report_ids.length === 1 ? "" : "s"}
      </p>
      {c.report_ids.length > 0 && (
        <p className="mt-1 font-mono text-xs text-stone-500">{c.report_ids.join(", ")}</p>
      )}
    </Section>
  );
}

function MemorySection({ trace }: { trace: RetrievalTrace }) {
  const m = trace.memory;
  if (m.fact_ids.length === 0) {
    return (
      <Section title="Memory">
        <p className="text-stone-500">none</p>
      </Section>
    );
  }
  return (
    <Section title={`Memory (${m.fact_ids.length})`}>
      <div className="text-stone-700">
        <span className="text-xs text-stone-500">scopes: {m.scopes.join(", ")}</span>
        <ul className="mt-1 font-mono text-xs text-stone-600">
          {m.fact_ids.map((id, i) => (
            <li key={i}>{id}</li>
          ))}
        </ul>
      </div>
    </Section>
  );
}
