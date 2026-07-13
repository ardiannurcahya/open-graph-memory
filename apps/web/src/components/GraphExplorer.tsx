import { Background, Controls, type Edge, type Node, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Network, RefreshCw } from "lucide-react";
import { useMemo } from "react";

import type { GraphSummary } from "../lib/types";

interface GraphExplorerProps {
  graph: GraphSummary | null;
  loading: boolean;
  onRefresh: () => void;
}

export function GraphExplorer({ graph, loading, onRefresh }: GraphExplorerProps) {
  const { nodes, edges } = useMemo(() => {
    const rawNodes = graph?.nodes ?? [];
    const nodeIds = new Set(rawNodes.map((n) => n.id));

    const flowNodes: Node[] = rawNodes.map((entity, i) => ({
      id: entity.id,
      position: {
        x: 120 + (i % 6) * 180,
        y: 60 + Math.floor(i / 6) * 140,
      },
      data: {
        label: entity.canonical_name,
        entityType: entity.entity_type,
        confidence: entity.confidence,
      },
      className: "graph-node",
    }));

    const flowEdges: Edge[] = (graph?.relations ?? [])
      .filter((r) => nodeIds.has(r.source_entity_id) && nodeIds.has(r.target_entity_id))
      .map((r) => ({
        id: r.id,
        source: r.source_entity_id,
        target: r.target_entity_id,
        label: r.relation_type,
        animated: false,
        className: "graph-edge",
      }));

    return { nodes: flowNodes, edges: flowEdges };
  }, [graph]);

  const hasGraph = nodes.length > 0;

  return (
    <section className="panel" id="graph" aria-labelledby="graph-heading">
      <div className="panel-header">
        <div>
          <span className="panel-eyebrow">Knowledge Graph</span>
          <h2 id="graph-heading" className="panel-title">
            Entity Atlas
          </h2>
        </div>
        <div className="panel-actions">
          <span className="badge">
            {graph ? `${graph.entity_count} entities · ${graph.relation_count} relations` : "—"}
          </span>
          <button
            className="btn btn-ghost"
            onClick={onRefresh}
            disabled={loading}
            title="Refresh graph"
          >
            <RefreshCw size={14} strokeWidth={2} className={loading ? "spin" : ""} />
          </button>
        </div>
      </div>

      <div className="graph-canvas">
        {hasGraph ? (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            proOptions={{ hideAttribution: true }}
            nodesDraggable
            zoomOnScroll
          >
            <Background color="#2a2a35" gap={20} />
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
