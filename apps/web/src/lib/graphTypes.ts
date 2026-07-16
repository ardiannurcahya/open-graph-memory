export type EntityType = "person" | "org" | "tech" | "concept" | "document" | "unknown";

export interface GraphNode {
  id: string;
  label: string;
  type: EntityType;
  community: string;
  description: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  degree: number;
  degFrac: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  weight: number;
  particles: number[];
}

export interface CommunityInfo {
  id: string;
  name: string;
  color: string;
  darkColor: string;
}

export interface CameraState {
  x: number;
  y: number;
  zoom: number;
}

export interface GraphState {
  nodes: GraphNode[];
  edges: GraphEdge[];
  adj: Map<string, GraphEdge[]>;
  communities: Map<string, CommunityInfo>;
  maxDegree: number;
}

export const SHAPE_MAP: Record<EntityType, string> = {
  person: "circle",
  org: "roundRect",
  tech: "star",
  concept: "diamond",
  document: "rect",
  unknown: "circle",
};

export function classifyEntityType(raw: string): EntityType {
  const lower = raw.trim().toLowerCase();
  if (lower === "person" || lower === "people" || lower === "author" || lower === "researcher") return "person";
  if (lower === "organization" || lower === "org" || lower === "organisation" || lower === "company" || lower === "institution") return "org";
  if (lower === "technology" || lower === "tech" || lower === "tool" || lower === "framework" || lower === "system") return "tech";
  if (lower === "concept" || lower === "topic" || lower === "method" || lower === "technique" || lower === "algorithm") return "concept";
  if (lower === "document" || lower === "paper" || lower === "article" || lower === "publication" || lower === "file") return "document";
  return "unknown";
}
