import { describe, it, expect } from "vitest";
import { explorerToGraphState } from "./graphMapping";
import type { ExplorerView } from "../api/types";

function makeView(overrides: Partial<ExplorerView> = {}): ExplorerView {
  return {
    dataset_id: "ds_1",
    community_level: 0,
    available_levels: [0],
    analytics: null,
    refresh_required: false,
    stats: { entity_count: 0, relation_count: 0, density: 0 },
    nodes: [],
    relations: [],
    communities: [],
    ...overrides,
  };
}

function makeNode(overrides: Partial<ExplorerView["nodes"][number]> = {}): ExplorerView["nodes"][number] {
  return {
    id: "ent_a",
    canonical_name: "Alice",
    entity_type: "person",
    community_id: "c0",
    degree: 1,
    weighted_degree: 1,
    importance: 0.5,
    ...overrides,
  };
}

describe("explorerToGraphState", () => {
  it("includes communities referenced only by nodes, not declared in view.communities", () => {
    const view = makeView({
      nodes: [makeNode({ id: "ent_a", community_id: "c1" })],
      communities: [],
    });
    const state = explorerToGraphState(view);
    expect(state.communities.has("c1")).toBe(true);
  });

  it("unions communities from the communities array and from node community ids", () => {
    const view = makeView({
      nodes: [
        makeNode({ id: "ent_a", community_id: "c0" }),
        makeNode({ id: "ent_b", community_id: "c1" }),
      ],
      communities: [
        { id: "c0", entity_count: 1, parent_id: null, child_ids: [], internal_edges: 0, external_edges: 0, density: 0, importance: 0.5 },
      ],
    });
    const state = explorerToGraphState(view);
    expect(state.communities.has("c0")).toBe(true);
    expect(state.communities.has("c1")).toBe(true);
    expect(state.communities.size).toBe(2);
  });

  it("does not duplicate a community id present in both nodes and the communities array", () => {
    const view = makeView({
      nodes: [
        makeNode({ id: "ent_a", community_id: "c0" }),
        makeNode({ id: "ent_b", community_id: "c0" }),
      ],
      communities: [
        { id: "c0", entity_count: 2, parent_id: null, child_ids: [], internal_edges: 1, external_edges: 0, density: 1, importance: 0.5 },
      ],
    });
    const state = explorerToGraphState(view);
    expect(state.communities.size).toBe(1);
  });

  it("falls back to 'default' community for nodes with a null community_id", () => {
    const view = makeView({
      nodes: [makeNode({ id: "ent_a", community_id: null })],
      communities: [],
    });
    const state = explorerToGraphState(view);
    expect(state.communities.has("default")).toBe(true);
    const node = state.nodes.find((n) => n.id === "ent_a");
    expect(node?.community).toBe("default");
  });

  it("uses the 'default' community when there are no nodes and no communities", () => {
    const view = makeView({ nodes: [], communities: [] });
    const state = explorerToGraphState(view);
    expect(state.communities.has("default")).toBe(true);
    expect(state.nodes).toHaveLength(0);
  });

  it("maps node and relation fields onto graph state", () => {
    const view = makeView({
      nodes: [
        makeNode({ id: "ent_a", canonical_name: "Alice", entity_type: "person", community_id: "c0", degree: 2, importance: 0.75 }),
      ],
      relations: [{ id: "rel_1", source: "ent_a", target: "ent_a", type: "self", weight: 1, confidence: 1 }],
      communities: [
        { id: "c0", entity_count: 1, parent_id: null, child_ids: [], internal_edges: 0, external_edges: 0, density: 0, importance: 0.5 },
      ],
    });
    const state = explorerToGraphState(view);
    const node = state.nodes.find((n) => n.id === "ent_a");
    expect(node?.label).toBe("Alice");
    expect(node?.type).toBe("person");
    expect(node?.community).toBe("c0");
    expect(node?.description).toContain("person");
    expect(node?.description).toContain("degree 2");
    expect(node?.description).toContain("importance 0.75");
    expect(state.edges).toHaveLength(1);
    expect(state.edges[0].label).toBe("self");
  });
});