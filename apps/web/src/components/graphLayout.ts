export const KNOWLEDGE_NODE_GAP = 16;

const CENTER_X = 450;
const CENTER_Y = 260;
const MAX_NODE_SIZE = 116;
const FIRST_RING_RADIUS = 150;
const RING_STEP = MAX_NODE_SIZE + KNOWLEDGE_NODE_GAP;

interface LayoutNode {
  data: { degree: number };
}

export function knowledgeNodeSize(degree: number): number {
  return Math.min(MAX_NODE_SIZE, 76 + degree * 7);
}

function ringCapacity(radius: number): number {
  const ratio = RING_STEP / (2 * radius);
  if (ratio >= 1) return 1;
  return Math.max(1, Math.floor(Math.PI / Math.asin(ratio)));
}

export function layoutKnowledgeNodes<T extends LayoutNode>(
  nodes: T[],
  hasHub: boolean,
): Array<T & { position: { x: number; y: number } }> {
  if (nodes.length === 0) return [];

  const positioned: Array<T & { position: { x: number; y: number } }> = [];
  let offset = 0;
  if (hasHub) {
    const hub = nodes[0];
    const size = knowledgeNodeSize(hub.data.degree);
    positioned.push({
      ...hub,
      position: { x: CENTER_X - size / 2, y: CENTER_Y - size / 2 },
    });
    offset = 1;
  }

  let radius = FIRST_RING_RADIUS;
  while (offset < nodes.length) {
    const count = Math.min(ringCapacity(radius), nodes.length - offset);
    for (let slot = 0; slot < count; slot += 1) {
      const node = nodes[offset + slot];
      const size = knowledgeNodeSize(node.data.degree);
      const angle = (slot / count) * Math.PI * 2 - Math.PI / 2;
      positioned.push({
        ...node,
        position: {
          x: CENTER_X + Math.cos(angle) * radius - size / 2,
          y: CENTER_Y + Math.sin(angle) * radius - size / 2,
        },
      });
    }
    offset += count;
    radius += RING_STEP;
  }

  return positioned;
}
