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
import { Network, RefreshCw } from "lucide-react";
import { useMemo } from "react";

import type { EntityView, GraphSummary } from "../lib/types";
import { knowledgeNodeSize, layoutKnowledgeBubbles } from "./graphLayout";

interface GraphExplorerProps {
  graph: GraphSummary | null;
  loading: boolean;
  onRefresh: () => void;
}

interface KnowledgeNodeData extends Record<string, unknown> {
  label: string;
  entityType: string;
  confidence: number;
  degree: number;
  color: string;
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

function KnowledgeNodeView({ data }: NodeProps<KnowledgeNode>) {
  const size = knowledgeNodeSize(data.degree);
  return (
    <div
      className="knowledge-node"
      style={{
        width: size,
        height: size,
        borderColor: data.color,
        boxShadow: `0 0 0 5px ${data.color}18, 0 0 28px ${data.color}22`,
      }}
      title={`${data.label} · ${data.entityType} · ${Math.round(data.confidence * 100)}% confidence`}
    >
      <Handle type="target" position={Position.Top} className="knowledge-handle" />
      <strong>{data.label}</strong>
      <Handle type="source" position={Position.Bottom} className="knowledge-handle" />
    </div>
  );
}

const nodeTypes = { knowledge: KnowledgeNodeView };

export function GraphExplorer({ graph, loading, onRefresh }: GraphExplorerProps) {
  const { nodes, edges, legend } = useMemo(() => {
    const rawNodes = graph?.nodes ?? [];
    const nodeIds = new Set(rawNodes.map((node) => node.id));
    const degree = new Map(rawNodes.map((node) => [node.id, 0]));
    for (const relation of graph?.relations ?? []) {
      if (!nodeIds.has(relation.source_entity_id) || !nodeIds.has(relation.target_entity_id)) continue;
      degree.set(relation.source_entity_id, (degree.get(relation.source_entity_id) ?? 0) + 1);
      degree.set(relation.target_entity_id, (degree.get(relation.target_entity_id) ?? 0) + 1);
    }

    const ordered = [...rawNodes].sort(
      (a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0) || a.canonical_name.localeCompare(b.canonical_name),
    );
    const layout = layoutKnowledgeBubbles(
      ordered.map((entity) => ({
        id: entity.id,
        type: "knowledge" as const,
        data: {
          label: entity.canonical_name,
          entityType: entity.entity_type,
          confidence: entity.confidence,
          degree: degree.get(entity.id) ?? 0,
          color: colorForType(entity.entity_type),
        },
        draggable: true,
      })),
    );
    const flowNodes: KnowledgeNode[] = layout.nodes;

    const flowEdges: Edge[] = (graph?.relations ?? [])
      .filter((relation) => nodeIds.has(relation.source_entity_id) && nodeIds.has(relation.target_entity_id))
      .map((relation, index) => ({
        id: relation.id,
        source: relation.source_entity_id,
        target: relation.target_entity_id,
        label: relation.relation_type.replaceAll("_", " "),
        type: "bezier",
        pathOptions: { curvature: 0.28 + (index % 3) * 0.08 },
        markerEnd: { type: MarkerType.ArrowClosed, width: 19, height: 19 },
        labelBgPadding: [7, 4],
        labelBgBorderRadius: 5,
        className: "knowledge-edge",
      }));

    const typeLegend = [...new Set(rawNodes.map((node: EntityView) => node.entity_type))]
      .sort()
      .map((type) => ({ type, color: colorForType(type) }));
    return { nodes: flowNodes, edges: flowEdges, legend: typeLegend };
  }, [graph]);

  const hasGraph = nodes.length > 0;

  return (
    <section className="panel knowledge-panel" id="graph" aria-labelledby="graph-heading">
      <div className="panel-header">
        <div>
          <span className="panel-eyebrow">Knowledge Graph</span>
          <h2 id="graph-heading" className="panel-title">Entity Network</h2>
        </div>
        <div className="panel-actions">
          <span className="badge">
            {graph ? `${graph.entity_count} entities · ${graph.relation_count} relations` : "—"}
          </span>
          <button className="btn btn-ghost" onClick={onRefresh} disabled={loading} title="Refresh graph">
            <RefreshCw size={14} strokeWidth={2} className={loading ? "spin" : ""} />
          </button>
        </div>
      </div>

      <div className="knowledge-legend" aria-label="Entity type legend">
        {legend.map((item) => (
          <span key={item.type}><i style={{ background: item.color }} />{item.type}</span>
        ))}
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
          >
            <Background color="#273140" gap={24} size={1} />
            <Controls showInteractive={false} />
          </ReactFlow>
        ) : (
          <div className="empty-state">
            <Network size={28} strokeWidth={1.5} />
            <p>
              {graph && graph.entity_count > 0
                ? "Entities exist but none match the current view limit."
                : "Graph projection will appear after entity extraction completes."}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
