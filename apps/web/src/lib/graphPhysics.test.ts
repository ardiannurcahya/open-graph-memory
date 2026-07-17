import { describe, it, expect } from "vitest";
import {
  buildGraphState,
  highlightConnected,
} from "./graphPhysics";
import { buildCommunityPalette } from "./colorPalette";

const palette = buildCommunityPalette(["c0", "c1"]);

const sampleNodes = [
  { id: "n0", label: "Alice", type: "person", community: "c0", description: "desc" },
  { id: "n1", label: "Bob", type: "person", community: "c0", description: "desc" },
  { id: "n2", label: "Tech", type: "tech", community: "c1", description: "desc" },
];

const sampleEdges = [
  { id: "e0", source: "n0", target: "n1", label: "knows", weight: 3 },
  { id: "e1", source: "n0", target: "n2", label: "uses", weight: 2 },
];

describe("buildGraphState", () => {
  it("builds nodes with reduced degree-scaled radii", () => {
    const state = buildGraphState(sampleNodes, sampleEdges, palette);
    const n0 = state.nodes.find((n) => n.id === "n0");
    const n1 = state.nodes.find((n) => n.id === "n1");
    expect(n0?.degree).toBe(2);
    expect(n0?.degFrac).toBe(1);
    expect(n0?.radius).toBe(16.9);
    expect(n1?.radius).toBe(11.05);
    expect(n0?.radius).toBeGreaterThan(n1?.radius ?? 0);
    expect(state.maxDegree).toBe(2);
  });

  it("builds adjacency map with edges on both endpoints", () => {
    const state = buildGraphState(sampleNodes, sampleEdges, palette);
    expect(state.adj.get("n0")?.length).toBe(2);
    expect(state.adj.get("n1")?.length).toBe(1);
    expect(state.adj.get("n2")?.length).toBe(1);
  });

  it("canonicalizes parallel raw edges after reversal", () => {
    const edges = [
      { id: "", source: "n0", target: "n1", label: "knows", weight: 3 },
      { id: "", source: "n0", target: "n1", label: "knows", weight: 1 },
      { id: "", source: "n0", target: "n1", label: "knows", weight: 2 },
      { id: "same", source: "n0", target: "n1", label: "knows", weight: 2 },
    ];
    const first = buildGraphState(sampleNodes, edges, palette);
    const second = buildGraphState(sampleNodes, [...edges].reverse(), palette);
    expect(first.edges).toEqual(second.edges);
    expect(first.edges.map((edge) => [edge.id, edge.weight])).toEqual([
      ["edge_0", 1],
      ["edge_1", 2],
      ["edge_2", 3],
      ["same", 2],
    ]);
  });

  it("avoids generated edge ID collisions", () => {
    const state = buildGraphState(sampleNodes, [
      { id: "edge_0", source: "n0", target: "n1", label: "explicit", weight: 1 },
      { id: "", source: "n1", target: "n2", label: "generated", weight: 1 },
    ], palette);
    expect(new Set(state.edges.map((edge) => edge.id)).size).toBe(2);
  });
});

describe("highlightConnected", () => {
  it("returns 1-hop connected nodes and edges", () => {
    const state = buildGraphState(sampleNodes, sampleEdges, palette);
    const result = highlightConnected(state, "n0");
    expect(result.nodes.has("n0")).toBe(true);
    expect(result.nodes.has("n1")).toBe(true);
    expect(result.nodes.has("n2")).toBe(true);
    expect(result.edges.has("e0")).toBe(true);
    expect(result.edges.has("e1")).toBe(true);
  });

  it("only includes direct neighbors for a leaf node", () => {
    const state = buildGraphState(sampleNodes, sampleEdges, palette);
    const result = highlightConnected(state, "n1");
    expect(result.nodes.has("n1")).toBe(true);
    expect(result.nodes.has("n0")).toBe(true);
    expect(result.nodes.has("n2")).toBe(false);
  });
});
