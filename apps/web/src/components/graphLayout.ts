export const KNOWLEDGE_NODE_GAP = 16;

const CENTER_X = 450;
const CENTER_Y = 260;
const MAX_NODE_SIZE = 116;
const FIRST_RING_RADIUS = 150;
const RING_STEP = MAX_NODE_SIZE + KNOWLEDGE_NODE_GAP;
const BUBBLE_CELL_WIDTH = 420;
const BUBBLE_CELL_HEIGHT = 340;
const BUBBLE_PADDING = 72;

interface LayoutNode {
  data: { degree: number; entityType?: string; color?: string };
}

export interface KnowledgeBubble {
  id: string;
  label: string;
  count: number;
  color: string;
  position: { x: number; y: number };
  width: number;
  height: number;
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


function clusterCenter(index: number, total: number): { x: number; y: number } {
  if (total <= 1) return { x: CENTER_X, y: CENTER_Y };
  const columns = Math.ceil(Math.sqrt(total));
  const row = Math.floor(index / columns);
  const column = index % columns;
  const rows = Math.ceil(total / columns);
  return {
    x: CENTER_X + (column - (columns - 1) / 2) * BUBBLE_CELL_WIDTH,
    y: CENTER_Y + (row - (rows - 1) / 2) * BUBBLE_CELL_HEIGHT,
  };
}


function layoutCluster<T extends LayoutNode>(
  nodes: T[],
  center: { x: number; y: number },
): Array<T & { position: { x: number; y: number } }> {
  const positioned: Array<T & { position: { x: number; y: number } }> = [];
  if (nodes.length === 1) {
    const size = knowledgeNodeSize(nodes[0].data.degree);
    return [{ ...nodes[0], position: { x: center.x - size / 2, y: center.y - size / 2 } }];
  }
  let offset = 0;
  let radius = Math.max(96, Math.min(170, 62 + nodes.length * 10));
  while (offset < nodes.length) {
    const count = Math.min(ringCapacity(radius), nodes.length - offset);
    for (let slot = 0; slot < count; slot += 1) {
      const node = nodes[offset + slot];
      const size = knowledgeNodeSize(node.data.degree);
      const angle = (slot / count) * Math.PI * 2 - Math.PI / 2;
      positioned.push({
        ...node,
        position: {
          x: center.x + Math.cos(angle) * radius - size / 2,
          y: center.y + Math.sin(angle) * radius - size / 2,
        },
      });
    }
    offset += count;
    radius += RING_STEP;
  }
  return positioned;
}


export function layoutKnowledgeBubbles<T extends LayoutNode>(nodes: T[]): {
  nodes: Array<T & { position: { x: number; y: number } }>;
  bubbles: KnowledgeBubble[];
} {
  const groups = new Map<string, T[]>();
  for (const node of nodes) {
    const key = node.data.entityType || "Other";
    groups.set(key, [...(groups.get(key) ?? []), node]);
  }
  const orderedGroups = [...groups.entries()].sort(
    ([aType, aNodes], [bType, bNodes]) =>
      bNodes.reduce((sum, node) => sum + node.data.degree, 0) -
        aNodes.reduce((sum, node) => sum + node.data.degree, 0) || aType.localeCompare(bType),
  );
  const positionedNodes: Array<T & { position: { x: number; y: number } }> = [];
  const bubbles: KnowledgeBubble[] = [];
  for (const [index, [type, clusterNodes]] of orderedGroups.entries()) {
    const center = clusterCenter(index, orderedGroups.length);
    const sortedNodes = [...clusterNodes].sort(
      (a, b) => b.data.degree - a.data.degree || String(type).localeCompare(type),
    );
    const placed = layoutCluster(sortedNodes, center);
    positionedNodes.push(...placed);
    const minX = Math.min(...placed.map((node) => node.position.x));
    const minY = Math.min(...placed.map((node) => node.position.y));
    const maxX = Math.max(
      ...placed.map((node) => node.position.x + knowledgeNodeSize(node.data.degree)),
    );
    const maxY = Math.max(
      ...placed.map((node) => node.position.y + knowledgeNodeSize(node.data.degree)),
    );
    bubbles.push({
      id: `bubble-${type}`,
      label: type,
      count: clusterNodes.length,
      color: clusterNodes[0]?.data.color || "#55d6be",
      position: { x: minX - BUBBLE_PADDING, y: minY - BUBBLE_PADDING },
      width: maxX - minX + BUBBLE_PADDING * 2,
      height: maxY - minY + BUBBLE_PADDING * 2,
    });
  }
  return { nodes: positionedNodes, bubbles };
}
