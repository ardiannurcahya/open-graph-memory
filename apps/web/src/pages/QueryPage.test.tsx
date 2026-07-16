import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import QueryPage from "./QueryPage";
import { useAuthStore } from "../store/auth";

function ok(body: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

const dataset = {
  id: "ds_1",
  project_id: "p",
  name: "Research",
  description: null,
  status: "active",
  error_message: null,
  metadata: {},
};

const queryResponse = {
  answer: "The document states recovery takes 4 weeks [1].",
  citations: [
    {
      index: 1,
      chunk_id: "chk_1",
      document_id: "doc_1",
      score: 0.9,
      text: "Recovery takes 4 weeks.",
      source_location: { page_number: 3 },
    },
  ],
  retrieval_trace: {
    trace_id: "t1",
    mode: "hybrid",
    requested_mode: "hybrid",
    resolved_mode: "hybrid",
    intent: "local",
    channel_candidates: { vector: [], graph: [], community: [] },
    fusion: [],
    graph: { status: "ok", paths_found: 0, evidence_chunk_ids: 0, hydrated_chunks: 0, missing_chunks: 0, paths: [] },
    community: { status: "not_requested", report_ids: [] },
    chunk_ids: ["chk_1"],
    scores: [0.9],
    timings_ms: { vector: 5, graph: 0, hydrate: 0, generation: 10 },
    memory: { fact_ids: [], scopes: [], source_message_ids: [] },
    latency_ms: 15,
  },
  usage: { prompt_tokens: 100, completion_tokens: 20, total_tokens: 120, estimated_cost_usd: 0.001 },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <QueryPage />
    </MemoryRouter>,
  );
}

describe("QueryPage", () => {
  beforeEach(() => {
    useAuthStore.setState({
      apiKey: "ogm_key",
      projectId: "11111111-2222-3333-4444-555555555555",
      adminKey: "",
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ apiKey: "", projectId: "", adminKey: "" });
  });

  it("loads datasets into the selector", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/v1/datasets") return ok([dataset]);
      return ok([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await waitFor(() => expect(screen.getByText("Research")).toBeInTheDocument());
  });

  it("runs a sync query and shows answer with citation", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/datasets") return ok([dataset]);
      if (url === "/api/v1/query" && init?.method === "POST") return ok(queryResponse);
      return ok([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await waitFor(() => expect(screen.getByText("Research")).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByDisplayValue("Select dataset…"), "ds_1");
    await userEvent.type(screen.getByPlaceholderText(/Ask a question/), "How long is recovery?");
    // Disable streaming to exercise the sync path.
    await userEvent.click(screen.getByLabelText("Stream tokens"));
    await userEvent.click(screen.getByRole("button", { name: "Run Query" }));
    await waitFor(() =>
      expect(screen.getByText("The document states recovery takes 4 weeks [1].")).toBeInTheDocument(),
    );
    expect(screen.getByText("Recovery takes 4 weeks.")).toBeInTheDocument();
    expect(screen.getByText(/page_number=3/)).toBeInTheDocument();
  });
});
