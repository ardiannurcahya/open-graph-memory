export const KNOWLEDGE_NODE_GAP = 16;

const CENTER_X = 450;
const CENTER_Y = 260;
const MIN_NODE_SIZE = 64;
const MAX_NODE_SIZE = 172;
const PACKING_STEP = 8;

interface LayoutNode {
  id?: unknown;
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
  const safeDegree = Math.max(0, degree);
  return Math.min(MAX_NODE_SIZE, MIN_NODE_SIZE + Math.sqrt(safeDegree) * 18);
}

function centerOf<T extends LayoutNode>(node: T & { position: { x: number; y: number } }) {
  const size = knowledgeNodeSize(node.data.degree);
  return { x: node.position.x + size / 2, y: node.position.y + size / 2, radius: size / 2 };
}

function overlaps<T extends LayoutNode>(
  candidate: { x: number; y: number; radius: number },
  placed: Array<T & { position: { x: number; y: number } }>,
): boolean {
  return placed.some((node) => {
    const other = centerOf(node);
    return Math.hypot(candidate.x - other.x, candidate.y - other.y) <
      candidate.radius + other.radius + KNOWLEDGE_NODE_GAP;
  });
}

function packedPosition<T extends LayoutNode>(
  node: T,
  placed: Array<T & { position: { x: number; y: number } }>,
): { x: number; y: number } {
  const size = knowledgeNodeSize(node.data.degree);
  const radius = size / 2;
  if (placed.length === 0) return { x: CENTER_X - radius, y: CENTER_Y - radius };

  let searchRadius = PACKING_STEP;
  while (searchRadius < 5000) {
    const slots = Math.max(12, Math.ceil((Math.PI * 2 * searchRadius) / PACKING_STEP));
    for (let slot = 0; slot < slots; slot += 1) {
      const angle = (slot / slots) * Math.PI * 2 + placed.length * 0.61;
      const candidate = {
        x: CENTER_X + Math.cos(angle) * searchRadius,
        y: CENTER_Y + Math.sin(angle) * searchRadius,
        radius,
      };
      if (!overlaps(candidate, placed)) return { x: candidate.x - radius, y: candidate.y - radius };
    }
    searchRadius += PACKING_STEP;
  }

  return { x: CENTER_X - radius, y: CENTER_Y - radius };
}

function recenter<T extends LayoutNode>(
  nodes: Array<T & { position: { x: number; y: number } }>,
): Array<T & { position: { x: number; y: number } }> {
  if (nodes.length === 0) return [];
  const minX = Math.min(...nodes.map((node) => node.position.x));
  const minY = Math.min(...nodes.map((node) => node.position.y));
  const maxX = Math.max(...nodes.map((node) => node.position.x + knowledgeNodeSize(node.data.degree)));
  const maxY = Math.max(...nodes.map((node) => node.position.y + knowledgeNodeSize(node.data.degree)));
  const dx = CENTER_X - (minX + maxX) / 2;
  const dy = CENTER_Y - (minY + maxY) / 2;
  return nodes.map((node) => ({
    ...node,
    position: { x: node.position.x + dx, y: node.position.y + dy },
  }));
}

export function layoutKnowledgeNodes<T extends LayoutNode>(
  nodes: T[],
  hasHub: boolean,
): Array<T & { position: { x: number; y: number } }> {
  void hasHub;
  if (nodes.length === 0) return [];

  const positioned: Array<T & { position: { x: number; y: number } }> = [];
  const sortedNodes = [...nodes].sort((a, b) => b.data.degree - a.data.degree || String(a.id).localeCompare(String(b.id)));
  for (const node of sortedNodes) {
    positioned.push({ ...node, position: packedPosition(node, positioned) });
  }

  return recenter(positioned);
}


export function layoutKnowledgeBubbles<T extends LayoutNode>(nodes: T[]): {
  nodes: Array<T & { position: { x: number; y: number } }>;
  bubbles: KnowledgeBubble[];
} {
  return { nodes: layoutKnowledgeNodes(nodes, false), bubbles: [] };
}
