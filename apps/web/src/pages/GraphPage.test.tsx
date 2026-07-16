import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import GraphPage from "./GraphPage";
import { useAuthStore } from "../store/auth";

// Mock canvas getContext — jsdom doesn't implement Canvas 2D
const mockCtx = {
  canvas: { width: 800, height: 600 },
  clearRect: vi.fn(),
  fillRect: vi.fn(),
  beginPath: vi.fn(),
  arc: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  quadraticCurveTo: vi.fn(),
  closePath: vi.fn(),
  fill: vi.fn(),
  stroke: vi.fn(),
  save: vi.fn(),
  restore: vi.fn(),
  translate: vi.fn(),
  scale: vi.fn(),
  createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
  setLineDash: vi.fn(),
  fillText: vi.fn(),
  set fillStyle(_v: unknown) { /* noop */ },
  get fillStyle() { return ""; },
  set strokeStyle(_v: unknown) { /* noop */ },
  get strokeStyle() { return ""; },
  set lineWidth(_v: unknown) { /* noop */ },
  get lineWidth() { return 1; },
  set shadowColor(_v: unknown) { /* noop */ },
  get shadowColor() { return ""; },
  set shadowBlur(_v: unknown) { /* noop */ },
  get shadowBlur() { return 0; },
  set font(_v: unknown) { /* noop */ },
  get font() { return ""; },
  set textAlign(_v: unknown) { /* noop */ },
  get textAlign() { return "start"; },
  set textBaseline(_v: unknown) { /* noop */ },
  get textBaseline() { return "alphabetic"; },
};

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

const explorerView = {
  dataset_id: "ds_1",
  community_level: 0,
  available_levels: [0, 1, 2],
  analytics: {
    id: "run_1",
    dataset_id: "ds_1",
    snapshot_hash: "h",
    entity_count: 2,
    relation_count: 1,
    community_count: 1,
    levels: 3,
    algorithm_version: "louvain-v1",
    created_at: "t",
    stale: false,
  },
  refresh_required: false,
  stats: { entity_count: 2, relation_count: 1, density: 1.0 },
  nodes: [
    { id: "ent_a", canonical_name: "Alice", entity_type: "person", community_id: "c0", degree: 1, weighted_degree: 1.0, importance: 0.5 },
    { id: "ent_b", canonical_name: "Bob", entity_type: "person", community_id: "c0", degree: 1, weighted_degree: 1.0, importance: 0.5 },
  ],
  relations: [
    { id: "rel_1", source: "ent_a", target: "ent_b", type: "knows", weight: 0.9, confidence: 0.9 },
  ],
  communities: [{ id: "c0", entity_count: 2, parent_id: null, child_ids: [], internal_edges: 1, external_edges: 0, density: 1.0, importance: 0.5 }],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <GraphPage />
    </MemoryRouter>,
  );
}

describe("GraphPage", () => {
  beforeEach(() => {
    useAuthStore.setState({
      apiKey: "ogm_key",
      projectId: "11111111-2222-3333-4444-555555555555",
      adminKey: "",
    });
    // Mock canvas context
    vi.stubGlobal("requestAnimationFrame", vi.fn(() => 0));
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    const origGetContext = HTMLCanvasElement.prototype.getContext;
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mockCtx as unknown as CanvasRenderingContext2D);
    void origGetContext;
  });

  afterEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ apiKey: "", projectId: "", adminKey: "" });
  });

  it("renders dataset selector", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/v1/datasets") return ok([dataset]);
        if (url.includes("/graph/explorer")) return ok(explorerView);
        return ok([]);
      }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("Research")).toBeInTheDocument());
  });

  it("loads explorer and shows stats", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/v1/datasets") return ok([dataset]);
        if (url.includes("/graph/explorer")) return ok(explorerView);
        return ok([]);
      }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("Research")).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByDisplayValue("Select dataset…"), "ds_1");
    await waitFor(() => expect(screen.getByText(/nodes/)).toBeInTheDocument());
    expect(screen.getByText(/edges/)).toBeInTheDocument();
    expect(screen.getByText(/communities/)).toBeInTheDocument();
  });

  it("shows density stat", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/v1/datasets") return ok([dataset]);
        if (url.includes("/graph/explorer")) return ok(explorerView);
        return ok([]);
      }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("Research")).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByDisplayValue("Select dataset…"), "ds_1");
    await waitFor(() => expect(screen.getByText(/density 1\.000/)).toBeInTheDocument());
  });

  it("refreshes analytics", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/datasets") return ok([dataset]);
      if (url.includes("/graph/explorer")) return ok(explorerView);
      if (url.includes("/analytics/refresh") && init?.method === "POST")
        return ok({ id: "run_2", dataset_id: "ds_1", snapshot_hash: "h2", entity_count: 2, relation_count: 1, community_count: 1, levels: 3, algorithm_version: "louvain-v1" });
      return ok([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await waitFor(() => expect(screen.getByText("Research")).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByDisplayValue("Select dataset…"), "ds_1");
    await waitFor(() => expect(screen.getByText(/nodes/)).toBeInTheDocument());
    await userEvent.click(screen.getByText("↻"));
    await waitFor(() => {
      const refreshCalls = fetchMock.mock.calls.filter(
        ([u, i]) => String(u).includes("/analytics/refresh") && (i as RequestInit)?.method === "POST",
      );
      expect(refreshCalls.length).toBeGreaterThan(0);
    });
  });
});
