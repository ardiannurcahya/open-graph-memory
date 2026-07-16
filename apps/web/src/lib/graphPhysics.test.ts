import { describe, it, expect } from "vitest";
import {
  buildGraphState,
  physicsStep,
  fitAll,
  highlightConnected,
  DEFAULT_PHYSICS,
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
  it("builds nodes with computed degree and radius", () => {
    const state = buildGraphState(sampleNodes, sampleEdges, palette);
    const n0 = state.nodes.find((n) => n.id === "n0");
    expect(n0?.degree).toBe(2);
    expect(n0?.degFrac).toBe(1);
    expect(n0?.radius).toBeGreaterThan(8);
    expect(state.maxDegree).toBe(2);
  });

  it("builds adjacency map with edges on both endpoints", () => {
    const state = buildGraphState(sampleNodes, sampleEdges, palette);
    expect(state.adj.get("n0")?.length).toBe(2);
    expect(state.adj.get("n1")?.length).toBe(1);
    expect(state.adj.get("n2")?.length).toBe(1);
  });

  it("assigns particles to edges", () => {
    const state = buildGraphState(sampleNodes, sampleEdges, palette);
    expect(state.edges[0].particles.length).toBe(3);
    expect(state.edges[0].particles.every((p) => p >= 0 && p < 1)).toBe(true);
  });
});

describe("physicsStep", () => {
  it("moves nodes when physics applied", () => {
    const state = buildGraphState(sampleNodes, sampleEdges, palette);
    const before = state.nodes.map((n) => ({ x: n.x, y: n.y }));
    physicsStep(state, DEFAULT_PHYSICS, null);
    const after = state.nodes.map((n) => ({ x: n.x, y: n.y }));
    const moved = after.some((p, i) => p.x !== before[i].x || p.y !== before[i].y);
    expect(moved).toBe(true);
  });

  it("does not move dragged node", () => {
    const state = buildGraphState(sampleNodes, sampleEdges, palette);
    const n0 = state.nodes.find((n) => n.id === "n0")!;
    const beforeX = n0.x;
    const beforeY = n0.y;
    physicsStep(state, DEFAULT_PHYSICS, "n0");
    expect(n0.x).toBe(beforeX);
    expect(n0.y).toBe(beforeY);
  });
});

describe("fitAll", () => {
  it("computes camera that fits all nodes", () => {
    const state = buildGraphState(sampleNodes, sampleEdges, palette);
    const cam = fitAll(state.nodes, 800, 600, 1);
    expect(cam.zoom).toBeGreaterThan(0.12);
    expect(cam.zoom).toBeLessThanOrEqual(3);
  });

  it("returns default camera for empty node list", () => {
    const cam = fitAll([], 800, 600, 1);
    expect(cam).toEqual({ x: 0, y: 0, zoom: 1 });
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
