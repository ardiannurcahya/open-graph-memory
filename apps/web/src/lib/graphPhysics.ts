import type { CommunityLayout, GraphNode, GraphEdge, GraphState } from "./graphTypes";

const BASE_RADIUS: Record<string, number> = {
  person: 5.2,
  org: 6.5,
  tech: 5.85,
  concept: 5.525,
  document: 6.175,
  unknown: 5.2,
};

export function buildGraphState(
  rawNodes: { id: string; label: string; type: string; community: string; description: string; degree?: number; validFrom?: string | null; validUntil?: string | null; isExpired?: boolean }[],
  rawEdges: { id: string; source: string; target: string; label: string; weight: number; validFrom?: string | null; validUntil?: string | null; isExpired?: boolean }[],
  communityPalette: Map<string, { id: string; name: string; color: string; darkColor: string }>,
): GraphState {
  const adj = new Map<string, GraphEdge[]>();
  const sortedEdges = [...rawEdges].sort(compareRawEdges);
  const reservedEdgeIds = new Set(sortedEdges.map((edge) => edge.id).filter(Boolean));
  const usedEdgeIds = new Set<string>();
  let generatedEdgeId = 0;
  const edges: GraphEdge[] = sortedEdges.map((r, i) => {
    let id = r.id;
    if (!id || usedEdgeIds.has(id)) {
      do id = `edge_${generatedEdgeId++}`; while (reservedEdgeIds.has(id) || usedEdgeIds.has(id));
    }
    usedEdgeIds.add(id);
    const e: GraphEdge = {
      id: id || `edge_${i}`,
      source: r.source,
      target: r.target,
      label: r.label,
      weight: r.weight,
      validFrom: r.validFrom,
      validUntil: r.validUntil,
      isExpired: r.isExpired,
    };
    if (!adj.has(r.source)) adj.set(r.source, []);
    if (!adj.has(r.target)) adj.set(r.target, []);
    adj.get(r.source)?.push(e);
    adj.get(r.target)?.push(e);
    return e;
  });

  let maxDeg = 1;
  for (const r of rawNodes) {
    const deg = r.degree ?? (adj.get(r.id)?.length ?? 0);
    if (deg > maxDeg) maxDeg = deg;
  }

  const nodes: GraphNode[] = [...rawNodes]
    .sort((a, b) => a.id.localeCompare(b.id))
    .map((r) => {
    const deg = r.degree ?? (adj.get(r.id)?.length ?? 0);
    const frac = deg / maxDeg;
    const typeKey = r.type in BASE_RADIUS ? r.type : "unknown";
    return {
      id: r.id,
      label: r.label,
      type: typeKey as GraphNode["type"],
      community: r.community,
      description: r.description,
      x: 0,
      y: 0,
      vx: 0,
      vy: 0,
      radius: (BASE_RADIUS[typeKey] ?? 5.2) + frac * 11.7,
      degree: deg,
      degFrac: frac,
      validFrom: r.validFrom,
      validUntil: r.validUntil,
      isExpired: r.isExpired,
    };
  });

  return {
    nodes,
    edges,
    adj,
    communities: communityPalette as Map<string, GraphState["communities"] extends Map<string, infer V> ? V : never>,
    communityLayout: new Map<string, CommunityLayout>(),
    seedPositions: new Map<string, [number, number]>(),
    maxDegree: maxDeg,
  };
}

function compareRawEdges(
  left: { id: string; source: string; target: string; label: string; weight: number },
  right: { id: string; source: string; target: string; label: string; weight: number },
): number {
  return left.id.localeCompare(right.id)
    || left.source.localeCompare(right.source)
    || left.target.localeCompare(right.target)
    || left.label.localeCompare(right.label)
    || left.weight - right.weight;
}

export function highlightConnected(
  state: GraphState,
  nodeId: string,
): { nodes: Set<string>; edges: Set<string> } {
  const nIds = new Set<string>([nodeId]);
  const eIds = new Set<string>();
  const adj = state.adj.get(nodeId) ?? [];
  for (const e of adj) {
    eIds.add(e.id);
    nIds.add(e.source);
    nIds.add(e.target);
  }
  return { nodes: nIds, edges: eIds };
}
