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
  | "embedding"
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

export type QueryMode =
  | "vector_only"
  | "graph_only"
  | "graph_local"
  | "graph_global"
  | "hybrid";

export type FusionMode = "rrf" | "weighted";

export interface QueryRequest {
  dataset_id: string;
  query: string;
  mode?: QueryMode;
  include_communities?: boolean | null;
  community_level?: number | null;
  top_k?: number;
  graph_depth?: number | null;
  graph_fanout?: number | null;
  graph_timeout_ms?: number | null;
  fusion?: FusionMode | null;
  memory_user_id?: string | null;
  memory_agent_id?: string | null;
  memory_session_id?: string | null;
  memory_top_k?: number;
}

export interface SourceLocation {
  page_number?: number;
  record_number?: number;
  segment_part?: number;
}

export interface Citation {
  index: number;
  chunk_id: string;
  document_id: string;
  score: number;
  text: string;
  source_location: SourceLocation | null;
}

export interface RetrievalTrace {
  trace_id: string;
  mode: string;
  requested_mode: string;
  resolved_mode: string;
  intent: string;
  channel_candidates: {
    vector: { chunk_id: string; score: number }[];
    graph: { chunk_id: string; score: number }[];
    community: { chunk_id: string; score: number }[];
  };
  fusion: unknown[];
  graph: {
    status: string;
    paths_found: number;
    evidence_chunk_ids: number;
    hydrated_chunks: number;
    missing_chunks: number;
    paths: {
      chunk_id: string;
      path: string[];
      relation_ids: string[];
      evidence_chunk_ids: string[];
    }[];
    [key: string]: unknown;
  };
  community: {
    status: string;
    report_ids: string[];
    [key: string]: unknown;
  };
  chunk_ids: string[];
  scores: number[];
  timings_ms: {
    vector: number;
    graph: number;
    hydrate: number;
    generation: number;
  };
  memory: {
    fact_ids: string[];
    scopes: string[];
    source_message_ids: (string | null)[];
  };
  latency_ms: number;
}

export interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
}

export interface QueryResponse {
  answer: string;
  citations: Citation[];
  retrieval_trace: RetrievalTrace;
  usage: Usage;
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

export interface CommunityReportView {
  id: string;
  job_id: string;
  dataset_id: string;
  analytics_run_id: string;
  community_id: string;
  level: number;
  title: string;
  summary: string;
  key_points: unknown[];
  evidence_chunk_ids: string[];
}

export interface CommunityReportJobView {
  id: string;
  dataset_id: string;
  analytics_run_id: string;
  community_id: string;
  level: number;
  status: string;
  attempts: number;
  max_attempts: number;
  error_message: string | null;
}

export type MemoryScope = "user" | "agent" | "session";
export type MessageRole = "system" | "user" | "assistant" | "tool";

export interface MemoryUser {
  id: string;
  project_id: string;
  external_id: string;
  display_name: string | null;
  metadata: Record<string, unknown>;
}

export interface MemoryAgent {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  metadata: Record<string, unknown>;
}

export interface MemorySession {
  id: string;
  project_id: string;
  user_id: string;
  agent_id: string;
  title: string | null;
  metadata: Record<string, unknown>;
  archived_at: string | null;
}

export interface MemoryMessage {
  id: string;
  project_id: string;
  session_id: string;
  role: MessageRole;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface MemoryFact {
  id: string;
  project_id: string;
  user_id: string | null;
  agent_id: string | null;
  session_id: string | null;
  scope: MemoryScope;
  subject: string;
  predicate: string;
  value: string;
  content: string;
  confidence: number;
  status: string;
  supersedes_id: string | null;
  source_message_id: string | null;
  provenance: Record<string, unknown>;
  metadata: Record<string, unknown>;
  valid_from: string;
  valid_until: string | null;
  deleted_at: string | null;
}

export interface MemoryFactInput {
  scope?: MemoryScope;
  subject: string;
  predicate: string;
  value: string;
  confidence?: number;
  metadata?: Record<string, unknown>;
}

export interface MemoryMessageInput {
  role: MessageRole;
  content: string;
  metadata?: Record<string, unknown>;
}

export interface MessageBatchInput {
  messages: MemoryMessageInput[];
  facts?: MemoryFactInput[];
}

export interface MessageBatchView {
  messages: MemoryMessage[];
  facts: MemoryFact[];
}

export interface MemorySearchInput {
  query: string;
  user_id?: string | null;
  agent_id?: string | null;
  session_id?: string | null;
  scopes?: MemoryScope[];
  limit?: number;
  include_superseded?: boolean;
}

export interface MemorySearchHit extends MemoryFact {
  score: number;
  matched_terms: string[];
}

export interface HealthStatus {
  status: string;
  checks?: Record<string, boolean>;
}
