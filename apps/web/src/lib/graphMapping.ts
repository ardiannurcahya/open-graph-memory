import type { ExplorerView } from "../api/types";
import type { GraphState, GraphNode } from "./graphTypes";
import { classifyEntityType } from "./graphTypes";
import { buildCommunityPalette } from "./colorPalette";
import { buildGraphState } from "./graphPhysics";

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

  // If no communities from API, assign all to "default"
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

export function getNodeById(state: GraphState, id: string): GraphNode | null {
  return state.nodes.find((n) => n.id === id) ?? null;
}
