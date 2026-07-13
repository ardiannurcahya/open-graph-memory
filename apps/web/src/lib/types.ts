/** TypeScript types mirroring the OpenGraphRAG backend API contracts (M0-M4). */

export type RetrievalMode = "vector_only" | "graph_only" | "hybrid";

export interface Credentials {
  projectId: string;
  apiKey: string;
}

// --- Datasets (POST/GET /v1/datasets) ---

export interface Dataset {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  metadata: Record<string, unknown>;
  status: string;
  error_message: string | null;
}

export interface DatasetInput {
  name: string;
  description?: string;
  metadata?: Record<string, unknown>;
}

// --- Documents (POST/GET /v1/datasets/{id}/documents) ---

export interface DocumentItem {
  id: string;
  project_id: string;
  dataset_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  content_hash: string;
  object_key: string;
  status: string;
  error_message: string | null;
  duplicate: boolean;
  created_at: string;
  updated_at: string;
}

// --- Query (POST /v1/query) ---

export interface QueryRequest {
  dataset_id: string;
  query: string;
  mode: RetrievalMode;
  top_k: number;
  graph_depth?: number;
  graph_fanout?: number;
  graph_timeout_ms?: number;
  fusion?: "rrf" | "weighted";
}

export interface Citation {
  index: number;
  chunk_id: string;
  document_id: string;
  score: number;
  text: string;
}

export interface ChannelCandidate {
  chunk_id: string;
  score: number;
}

export interface FusionEntry {
  chunk_id: string;
  score: number;
  channels: string[];
}

export interface GraphPath {
  chunk_id: string;
  path: string[];
  relation_ids: string[];
  evidence_chunk_ids: string[];
}

export interface GraphTrace {
  status: string;
  reason?: string;
  latency_ms?: number;
  paths: GraphPath[];
}

export interface RetrievalTrace {
  trace_id: string;
  mode: RetrievalMode;
  channel_candidates: {
    vector: ChannelCandidate[];
    graph: ChannelCandidate[];
  };
  fusion: FusionEntry[];
  graph: GraphTrace;
  chunk_ids: string[];
  scores: number[];
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

// --- Graph (GET /v1/datasets/{id}/graph) ---

export interface EntityView {
  id: string;
  dataset_id: string;
  canonical_name: string;
  entity_type: string;
  confidence: number;
  version: number;
  review_state: string;
}

export interface RelationCitation {
  dataset_id: string;
  document_id: string;
  chunk_id: string;
  quote: string;
}

export interface RelationView {
  id: string;
  dataset_id: string;
  source_entity_id: string;
  target_entity_id: string;
  relation_type: string;
  confidence: number;
  extractor_version: string;
  review_state: string;
  citations: RelationCitation[];
}

export interface GraphSummary {
  dataset_id: string;
  entity_count: number;
  relation_count: number;
  nodes: EntityView[];
  relations: RelationView[];
}

// --- Health (GET /ready) ---

export interface ReadinessCheck {
  status: string;
  checks: Record<string, boolean>;
}
