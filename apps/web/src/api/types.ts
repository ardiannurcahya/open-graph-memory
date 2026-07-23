export interface ProjectCreated {
  id: string;
  name: string;
  api_key: string;
}

export interface Dataset {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  status: string;
  error_message: string | null;
  metadata: Record<string, unknown>;
}

export interface DatasetInput {
  name: string;
  description?: string | null;
  metadata?: Record<string, unknown>;
}

export type DatasetPatch = Partial<DatasetInput>;

export type DocumentStatus =
  | "pending_upload"
  | "uploaded"
  | "storage_failed"
  | "queued"
  | "parsing"
  | "chunking"
  | "persisting"
  | "indexed"
  | "failed"
  | "cancelled"
  | "stale"
  | "deleting"
  | "delete_failed";

export interface Document {
  id: string;
  project_id: string;
  dataset_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  content_hash: string;
  object_key: string;
  status: DocumentStatus;
  error_message: string | null;
  graph_stage: string | null;
  duplicate: boolean;
  created_at: string;
  updated_at: string;
}

export interface SourceLocation {
  page_number?: number;
  record_number?: number;
  segment_part?: number;
}

export type ReviewState = "unreviewed" | "approved" | "rejected" | "needs_review";

export interface EntityView {
  id: string;
  dataset_id: string;
  canonical_name: string;
  entity_type: string;
  confidence: number;
  version: number;
  review_state: ReviewState;
  valid_from: string | null;
  valid_until: string | null;
  superseded_by: string | null;
}

export interface CitationRef {
  dataset_id: string;
  document_id: string;
  chunk_id: string;
  quote: string;
  source_location: SourceLocation | null;
}

export interface RelationView {
  id: string;
  dataset_id: string;
  source_entity_id: string;
  target_entity_id: string;
  relation_type: string;
  confidence: number;
  extractor_version: string;
  review_state: ReviewState;
  valid_from: string | null;
  valid_until: string | null;
  superseded_by: string | null;
  citations: CitationRef[];
}

export interface NeighborView {
  relation: RelationView;
  entity: EntityView;
}

export interface GraphSummary {
  dataset_id: string;
  entity_count: number;
  relation_count: number;
  nodes: EntityView[];
  relations: RelationView[];
}

export interface GraphPathView {
  dataset_id: string;
  source_entity_id: string;
  target_entity_id: string;
  found: boolean;
  hops: number;
  nodes: EntityView[];
  relations: RelationView[];
}

export interface GraphSubgraphView {
  dataset_id: string;
  root_entity_id: string;
  depth: number;
  nodes: EntityView[];
  relations: RelationView[];
}

export interface ExplorerNode {
  id: string;
  canonical_name: string;
  entity_type: string;
  community_id: string | null;
  degree: number;
  weighted_degree: number;
  importance: number;
}

export interface ExplorerRelation {
  id: string;
  source: string;
  target: string;
  type: string;
  weight: number;
  confidence: number;
}

export interface ExplorerCommunity {
  id: string;
  entity_count: number;
  parent_id: string | null;
  child_ids: string[];
  internal_edges: number;
  external_edges: number;
  density: number;
  importance: number;
}

export interface ExplorerStats {
  entity_count: number;
  relation_count: number;
  density: number;
}

export interface ExplorerAnalyticsView {
  id: string;
  dataset_id: string;
  snapshot_hash: string;
  entity_count: number;
  relation_count: number;
  community_count: number;
  levels: number;
  algorithm_version: string;
  created_at: string | null;
  stale: boolean;
}

export interface ExplorerView {
  dataset_id: string;
  community_level: number;
  available_levels: number[];
  analytics: ExplorerAnalyticsView | null;
  refresh_required: boolean;
  stats: ExplorerStats;
  nodes: ExplorerNode[];
  relations: ExplorerRelation[];
  communities: ExplorerCommunity[];
}

export interface ExplorerNodePage {
  nodes: ExplorerNode[];
  next_cursor: string | null;
}

export interface ExplorerRelationPage {
  relations: ExplorerRelation[];
  next_cursor: string | null;
}

export interface AnalyticsRunView {
  id: string;
  dataset_id: string;
  snapshot_hash: string;
  entity_count: number;
  relation_count: number;
  community_count: number;
  levels: number;
  algorithm_version: string;
}

export interface EvidenceView {
  id: string;
  dataset_id: string;
  document_id: string;
  chunk_id: string;
  quote: string;
  run_id: string;
  entity_id: string | null;
  relation_id: string | null;
  confidence: number;
  start_offset: number | null;
  end_offset: number | null;
  source_location: SourceLocation | null;
}

export interface GraphRunView {
  id: string;
  dataset_id: string;
  document_id: string;
  chunk_id: string;
  status: string;
  provider: string;
  model: string;
  extractor_version: string;
  prompt_version: string;
  ontology_version: string | null;
  error_message: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface GraphJobView {
  id: string;
  dataset_id: string;
  document_id: string;
  status: string;
  attempt: number;
  max_attempts: number;
  error_message: string | null;
  provider: string;
  model: string;
  extractor_version: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface HealthStatus {
  status: string;
  checks?: Record<string, boolean>;
}

export interface AgentMemoryAttempt {
  id: string;
  sequence: number;
  hypothesis: string;
  actions: unknown[];
  result: "success" | "failed" | "partial";
  notes: string | null;
  metadata: Record<string, unknown>;
}

export interface AgentMemoryEpisode {
  id: string;
  project_id: string;
  domain: "engineering" | "trading" | "research" | "operations" | "custom";
  title: string;
  goal: string;
  problem_signature: string;
  scope: Record<string, unknown>;
  tags: string[];
  metadata: Record<string, unknown>;
  status: "open" | "active" | "degraded" | "superseded" | "rejected";
  feedback_score: number;
  superseded_by_id: string | null;
  attempts: AgentMemoryAttempt[];
}

export interface AgentMemorySearchResult {
  episode: AgentMemoryEpisode;
  pattern: {
    pattern_key: string;
    verified_outcomes: number;
    weighted_successes: number;
    weighted_total: number;
    confidence: number;
    promoted: boolean;
  } | null;
  recommended_actions: unknown[];
  lesson: string | null;
  scope_match: boolean;
}

export interface AgentMemorySearchResponse {
  query: string;
  results: AgentMemorySearchResult[];
}

export type MemoryNodeType = "episode" | "attempt" | "outcome" | "pattern" | "verifier" | "evidence";
export type MemoryEdgeType = "has_attempt" | "has_outcome" | "matches_pattern" | "verified_by" | "has_evidence" | "supersedes";

export interface MemoryGraphNode {
  id: string;
  type: MemoryNodeType;
  label: string;
  status: string | null;
  domain: string | null;
  metadata: Record<string, unknown>;
}

export interface MemoryGraphEdge {
  id: string;
  source: string;
  target: string;
  type: MemoryEdgeType;
}

export interface MemoryGraphView {
  nodes: MemoryGraphNode[];
  edges: MemoryGraphEdge[];
  stats: {
    episodes: number;
    attempts: number;
    outcomes: number;
    patterns: number;
    verifiers: number;
    evidence: number;
  };
}
