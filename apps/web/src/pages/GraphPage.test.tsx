import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import GraphPage from "./GraphPage";
import { useAuthStore } from "../store/auth";

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
  set fillStyle(_value: unknown) {},
  get fillStyle() { return ""; },
  set strokeStyle(_value: unknown) {},
  get strokeStyle() { return ""; },
  set lineWidth(_value: unknown) {},
  get lineWidth() { return 1; },
  set shadowColor(_value: unknown) {},
  get shadowColor() { return ""; },
  set shadowBlur(_value: unknown) {},
  get shadowBlur() { return 0; },
  set font(_value: unknown) {},
  get font() { return ""; },
  set textAlign(_value: unknown) {},
  get textAlign() { return "start"; },
  set textBaseline(_value: unknown) {},
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

const alice = {
  id: "ent_a",
  dataset_id: "ds_1",
  canonical_name: "Alice",
  entity_type: "person",
  confidence: 0.9,
  version: 1,
  review_state: "approved",
};

const bob = { ...alice, id: "ent_b", canonical_name: "Bob" };

const relation = {
  id: "rel_1",
  dataset_id: "ds_1",
  source_entity_id: "ent_a",
  target_entity_id: "ent_b",
  relation_type: "knows",
  confidence: 0.9,
  extractor_version: "v1",
  review_state: "approved",
  citations: [],
};

const explorerView = {
  dataset_id: "ds_1",
  community_level: 0,
  available_levels: [0, 1],
  analytics: null,
  refresh_required: false,
  stats: { entity_count: 2, relation_count: 1, density: 1 },
  nodes: [
    { id: "ent_a", canonical_name: "Alice", entity_type: "person", community_id: "c0", degree: 1, weighted_degree: 1, importance: 0.5 },
    { id: "ent_b", canonical_name: "Bob", entity_type: "person", community_id: "c0", degree: 1, weighted_degree: 1, importance: 0.5 },
  ],
  relations: [{ id: "rel_1", source: "ent_a", target: "ent_b", type: "knows", weight: 0.9, confidence: 0.9 }],
  communities: [{ id: "c0", entity_count: 2, parent_id: null, child_ids: [], internal_edges: 1, external_edges: 0, density: 1, importance: 0.5 }],
};

function renderPage() {
  return render(<MemoryRouter><GraphPage /></MemoryRouter>);
}

async function selectDataset() {
  await waitFor(() => expect(screen.getByText("Research")).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("Dataset"), "ds_1");
  await waitFor(() => expect(screen.getByText("2 nodes")).toBeInTheDocument());
}

