import { describe, expect, it } from "vitest";

import {
  KNOWLEDGE_NODE_GAP,
  knowledgeNodeSize,
  layoutKnowledgeBubbles,
  layoutKnowledgeNodes,
} from "./graphLayout";

describe("knowledge graph layout", () => {
  it("keeps dense graphs from overlapping", () => {
    const nodes = Array.from({ length: 100 }, (_, index) => ({
      id: `node-${index}`,
      data: { degree: index % 9 },
    }));
    const positioned = layoutKnowledgeNodes(nodes, true);

    for (let left = 0; left < positioned.length; left += 1) {
      for (let right = left + 1; right < positioned.length; right += 1) {
        const a = positioned[left];
        const b = positioned[right];
        const sizeA = knowledgeNodeSize(a.data.degree);
        const sizeB = knowledgeNodeSize(b.data.degree);
        const centerAx = a.position.x + sizeA / 2;
        const centerAy = a.position.y + sizeA / 2;
        const centerBx = b.position.x + sizeB / 2;
        const centerBy = b.position.y + sizeB / 2;
        const distance = Math.hypot(centerAx - centerBx, centerAy - centerBy);

        expect(distance + 1e-6).toBeGreaterThanOrEqual(
          sizeA / 2 + sizeB / 2 + KNOWLEDGE_NODE_GAP,
        );
      }
    }
  });

  it("uses stable bounded node sizes", () => {
    expect(knowledgeNodeSize(0)).toBe(64);
    expect(knowledgeNodeSize(1)).toBe(82);
    expect(knowledgeNodeSize(5)).toBeCloseTo(104.25, 2);
    expect(knowledgeNodeSize(6)).toBeCloseTo(108.09, 2);
    expect(knowledgeNodeSize(100)).toBe(172);
  });

  it("produces deterministic positions", () => {
    const nodes = Array.from({ length: 24 }, (_, index) => ({
      id: String(index),
      data: { degree: 2 },
    }));
    expect(layoutKnowledgeNodes(nodes, false)).toEqual(layoutKnowledgeNodes(nodes, false));
  });

  it("packs degree-sized bubbles without group wrappers", () => {
    const nodes = [
      { id: "person", data: { degree: 4, entityType: "Person", color: "#8b9cff" } },
      { id: "skill", data: { degree: 2, entityType: "Skill", color: "#55d6be" } },
      { id: "tool", data: { degree: 1, entityType: "Skill", color: "#55d6be" } },
    ];

    const layout = layoutKnowledgeBubbles(nodes);

    expect(layout.nodes).toHaveLength(3);
    expect(layout.bubbles).toEqual([]);
    expect(layout.nodes[0].id).toBe("person");
    expect(knowledgeNodeSize(layout.nodes[0].data.degree)).toBeGreaterThan(
      knowledgeNodeSize(layout.nodes[1].data.degree),
    );
  });
});
