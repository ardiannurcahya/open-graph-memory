import type { GraphNode, GraphEdge, GraphState } from "./graphTypes";

const BASE_RADIUS: Record<string, number> = {
  person: 8,
  org: 10,
  tech: 9,
  concept: 8.5,
  document: 9.5,
  unknown: 8,
};

export interface PhysicsConfig {
  repulsion: number;
  attraction: number;
  communityGravity: number;
  damping: number;
  centering: number;
}

export const DEFAULT_PHYSICS: PhysicsConfig = {
  repulsion: 5500,
  attraction: 0.0004,
  communityGravity: 0.002,
  damping: 0.87,
  centering: 0.0002,
};

export function buildGraphState(
  rawNodes: { id: string; label: string; type: string; community: string; description: string; degree?: number }[],
  rawEdges: { id: string; source: string; target: string; label: string; weight: number }[],
  communityPalette: Map<string, { id: string; name: string; color: string; darkColor: string }>,
): GraphState {
  const adj = new Map<string, GraphEdge[]>();
  const edges: GraphEdge[] = rawEdges.map((r, i) => {
    const e: GraphEdge = {
      id: r.id || `edge_${i}`,
      source: r.source,
      target: r.target,
      label: r.label,
      weight: r.weight,
      particles: [Math.random(), Math.random(), Math.random()],
    };
    if (!adj.has(r.source)) adj.set(r.source, []);
    if (!adj.has(r.target)) adj.set(r.target, []);
    adj.get(r.source)?.push(e);
    adj.get(r.target)?.push(e);
    return e;
  });

  let maxDeg = 1;
  for (const r of rawNodes) {
    const deg = adj.get(r.id)?.length ?? 0;
    if (deg > maxDeg) maxDeg = deg;
  }

  const nodes: GraphNode[] = rawNodes.map((r, i) => {
    const deg = adj.get(r.id)?.length ?? 0;
    const frac = deg / maxDeg;
    const a = (i / Math.max(rawNodes.length, 1)) * Math.PI * 2 + (Math.random() - 0.5) * 0.5;
    const rad = 160 + Math.random() * 200;
    const typeKey = r.type in BASE_RADIUS ? r.type : "unknown";
    return {
      id: r.id,
      label: r.label,
      type: typeKey as GraphNode["type"],
      community: r.community,
      description: r.description,
      x: Math.cos(a) * rad,
      y: Math.sin(a) * rad,
      vx: 0,
      vy: 0,
      radius: (BASE_RADIUS[typeKey] ?? 8) + frac * 18,
      degree: r.degree ?? deg,
      degFrac: frac,
    };
  });

  return {
    nodes,
    edges,
    adj,
    communities: communityPalette as Map<string, GraphState["communities"] extends Map<string, infer V> ? V : never>,
    maxDegree: maxDeg,
  };
}

export function physicsStep(
  state: GraphState,
  config: PhysicsConfig,
  dragId: string | null,
): void {
  const { nodes, edges } = state;
  const N = nodes.length;

  // Repulsion (O(N²))
  for (let i = 0; i < N; i++) {
    for (let j = i + 1; j < N; j++) {
      const a = nodes[i];
      const b = nodes[j];
      if (a.id === dragId || b.id === dragId) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d2 = dx * dx + dy * dy + 1;
      const d = Math.sqrt(d2);
      const f = (config.repulsion * (a.radius + b.radius)) / 20 / d2;
      const fx = (dx / d) * f;
      const fy = (dy / d) * f;
      a.vx -= fx;
      a.vy -= fy;
      b.vx += fx;
      b.vy += fy;
    }
  }

  // Attraction (springs)
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  for (const e of edges) {
    const s = nodeMap.get(e.source);
    const t = nodeMap.get(e.target);
    if (!s || !t) continue;
    const dx = t.x - s.x;
    const dy = t.y - s.y;
    const d = Math.sqrt(dx * dx + dy * dy) + 1;
    const f = d * config.attraction * e.weight;
    const fx = (dx / d) * f;
    const fy = (dy / d) * f;
    if (s.id !== dragId) { s.vx += fx; s.vy += fy; }
    if (t.id !== dragId) { t.vx -= fx; t.vy -= fy; }
  }

  // Community gravity
  const cent: Record<string, { x: number; y: number; c: number }> = {};
  for (const n of nodes) {
    if (!cent[n.community]) cent[n.community] = { x: 0, y: 0, c: 0 };
    cent[n.community].x += n.x;
    cent[n.community].y += n.y;
    cent[n.community].c += 1;
  }
  for (const k in cent) {
    cent[k].x /= cent[k].c;
    cent[k].y /= cent[k].c;
  }
  for (const n of nodes) {
    if (n.id === dragId) continue;
    const c = cent[n.community];
    if (c) {
      n.vx += (c.x - n.x) * config.communityGravity;
      n.vy += (c.y - n.y) * config.communityGravity;
    }
  }

  // Integrate
  for (const n of nodes) {
    if (n.id === dragId) continue;
    n.vx = (n.vx - n.x * config.centering) * config.damping;
    n.vy = (n.vy - n.y * config.centering) * config.damping;
    n.x += n.vx;
    n.y += n.vy;
  }
}

export function fitAll(
  nodes: GraphNode[],
  width: number,
  height: number,
  dpr: number,
): { x: number; y: number; zoom: number } {
  if (nodes.length === 0) return { x: 0, y: 0, zoom: 1 };
  const minX = Math.min(...nodes.map((n) => n.x));
  const maxX = Math.max(...nodes.map((n) => n.x));
  const minY = Math.min(...nodes.map((n) => n.y));
  const maxY = Math.max(...nodes.map((n) => n.y));
  const rangeX = maxX - minX || 1;
  const rangeY = maxY - minY || 1;
  const pad = 100;
  const z = Math.min(
    (width * dpr - pad * 2) / rangeX,
    (height * dpr - pad * 2) / rangeY,
  ) * 0.85;
  const zoom = Math.max(0.12, Math.min(3, z));
  return {
    x: -(minX + rangeX / 2) * zoom,
    y: -(minY + rangeY / 2) * zoom,
    zoom,
  };
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
