import { describe, expect, it } from "vitest";

import { buildGraphModel, colorForCommunity, connectedNodeIds, initialPosition, nodeRadius } from "./graphModel";

const graph = { nodes: [{ id: "one", entity_type: "person", community_id: "alpha", degree: 4 }], relations: [] } as never;

describe("graphModel", () => {
  it("keeps community colors and initial positions stable", () => {
    expect(colorForCommunity("alpha")).toBe(colorForCommunity("alpha"));
    expect(initialPosition("one")).toEqual(initialPosition("one"));
    expect(nodeRadius(4, 2)).toBeGreaterThan(nodeRadius(4));
  });
  it("builds filtered model and finds neighbors", () => {
    expect(buildGraphModel(graph, { entityType: "person" }).nodes).toHaveLength(1);
    expect(connectedNodeIds([{ source: "one", target: "two" }], "one").has("two")).toBe(true);
  });
});
