import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import GraphPage from "./GraphPage";
import { useAuthStore } from "../store/auth";
import { ThemeProvider } from "../theme";

vi.mock("sigma", () => {
  class FakeSigma {
    on() {}
    addListener() {}
    getCamera() { return { on() {}, getState: () => ({ ratio: 1 }), animatedReset: () => undefined }; }
    setSetting() {}
    setSettings() {}
    refresh() {}
    kill() {}
  }
  return { default: FakeSigma, Sigma: FakeSigma };
});

vi.mock("graphology", () => {
  class FakeGraph {
    addNode() {}
    addEdgeWithKey() {}
    hasNode() { return true; }
    setNodeAttribute() {}
    setEdgeAttribute() {}
    getNodeAttribute() { return "c0"; }
    source() { return "ent_a"; }
    target() { return "ent_b"; }
    forEachNode() {}
    forEachEdge() {}
    get order() { return 2; }
  }
  return { default: FakeGraph };
});

vi.mock("graphology-layout-forceatlas2", () => {
  const fn = () => ({});
  (fn as unknown as { assign: () => void }).assign = () => undefined;
  (fn as unknown as { inferSettings: () => unknown }).inferSettings = () => ({});
  return { default: fn };
});

const mockCtx = {
  getContext: vi.fn(() => ({})),
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

const secondDataset = { ...dataset, id: "ds_2", name: "Operations" };

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
  return render(<ThemeProvider><MemoryRouter><GraphPage /></MemoryRouter></ThemeProvider>);
}

async function selectDataset(expectedNodes = 2) {
  await waitFor(() => expect(screen.getByText("Research")).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("Dataset"), "ds_1");
  await waitFor(() => expect(screen.getByText(`${expectedNodes} nodes`)).toBeInTheDocument());
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
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mockCtx.getContext() as unknown as CanvasRenderingContext2D);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ apiKey: "", projectId: "", adminKey: "" });
  });

  it("loads explorer in graph playground", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/v1/datasets") return ok([dataset]);
      if (url.includes("/graph/explorer")) return ok(explorerView);
      return ok([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    expect(screen.getByText("Graph Playground")).toBeInTheDocument();
    await selectDataset();
    expect(screen.getByText("1 edges")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Entity search" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/datasets/ds_1/graph/explorer?community_level=0&node_limit=3000&relation_limit=5000",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("uses semantic inverse text for active amber tool", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/api/v1/datasets") return ok([dataset]);
      return ok([]);
    }));
    renderPage();
    await waitFor(() => expect(screen.getByRole("button", { name: "Entity search" })).toHaveClass("text-ui-inverse"));
  });

  it("preserves 2700 explorer nodes", async () => {
    const largeExplorerView = {
      ...explorerView,
      stats: { entity_count: 2700, relation_count: 0, density: 0 },
      nodes: Array.from({ length: 2700 }, (_, index) => ({
        id: `ent_${index}`,
        canonical_name: `Entity ${index}`,
        entity_type: "person",
        community_id: "c0",
        degree: 0,
        weighted_degree: 0,
        importance: 0,
      })),
      relations: [],
    };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/api/v1/datasets") return ok([dataset]);
      if (url.includes("/graph/explorer")) return ok(largeExplorerView);
      return ok([]);
    }));
    renderPage();
    await selectDataset(2700);
    expect(screen.getByText("2700 nodes")).toBeInTheDocument();
  });

  it("loads every node and relation when explorer response is truncated", async () => {
    const truncated = {
      ...explorerView,
      stats: { entity_count: 3, relation_count: 2, density: 0.67 },
      nodes: [explorerView.nodes[0]],
      relations: [explorerView.relations[0]],
    };
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/v1/datasets") return ok([dataset]);
      if (url.includes("/graph/explorer/nodes")) return ok({
        nodes: [
          explorerView.nodes[0],
          explorerView.nodes[1],
          { ...explorerView.nodes[0], id: "ent_c", canonical_name: "Carol" },
        ],
        next_cursor: null,
      });
      if (url.includes("/graph/explorer/relations")) return ok({
        relations: [
          explorerView.relations[0],
          { ...explorerView.relations[0], id: "rel_2", source: "ent_b", target: "ent_c" },
        ],
        next_cursor: null,
      });
      if (url.includes("/graph/explorer")) return ok(truncated);
      return ok([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await selectDataset(3);
    expect(screen.getByText("2 edges")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/datasets/ds_1/graph/explorer/nodes?limit=3000&community_level=0",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/datasets/ds_1/graph/explorer/relations?limit=5000",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("keeps latest explorer response when deferred requests resolve out of order", async () => {
    let resolveFirst: ((response: Response) => void) | undefined;
    let resolveSecond: ((response: Response) => void) | undefined;
    const first = new Promise<Response>((resolve) => { resolveFirst = resolve; });
    const second = new Promise<Response>((resolve) => { resolveSecond = resolve; });
    const fetchMock = vi.fn((url: string) => {
      if (url === "/api/v1/datasets") return Promise.resolve(ok([dataset, secondDataset]));
      if (url.includes("/datasets/ds_1/graph/explorer")) return first;
      if (url.includes("/datasets/ds_2/graph/explorer")) return second;
      return Promise.resolve(ok([]));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await waitFor(() => expect(screen.getByText("Operations")).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Dataset"), "ds_1");
    await userEvent.selectOptions(screen.getByLabelText("Dataset"), "ds_2");
    const latest = {
      ...explorerView,
      dataset_id: "ds_2",
      stats: { entity_count: 3, relation_count: 0, density: 0 },
      nodes: [...explorerView.nodes, { ...explorerView.nodes[0], id: "ent_c", canonical_name: "Carol" }],
      relations: [],
    };
    resolveSecond?.(ok(latest));
    await waitFor(() => expect(screen.getByText("3 nodes")).toBeInTheDocument());
    resolveFirst?.(ok(explorerView));
    await waitFor(() => expect(screen.getByText("3 nodes")).toBeInTheDocument());
    expect(screen.queryByText("2 nodes")).not.toBeInTheDocument();
  });

  it("resets community filters when explorer level replaces graph", async () => {
    const initial = {
      ...explorerView,
      nodes: [
        explorerView.nodes[0],
        { ...explorerView.nodes[1], community_id: "c1" },
      ],
      communities: [
        { ...explorerView.communities[0], id: "c0" },
        { ...explorerView.communities[0], id: "c1" },
      ],
    };
    const replacement = {
      ...initial,
      community_level: 1,
      nodes: initial.nodes.map((node) => ({ ...node, community_id: "c1" })),
      communities: [{ ...explorerView.communities[0], id: "c1" }],
    };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/api/v1/datasets") return ok([dataset]);
      if (url.includes("community_level=1")) return ok(replacement);
      if (url.includes("/graph/explorer")) return ok(initial);
      return ok([]);
    }));
    renderPage();
    await selectDataset();
    await userEvent.click(screen.getByRole("button", { name: "Filters" }));
    const c0 = screen.getByRole("button", { name: "c0" });
    await userEvent.click(c0);
    expect(c0).toHaveAttribute("aria-pressed", "true");
    await userEvent.selectOptions(screen.getByLabelText("Community level"), "1");
    await waitFor(() => expect(screen.getByRole("button", { name: "c1" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "c1" })).toHaveAttribute("data-active", "false");
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