describe("GraphPage", () => {
  beforeEach(() => {
    useAuthStore.setState({
      apiKey: "ogm_key",
      projectId: "11111111-2222-3333-4444-555555555555",
      adminKey: "",
    });
    vi.stubGlobal("requestAnimationFrame", vi.fn(() => 0));
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mockCtx as unknown as CanvasRenderingContext2D);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ apiKey: "", projectId: "", adminKey: "" });
  });

  it("loads explorer in graph playground", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/api/v1/datasets") return ok([dataset]);
      if (url.includes("/graph/explorer")) return ok(explorerView);
      return ok([]);
    }));
    renderPage();
    expect(screen.getByText("Graph Playground")).toBeInTheDocument();
    await selectDataset();
    expect(screen.getByText("1 edges")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Entity search" })).toBeInTheDocument();
  });

  it("searches entities and sends structured parameters", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/v1/datasets") return ok([dataset]);
      if (url.includes("/graph/explorer")) return ok(explorerView);
      if (url === "/api/v1/datasets/ds_1/entities/search?q=Alice&limit=25") return ok([alice]);
      return ok([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await selectDataset();
    await userEvent.type(screen.getByLabelText("Entity name"), "Alice");
    await userEvent.click(screen.getByRole("button", { name: "Run Entity search" }));
    await waitFor(() => expect(screen.getByText("person · ent_a")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/datasets/ds_1/entities/search?q=Alice&limit=25",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("loads neighbors into existing visualizer", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/v1/datasets") return ok([dataset]);
      if (url.includes("/graph/explorer")) return ok(explorerView);
      if (url === "/api/v1/entities/ent_a") return ok(alice);
      if (url === "/api/v1/entities/ent_a/neighbors?limit=25") return ok([{ entity: bob, relation }]);
      return ok([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await selectDataset();
    await userEvent.click(screen.getByRole("button", { name: "Neighbors" }));
    await userEvent.type(screen.getByLabelText("Entity ID"), "ent_a");
    await userEvent.click(screen.getByRole("button", { name: "Run Neighbors" }));
    await waitFor(() => expect(screen.getByText("2 nodes")).toBeInTheDocument());
    expect(screen.getByText("1 edges")).toBeInTheDocument();
  });

  it("loads a structured subgraph into existing visualizer", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/v1/datasets") return ok([dataset]);
      if (url.includes("/graph/explorer")) return ok(explorerView);
      if (url === "/api/v1/datasets/ds_1/graph/subgraph?entity_id=ent_a&depth=2&node_limit=100&relation_limit=200") {
        return ok({
          dataset_id: "ds_1",
          root_entity_id: "ent_a",
          depth: 2,
          nodes: [alice, bob],
          relations: [relation],
        });
      }
      return ok([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await selectDataset();
    await userEvent.click(screen.getByRole("button", { name: "Subgraph" }));
    await userEvent.type(screen.getByLabelText("Entity ID"), "ent_a");
    await userEvent.clear(screen.getByLabelText("Max depth"));
    await userEvent.type(screen.getByLabelText("Max depth"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Run Subgraph" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/datasets/ds_1/graph/subgraph?entity_id=ent_a&depth=2&node_limit=100&relation_limit=200",
      expect.objectContaining({ method: "GET" }),
    ));
    expect(screen.getByText("2 nodes")).toBeInTheDocument();
    expect(screen.getByText("1 edges")).toBeInTheDocument();
  });

  it("requests path and relation evidence and exposes raw JSON", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/v1/datasets") return ok([dataset]);
      if (url.includes("/graph/explorer")) return ok(explorerView);
      if (url === "/api/v1/datasets/ds_1/graph/path?source_entity_id=ent_a&target_entity_id=ent_b&max_depth=1&relation_limit=100") return ok({
        dataset_id: "ds_1",
        source_entity_id: "ent_a",
        target_entity_id: "ent_b",
        found: true,
        hops: 1,
        nodes: [alice, bob],
        relations: [relation],
      });
      if (url === "/api/v1/datasets/ds_1/relations/rel_1/evidence?limit=25") return ok([{ id: "ev_1", quote: "Alice knows Bob." }]);
      return ok([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await selectDataset();
    await userEvent.click(screen.getByRole("button", { name: "Path" }));
    await userEvent.type(screen.getByLabelText("Source entity ID"), "ent_a");
    await userEvent.type(screen.getByLabelText("Target entity ID"), "ent_b");
    await userEvent.click(screen.getByRole("button", { name: "Run Path" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/datasets/ds_1/graph/path?source_entity_id=ent_a&target_entity_id=ent_b&max_depth=1&relation_limit=100",
      expect.objectContaining({ method: "GET" }),
    ));
    await userEvent.click(screen.getByRole("button", { name: "Relation evidence" }));
    await userEvent.type(screen.getByLabelText("Relation ID"), "rel_1");
    await userEvent.click(screen.getByRole("button", { name: "Run Relation evidence" }));
    await waitFor(() => expect(screen.getByLabelText("Raw JSON result")).toHaveTextContent("Alice knows Bob."));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/datasets/ds_1/relations/rel_1/evidence?limit=25",
      expect.objectContaining({ method: "GET" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Raw JSON" }));
    expect(screen.getByLabelText("Raw JSON result")).toHaveTextContent("ev_1");
  });
});
