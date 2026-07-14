import { describe, expect, it } from "vitest";

import {
  KNOWLEDGE_NODE_GAP,
  knowledgeNodeSize,
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
    expect(knowledgeNodeSize(0)).toBe(76);
    expect(knowledgeNodeSize(1)).toBe(83);
    expect(knowledgeNodeSize(5)).toBe(111);
    expect(knowledgeNodeSize(6)).toBe(116);
    expect(knowledgeNodeSize(100)).toBe(116);
  });

  it("produces deterministic positions", () => {
    const nodes = Array.from({ length: 24 }, (_, index) => ({
      id: String(index),
      data: { degree: 2 },
    }));
    expect(layoutKnowledgeNodes(nodes, false)).toEqual(layoutKnowledgeNodes(nodes, false));
  });
});
