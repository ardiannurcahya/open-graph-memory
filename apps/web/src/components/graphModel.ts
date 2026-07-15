import type { ExplorerNode, GraphExplorerView } from "../lib/types";

export const COMMUNITY_COLORS = ["#55d6be", "#8b9cff", "#f0b35a", "#d98cff", "#58b8f5", "#ef7d8f"] as const;

function hash(value: string): number {
  return [...value].reduce((total, char) => ((total * 31) + char.charCodeAt(0)) >>> 0, 0);
}

export function colorForCommunity(communityId: string | null): string {
  return COMMUNITY_COLORS[hash(communityId ?? "unassigned") % COMMUNITY_COLORS.length];
}

export function colorForNode(node: ExplorerNode): string {
  return colorForCommunity(node.community_id);
}

export function nodeRadius(degree: number, scale = 1): number {
  return Math.min(42, 18 + Math.sqrt(Math.max(0, degree)) * 5) * scale;
}

export function initialPosition(id: string, width = 900, height = 520): { x: number; y: number } {
  const value = hash(id);
  return { x: 60 + (value % Math.max(1, width - 120)), y: 60 + (Math.floor(value / 997) % Math.max(1, height - 120)) };
}

export function buildGraphModel(graph: GraphExplorerView | null, options: { communityId?: string; entityType?: string; relationType?: string; nodeScale?: number } = {}) {
  const nodes = (graph?.nodes ?? []).filter((node) =>
    (!options.communityId || options.communityId === "all" || node.community_id === options.communityId)
    && (!options.entityType || options.entityType === "all" || node.entity_type === options.entityType),
  ).map((node) => ({ ...node, color: colorForNode(node), radius: nodeRadius(node.degree, options.nodeScale) }));
  const ids = new Set(nodes.map((node) => node.id));
  const links = (graph?.relations ?? []).filter((link) => ids.has(link.source) && ids.has(link.target)
    && (!options.relationType || options.relationType === "all" || link.type === options.relationType));
  return { nodes, links };
}

export function connectedNodeIds(links: Array<{ source: string; target: string }>, nodeId: string | null): Set<string> {
  if (!nodeId) return new Set();
  return new Set(links.flatMap((link) => link.source === nodeId ? [link.target] : link.target === nodeId ? [link.source] : []));
}
