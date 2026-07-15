import {
  Background,
  Controls,
  type Edge,
  Handle,
  MarkerType,
  type Node,
  type NodeProps,
  Position,
  ReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Network, RefreshCw, RotateCw, X } from "lucide-react";
import { useMemo, useState } from "react";

import type { ExplorerNode, GraphExplorerView } from "../lib/types";
import { knowledgeNodeSize, layoutKnowledgeBubbles } from "./graphLayout";

interface GraphExplorerProps {
  graph: GraphExplorerView | null;
  loading: boolean;
  refreshingAnalytics: boolean;
  onRefresh: () => void;
  onRefreshAnalytics: () => void;
}

interface KnowledgeNodeData extends Record<string, unknown> {
  label: string;
  entityType: string;
  degree: number;
  importance: number;
  color: string;
  communityId: string | null;
}

type KnowledgeNode = Node<KnowledgeNodeData, "knowledge">;

const TYPE_COLORS = ["#55d6be", "#8b9cff", "#f0b35a", "#d98cff", "#58b8f5", "#ef7d8f"];
const SEMANTIC_COLORS: Record<string, string> = {
  person: "#8b9cff",
  organization: "#55d6be",
  place: "#ef7d8f",
  award: "#d98cff",
  "chemical element": "#f0b35a",
  "scientific concept": "#58b8f5",
};

function colorForType(type: string): string {
  const semanticColor = SEMANTIC_COLORS[type.toLowerCase()];
  if (semanticColor) return semanticColor;
  let hash = 0;
  for (const char of type) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return TYPE_COLORS[hash % TYPE_COLORS.length];
}

function KnowledgeNodeView({ data, selected }: NodeProps<KnowledgeNode>) {
  const size = knowledgeNodeSize(data.degree);
  return (
    <div
      className={`knowledge-node ${selected ? "is-selected" : ""}`}
      style={{
        width: size,
        height: size,
        borderColor: data.color,
        boxShadow: `0 0 0 5px ${data.color}18, 0 0 28px ${data.color}22`,
      }}
      title={`${data.label} · ${data.entityType} · ${data.degree} connections`}
    >
      <Handle type="target" position={Position.Top} className="knowledge-handle" />
      <strong>{data.label}</strong>
      <Handle type="source" position={Position.Bottom} className="knowledge-handle" />
    </div>
  );
}

const nodeTypes = { knowledge: KnowledgeNodeView };

function selectedNode(graph: GraphExplorerView | null, id: string | null): ExplorerNode | null {
  return id ? graph?.nodes.find((node) => node.id === id) ?? null : null;
}

