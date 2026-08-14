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

describe("explorerToGraphState community set", () => {
  it("includes node community ids that are missing from the communities list", () => {
    const view = makeView({
      nodes: [
        {
          id: "e1",
          canonical_name: "Alice",
          entity_type: "person",
          community_id: "orphan",
          degree: 0,
          weighted_degree: 0,
          importance: 0,
        },
      ],
      communities: [],
    });
    const state = explorerToGraphState(view);
    expect(state.communities.has("orphan")).toBe(true);
    expect(state.nodes[0].community).toBe("orphan");
  });

  it("falls back to 'default' for nodes without a community id and includes it in the palette", () => {
    const view = makeView({
      nodes: [
        {
          id: "e1",
          canonical_name: "Alice",
          entity_type: "person",
          community_id: null,
          degree: 0,
          weighted_degree: 0,
          importance: 0,
        },
      ],
    });
    const state = explorerToGraphState(view);
    expect(state.nodes[0].community).toBe("default");
    expect(state.communities.has("default")).toBe(true);
  });

  it("deduplicates community ids shared between the communities list and node community ids", () => {
    const view = makeView({
      nodes: [
        {
          id: "e1",
          canonical_name: "Alice",
          entity_type: "person",
          community_id: "c0",
          degree: 0,
          weighted_degree: 0,
          importance: 0,
        },
        {
          id: "e2",
          canonical_name: "Bob",
          entity_type: "person",
          community_id: "c0",
          degree: 0,
          weighted_degree: 0,
          importance: 0,
        },
      ],
      communities: [
        {
          id: "c0",
          entity_count: 2,
          parent_id: null,
          child_ids: [],
          internal_edges: 0,
          external_edges: 0,
          density: 0,
          importance: 0,
        },
      ],
    });
    const state = explorerToGraphState(view);
    expect(state.communities.size).toBe(1);
    expect(state.communities.has("c0")).toBe(true);
  });

  it("builds a palette entry for every distinct community id referenced by nodes", () => {
    const view = makeView({
      nodes: [
        {
          id: "e1",
          canonical_name: "Alice",
          entity_type: "person",
          community_id: "c0",
          degree: 0,
          weighted_degree: 0,
          importance: 0,
        },
        {
          id: "e2",
          canonical_name: "Bob",
          entity_type: "person",
          community_id: "c1",
          degree: 0,
          weighted_degree: 0,
          importance: 0,
        },
      ],
      communities: [
        {
          id: "c0",
          entity_count: 1,
          parent_id: null,
          child_ids: [],
          internal_edges: 0,
          external_edges: 0,
          density: 0,
          importance: 0,
        },
      ],
    });
    const state = explorerToGraphState(view);
    expect(state.communities.size).toBe(2);
    expect(state.communities.has("c0")).toBe(true);
    expect(state.communities.has("c1")).toBe(true);
  });
});