import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationNodeDatum,
} from "d3-force";
import { Network, RefreshCw, RotateCw, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type PointerEvent } from "react";

import type { ExplorerNode, GraphExplorerView } from "../lib/types";

interface GraphExplorerProps {
  graph: GraphExplorerView | null;
  loading: boolean;
  refreshingAnalytics: boolean;
  onRefresh: () => void;
  onRefreshAnalytics: () => void;
}

interface ForceNode extends SimulationNodeDatum, ExplorerNode {
  color: string;
  radius: number;
}

interface ForceLink {
  id: string;
  source: string | ForceNode;
  target: string | ForceNode;
  type: string;
  weight: number;
}

const TYPE_COLORS = ["#55d6be", "#8b9cff", "#f0b35a", "#d98cff", "#58b8f5", "#ef7d8f"];
const SEMANTIC_COLORS: Record<string, string> = {
  person: "#8b9cff", organization: "#55d6be", place: "#ef7d8f", award: "#d98cff",
  "chemical element": "#f0b35a", "scientific concept": "#58b8f5",
};

function colorForType(type: string): string {
  const semanticColor = SEMANTIC_COLORS[type.toLowerCase()];
  if (semanticColor) return semanticColor;
  let hash = 0;
  for (const char of type) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return TYPE_COLORS[hash % TYPE_COLORS.length];
}

function nodeRadius(degree: number): number {
  return Math.min(42, 18 + Math.sqrt(Math.max(0, degree)) * 5);
}

function selectedNode(graph: GraphExplorerView | null, id: string | null): ExplorerNode | null {
  return id ? graph?.nodes.find((node) => node.id === id) ?? null : null;
}