export function GraphExplorer({
  graph,
  loading,
  refreshingAnalytics,
  onRefresh,
  onRefreshAnalytics,
}: GraphExplorerProps) {
  const [communityFilter, setCommunityFilter] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { nodes, edges, legend } = useMemo(() => {
    const allNodes = graph?.nodes ?? [];
    const rawNodes = communityFilter === "all"
      ? allNodes
      : allNodes.filter((node) => node.community_id === communityFilter);
    const nodeIds = new Set(rawNodes.map((node) => node.id));
    const layout = layoutKnowledgeBubbles(
      [...rawNodes]
        .sort((a, b) => b.importance - a.importance || a.canonical_name.localeCompare(b.canonical_name))
        .map((entity) => ({
          id: entity.id,
          type: "knowledge" as const,
          data: {
            label: entity.canonical_name,
            entityType: entity.entity_type,
            degree: entity.degree,
            importance: entity.importance,
            color: colorForType(entity.entity_type),
            communityId: entity.community_id,
          },
          draggable: true,
        })),
    );
    const flowEdges: Edge[] = (graph?.relations ?? [])
      .filter((relation) => nodeIds.has(relation.source) && nodeIds.has(relation.target))
      .map((relation, index) => ({
        id: relation.id,
        source: relation.source,
        target: relation.target,
        label: relation.type.replaceAll("_", " "),
        type: "bezier",
        pathOptions: { curvature: 0.28 + (index % 3) * 0.08 },
        markerEnd: { type: MarkerType.ArrowClosed, width: 19, height: 19 },
        labelBgPadding: [7, 4],
        labelBgBorderRadius: 5,
        className: "knowledge-edge",
      }));
    const typeLegend = [...new Set(rawNodes.map((node) => node.entity_type))]
      .sort()
      .map((type) => ({ type, color: colorForType(type) }));
    return { nodes: layout.nodes as KnowledgeNode[], edges: flowEdges, legend: typeLegend };
  }, [communityFilter, graph]);

  const selected = selectedNode(graph, selectedId);
  const hasGraph = nodes.length > 0;
  const analyticsState = graph?.analytics
    ? graph.analytics.stale ? "Stale analytics" : `${graph.analytics.community_count} communities`
    : "Analytics not run";

  return (
    <section className="panel knowledge-panel" id="graph" aria-labelledby="graph-heading">
      <div className="panel-header">
        <div>
          <span className="panel-eyebrow">Knowledge Graph</span>
          <h2 id="graph-heading" className="panel-title">Entity Network</h2>
        </div>
        <div className="panel-actions">
          <span className="badge">{graph ? `${graph.stats.entity_count} entities · ${graph.stats.relation_count} relations` : "—"}</span>
          <button className="btn btn-ghost" onClick={onRefresh} disabled={loading} title="Refresh graph">
            <RefreshCw size={14} strokeWidth={2} className={loading ? "spin" : ""} />
          </button>
        </div>
      </div>

      <div className="knowledge-toolbar">
        <label>
          Community
          <select value={communityFilter} onChange={(event) => { setCommunityFilter(event.target.value); setSelectedId(null); }}>
            <option value="all">All communities</option>
            {graph?.communities.map((community, index) => (
              <option key={community.id} value={community.id}>Community {index + 1} · {community.entity_count}</option>
            ))}
          </select>
        </label>
        <span className={graph?.refresh_required ? "analytics-state is-stale" : "analytics-state"}>{analyticsState}</span>
        <button className="btn btn-ghost analytics-refresh" onClick={onRefreshAnalytics} disabled={refreshingAnalytics || !graph} title="Refresh community analytics">
          <RotateCw size={14} className={refreshingAnalytics ? "spin" : ""} /> Refresh analytics
        </button>
      </div>

      <div className="knowledge-legend" aria-label="Entity type legend">
        {legend.map((item) => <span key={item.type}><i style={{ background: item.color }} />{item.type}</span>)}
      </div>

      <div className="graph-canvas knowledge-canvas">
        {hasGraph ? (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.16, minZoom: 0.35, maxZoom: 1.15 }}
            minZoom={0.35}
            maxZoom={1.8}
            proOptions={{ hideAttribution: true }}
            nodesDraggable
            zoomOnScroll
            onNodeClick={(_, node) => setSelectedId(node.id)}
            onPaneClick={() => setSelectedId(null)}
          >
            <Background color="#273140" gap={24} size={1} />
            <Controls showInteractive={false} />
          </ReactFlow>
        ) : (
          <div className="empty-state"><Network size={28} strokeWidth={1.5} /><p>Graph projection will appear after entity extraction completes.</p></div>
        )}
        {selected && (
          <aside className="graph-node-detail" aria-label="Selected entity">
            <button onClick={() => setSelectedId(null)} aria-label="Close entity details"><X size={15} /></button>
            <span>{selected.entity_type}</span>
            <strong>{selected.canonical_name}</strong>
            <dl><div><dt>Connections</dt><dd>{selected.degree}</dd></div><div><dt>Importance</dt><dd>{(selected.importance * 100).toFixed(1)}%</dd></div><div><dt>Weight</dt><dd>{selected.weighted_degree.toFixed(2)}</dd></div></dl>
          </aside>
        )}
      </div>
    </section>
  );
}
