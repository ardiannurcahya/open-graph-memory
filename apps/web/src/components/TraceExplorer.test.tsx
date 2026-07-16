import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TraceExplorer } from "./TraceExplorer";
import type { QueryResponse } from "../api/types";

const response: QueryResponse = {
  answer: "answer [1]",
  citations: [],
  retrieval_trace: {
    trace_id: "trace_abc",
    mode: "hybrid",
    requested_mode: "hybrid",
    resolved_mode: "graph_local",
    intent: "local",
    channel_candidates: {
      vector: [{ chunk_id: "chk_v1", score: 0.8 }],
      graph: [{ chunk_id: "chk_g1", score: 0.6 }],
      community: [],
    },
    fusion: [{ fused: true }],
    graph: {
      status: "ok",
      paths_found: 1,
      evidence_chunk_ids: 1,
      hydrated_chunks: 1,
      missing_chunks: 0,
      paths: [
        {
          chunk_id: "chk_seed",
          path: ["ent_a", "ent_b"],
          relation_ids: ["rel_1"],
          evidence_chunk_ids: ["chk_ev"],
        },
      ],
    },
    community: { status: "unavailable", report_ids: [] },
    chunk_ids: ["chk_v1"],
    scores: [0.8],
    timings_ms: { vector: 5, graph: 12, hydrate: 3, generation: 20 },
    memory: { fact_ids: ["mem_1"], scopes: ["user"], source_message_ids: ["msg_1"] },
    latency_ms: 40,
  },
  usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15, estimated_cost_usd: 0 },
};

describe("TraceExplorer", () => {
  it("renders summary in collapsed header", () => {
    render(<TraceExplorer response={response} />);
    expect(screen.getByText("graph_local · 40ms · show")).toBeInTheDocument();
  });

  it("expands to show trace details", async () => {
    render(<TraceExplorer response={response} />);
    await userEvent.click(screen.getByText("Retrieval Trace"));
    expect(screen.getByText("trace_abc")).toBeInTheDocument();
    expect(screen.getByText("chk_v1:0.80")).toBeInTheDocument();
    expect(screen.getByText("seed: chk_seed")).toBeInTheDocument();
    expect(screen.getByText(/path: ent_a → ent_b/)).toBeInTheDocument();
    expect(screen.getByText(/mem_1/)).toBeInTheDocument();
  });

  it("handles empty graph paths", async () => {
    const empty: QueryResponse = {
      ...response,
      retrieval_trace: {
        ...response.retrieval_trace,
        graph: { status: "not_requested", paths_found: 0, evidence_chunk_ids: 0, hydrated_chunks: 0, missing_chunks: 0, paths: [] },
        memory: { fact_ids: [], scopes: [], source_message_ids: [] },
      },
    };
    render(<TraceExplorer response={empty} />);
    await userEvent.click(screen.getByText("Retrieval Trace"));
    expect(screen.getByText(/status: not_requested · 0 paths/)).toBeInTheDocument();
    expect(screen.getByText("none")).toBeInTheDocument();
  });
});
