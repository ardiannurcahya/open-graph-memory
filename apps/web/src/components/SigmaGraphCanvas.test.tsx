import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "../theme";
import { buildCommunityPalette } from "../lib/colorPalette";
import { buildGraphState } from "../lib/graphPhysics";
import type { GraphState } from "../lib/graphTypes";

const graphOptions: unknown[] = [];
const edgeKeys: string[] = [];
let sigmaSettings: { nodeReducer?: (node: string, data: Record<string, unknown>) => Record<string, unknown> } | null = null;

vi.mock("sigma", () => {
  class FakeSigma {
    constructor(_graph: unknown, _container: unknown, settings: typeof sigmaSettings) { sigmaSettings = settings; }
    graph = { forEachNode: () => undefined, forEachEdge: () => undefined, source: () => "n0", target: () => "n1", getNodeAttribute: (_node: string, attribute: string) => attribute === "community" ? "c0" : false, order: 2 };
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
    constructor(options?: unknown) { graphOptions.push(options); }
    addNode() {}
    addEdgeWithKey(key: string) { edgeKeys.push(key); }
    hasNode() { return true; }
    setNodeAttribute() {}
    setEdgeAttribute() {}
    getNodeAttribute(_node: string, attribute: string) { return attribute === "community" ? "c0" : false; }
    getEdgeAttributes() { return { isExpired: false }; }
    source() { return "n0"; }
    target() { return "n1"; }
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

const sampleNodes = [
  { id: "n0", label: "Alice", type: "person", community: "c0", description: "desc" },
  { id: "n1", label: "Bob", type: "person", community: "c0", description: "desc" },
];

const sampleEdges = [
  { id: "e0", source: "n0", target: "n1", label: "knows", weight: 2 },
];

const parallelEdges = [
  ...sampleEdges,
  { id: "e1", source: "n0", target: "n1", label: "works-with", weight: 1 },
];

function makeState(edges = sampleEdges): GraphState {
  return buildGraphState(sampleNodes, edges, buildCommunityPalette(["c0"]));
}

function renderCanvas(state = makeState()) {
  return render(
    <ThemeProvider>
      <MemoryRouter>
        <SigmaGraphCanvas
          state={state}
          physicsEnabled={true}
          showLabels={true}
          activeFilters={new Set()}
          selectedNodeId={null}
          onNodeSelect={() => undefined}
        />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

import SigmaGraphCanvas from "./SigmaGraphCanvas";

describe("SigmaGraphCanvas", () => {
  beforeEach(() => {
    graphOptions.length = 0;
    edgeKeys.length = 0;
    sigmaSettings = null;
    vi.stubGlobal("requestAnimationFrame", vi.fn((cb: () => void) => { cb(); return 0; }));
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mounts the graph-canvas container with sigma renderer marker", () => {
    renderCanvas();
    const container = document.getElementById("graph-canvas");
    expect(container).not.toBeNull();
    expect(container?.getAttribute("data-renderer")).toBe("sigma");
  });

  it("does not show the loading overlay once mounted", () => {
    renderCanvas();
    expect(screen.queryByText("Computing layout…")).not.toBeInTheDocument();
  });

  it("preserves parallel relations in a multi graph with stable edge keys", () => {
    renderCanvas(makeState(parallelEdges));

    expect(graphOptions).toContainEqual({ multi: true });
    expect(edgeKeys).toEqual(["e0", "e1"]);
  });

  it("preserves node positions in Sigma reducer output", () => {
    renderCanvas();

    const data = { x: 3, y: -2, community: "c0", color: "#111" };
    expect(sigmaSettings?.nodeReducer?.("n0", data)).toEqual(data);
  });

  it("cancels pending layout work when unmounted", () => {
    const cancelFrame = vi.fn();
    vi.stubGlobal("requestAnimationFrame", vi.fn(() => 42));
    vi.stubGlobal("cancelAnimationFrame", cancelFrame);

    const { unmount } = renderCanvas();
    unmount();

    expect(cancelFrame).toHaveBeenCalledWith(42);
  });
});
