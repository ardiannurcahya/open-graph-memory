import type { EntityView, ExplorerView, GraphSummary, RelationView } from "../api/types";
import type { GraphState, GraphNode } from "./graphTypes";
import { classifyEntityType } from "./graphTypes";
import { buildCommunityPalette } from "./colorPalette";
import { buildGraphState } from "./graphPhysics";

function isExpired(validUntil: string | null | undefined): boolean {
  return validUntil != null;
}

export function explorerToGraphState(view: ExplorerView): GraphState {
  const communityIds = view.communities.map((c) => c.id);
  const communityNames = new Map<string, string>();
  for (const c of view.communities) {
    communityNames.set(c.id, c.id);
  }

  const palette = buildCommunityPalette(communityIds.length > 0 ? communityIds : ["default"], communityNames);

  const rawNodes = view.nodes.map((n) => ({
    id: n.id,
    label: n.canonical_name,
    type: classifyEntityType(n.entity_type),
    community: n.community_id ?? "default",
    description: `${n.entity_type} · degree ${n.degree} · importance ${n.importance.toFixed(2)}`,
    degree: n.degree,
  }));

  const rawEdges = view.relations.map((r) => ({
    id: r.id,
    source: r.source,
    target: r.target,
    label: r.type,
    weight: r.weight,
  }));

  const state = buildGraphState(rawNodes, rawEdges, palette);

  if (communityIds.length === 0 && !state.communities.has("default")) {
    state.communities.set("default", {
      id: "default",
      name: "Default",
      color: "#d4a056",
      darkColor: "#8a6730",
    });
  }

  return state;
}

export function graphSummaryToGraphState(view: GraphSummary): GraphState {
  const communityNames = new Map<string, string>();
  const communityIds = [...new Set(view.nodes.map((node) => node.entity_type || "unknown"))];
  for (const id of communityIds) communityNames.set(id, id);
  const palette = buildCommunityPalette(communityIds, communityNames);
  return buildGraphState(
    view.nodes.map((node) => ({
      id: node.id,
      label: node.canonical_name,
      type: classifyEntityType(node.entity_type),
      community: node.entity_type || "unknown",
      description: `${node.entity_type} · confidence ${node.confidence.toFixed(2)} · ${node.review_state}${isExpired(node.valid_until) ? " · expired" : ""}`,
      degree: relationDegree(node, view.relations),
      validFrom: node.valid_from,
      validUntil: node.valid_until,
      isExpired: isExpired(node.valid_until),
    })),
    view.relations.map((relation) => ({
      id: relation.id,
      source: relation.source_entity_id,
      target: relation.target_entity_id,
      label: relation.relation_type,
      weight: relation.confidence,
      validFrom: relation.valid_from,
      validUntil: relation.valid_until,
      isExpired: isExpired(relation.valid_until),
    })),
    palette,
  );
}

function relationDegree(entity: EntityView, relations: RelationView[]): number {
  return relations.filter(
    (relation) =>
      relation.source_entity_id === entity.id || relation.target_entity_id === entity.id,
  ).length;
}

export function getNodeById(state: GraphState, id: string): GraphNode | null {
  return state.nodes.find((n) => n.id === id) ?? null;
}