export function GraphExplorer({ graph, loading, refreshingAnalytics, onRefresh, onRefreshAnalytics }: GraphExplorerProps) {
  const canvasRef = useRef<SVGSVGElement>(null);
  const dragRef = useRef<ForceNode | null>(null);
  const [communityFilter, setCommunityFilter] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [size, setSize] = useState({ width: 900, height: 520 });
  const [positions, setPositions] = useState<ForceNode[]>([]);
  const { nodes, links, legend } = useMemo(() => {
    const visible = (graph?.nodes ?? []).filter((node) => communityFilter === "all" || node.community_id === communityFilter);
    const ids = new Set(visible.map((node) => node.id));
    return {
      nodes: visible.map((node) => ({ ...node, color: colorForType(node.entity_type), radius: nodeRadius(node.degree) })),
      links: (graph?.relations ?? []).filter((link) => ids.has(link.source) && ids.has(link.target)).map((link) => ({ ...link })),
      legend: [...new Set(visible.map((node) => node.entity_type))].sort().map((type) => ({ type, color: colorForType(type) })),
    };
  }, [communityFilter, graph]);

  useEffect(() => {
    const element = canvasRef.current;
    if (!element) return;
    const resize = () => setSize({ width: element.clientWidth || 900, height: element.clientHeight || 520 });
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (nodes.length === 0) {
      setPositions([]);
      return;
    }
    const simulationNodes = nodes.map((node) => ({ ...node }));
    const simulation = forceSimulation<ForceNode>(simulationNodes)
      .force("link", forceLink<ForceNode, ForceLink>(links).id((node) => node.id).distance((link) => 72 + (1 / Math.max(link.weight, 0.1)) * 12).strength(0.55))
      .force("charge", forceManyBody().strength(-260))
      .force("collide", forceCollide<ForceNode>().radius((node) => node.radius + 10).strength(0.9))
      .force("center", forceCenter(size.width / 2, size.height / 2))
      .alpha(1)
      .on("tick", () => setPositions([...simulationNodes]));
    return () => { simulation.stop(); };
  }, [links, nodes, size]);

  const selected = selectedNode(graph, selectedId);
  const selectedRelations = useMemo(
    () => selectedId ? links.filter((link) => {
      const source = link.source as string | ForceNode;
      const target = link.target as string | ForceNode;
      return (typeof source === "string" ? source : source.id) === selectedId || (typeof target === "string" ? target : target.id) === selectedId;
    }) : [],
    [links, selectedId],
  );
  const analyticsState = graph?.analytics ? graph.analytics.stale ? "Stale analytics" : `${graph.analytics.community_count} communities` : "Analytics not run";
  const point = (event: PointerEvent<SVGSVGElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return { x: event.clientX - bounds.left, y: event.clientY - bounds.top };
  };
  const startDrag = (event: PointerEvent<SVGGElement>, node: ForceNode) => {
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = node;
    node.fx = node.x;
    node.fy = node.y;
  };
  const drag = (event: PointerEvent<SVGSVGElement>) => {
    const node = dragRef.current;
    if (!node) return;
    const cursor = point(event);
    node.fx = cursor.x;
    node.fy = cursor.y;
    setPositions((current) => [...current]);
  };
  const endDrag = () => {
    const node = dragRef.current;
    if (node) { node.fx = null; node.fy = null; }
    dragRef.current = null;
  };

  return <section className="panel knowledge-panel" id="graph" aria-labelledby="graph-heading">
    <div className="panel-header"><div><span className="panel-eyebrow">Knowledge Graph</span><h2 id="graph-heading" className="panel-title">Entity Network</h2></div><div className="panel-actions"><span className="badge">{graph ? `${graph.stats.entity_count} entities · ${graph.stats.relation_count} relations` : "—"}</span><button className="btn btn-ghost" onClick={onRefresh} disabled={loading} title="Refresh graph"><RefreshCw size={14} strokeWidth={2} className={loading ? "spin" : ""} /></button></div></div>
    <div className="knowledge-toolbar"><label>Community<select value={communityFilter} onChange={(event) => { setCommunityFilter(event.target.value); setSelectedId(null); }}><option value="all">All communities</option>{graph?.communities.map((community, index) => <option key={community.id} value={community.id}>Community {index + 1} · {community.entity_count}</option>)}</select></label><label className="graph-search"><Search size={14} /><span className="sr-only">Find entity</span><input value={query} onChange={(event) => { const value = event.target.value; setQuery(value); const match = nodes.find((node) => node.canonical_name.toLowerCase().includes(value.trim().toLowerCase())); if (value.trim() && match) setSelectedId(match.id); }} placeholder="Find entity" aria-label="Find entity" /></label><span className={graph?.refresh_required ? "analytics-state is-stale" : "analytics-state"}>{analyticsState}</span><button className="btn btn-ghost analytics-refresh" onClick={onRefreshAnalytics} disabled={refreshingAnalytics || !graph} title="Refresh community analytics"><RotateCw size={14} className={refreshingAnalytics ? "spin" : ""} /> Refresh analytics</button></div>
    <div className="knowledge-legend" aria-label="Entity type legend">{legend.map((item) => <span key={item.type}><i style={{ background: item.color }} />{item.type}</span>)}</div>
    <div className="graph-canvas knowledge-canvas">{nodes.length ? <svg ref={canvasRef} data-testid="d3-graph" className="d3-graph" viewBox={`0 0 ${size.width} ${size.height}`} role="img" aria-label="Force-directed entity network" onPointerMove={drag} onPointerUp={endDrag} onPointerCancel={endDrag} onClick={() => setSelectedId(null)}>
      <g className="d3-links">{links.map((link) => { const source = typeof link.source === "string" ? positions.find((node) => node.id === link.source) : link.source; const target = typeof link.target === "string" ? positions.find((node) => node.id === link.target) : link.target; return source?.x != null && source.y != null && target?.x != null && target.y != null ? <line key={link.id} x1={source.x} y1={source.y} x2={target.x} y2={target.y}><title>{link.type.replaceAll("_", " ")}</title></line> : null; })}</g>
      <g className="d3-nodes">{positions.map((node) => node.x != null && node.y != null ? <g key={node.id} tabIndex={0} role="button" aria-label={`View ${node.canonical_name}`} className={`d3-node ${selectedId === node.id ? "is-selected" : ""} ${query.trim() && node.canonical_name.toLowerCase().includes(query.trim().toLowerCase()) ? "is-match" : ""}`} transform={`translate(${node.x},${node.y})`} onPointerDown={(event) => startDrag(event, node)} onClick={(event) => { event.stopPropagation(); setSelectedId(node.id); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedId(node.id); } }}><circle r={node.radius} fill={node.color} /><text dy="-0.1em">{node.canonical_name}</text><text className="d3-node-type" dy="1.25em">{node.entity_type}</text><title>{node.canonical_name} · {node.entity_type} · {node.degree} connections</title></g> : null)}</g>
    </svg> : <div className="empty-state"><Network size={28} strokeWidth={1.5} /><p>Graph projection will appear after entity extraction completes.</p></div>}{selected && <aside className="graph-node-detail" aria-label="Selected entity"><button onClick={() => setSelectedId(null)} aria-label="Close entity details"><X size={15} /></button><span>{selected.entity_type}</span><strong>{selected.canonical_name}</strong><dl><div><dt>Connections</dt><dd>{selected.degree}</dd></div><div><dt>Importance</dt><dd>{(selected.importance * 100).toFixed(1)}%</dd></div><div><dt>Weight</dt><dd>{selected.weighted_degree.toFixed(2)}</dd></div></dl>{selectedRelations.length > 0 && <ul className="graph-node-relations" aria-label="Entity relations">{selectedRelations.map((relation) => <li key={relation.id}>{relation.type.replaceAll("_", " ")} · {relation.confidence.toFixed(2)}</li>)}</ul>}</aside>}</div>
  </section>;
}
