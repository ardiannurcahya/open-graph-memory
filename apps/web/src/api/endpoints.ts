import { api } from "./client";
import type {
  AnalyticsRunView,
  CommunityReportJobView,
  CommunityReportView,
  Dataset,
  DatasetInput,
  DatasetPatch,
  Document,
  EntityView,
  EvidenceView,
  ExplorerView,
  GraphJobView,
  GraphRunView,
  GraphSummary,
  HealthStatus,
  MemoryAgent,
  MemoryFact,
  MemorySearchHit,
  MemorySearchInput,
  MemorySession,
  MemoryUser,
  MessageBatchInput,
  MessageBatchView,
  NeighborView,
  ProjectCreated,
  QueryRequest,
  QueryResponse,
  RelationView,
} from "./types";

export const projectsApi = {
  create: (name: string) =>
    api.post<ProjectCreated>("/v1/projects", { admin: true, json: { name } }),
};

export const datasetsApi = {
  list: () => api.get<Dataset[]>("/v1/datasets"),
  get: (id: string) => api.get<Dataset>(`/v1/datasets/${id}`),
  create: (body: DatasetInput) => api.post<Dataset>("/v1/datasets", { json: body }),
  update: (id: string, body: DatasetPatch) =>
    api.patch<Dataset>(`/v1/datasets/${id}`, { json: body }),
  delete: (id: string) => api.del<void>(`/v1/datasets/${id}`),
};

export const documentsApi = {
  list: (datasetId: string) =>
    api.get<Document[]>(`/v1/datasets/${datasetId}/documents`),
  get: (datasetId: string, documentId: string) =>
    api.get<Document>(`/v1/datasets/${datasetId}/documents/${documentId}`),
  getById: (documentId: string) => api.get<Document>(`/v1/documents/${documentId}`),
  upload: (datasetId: string, file: File) =>
    api.upload<Document>(`/v1/datasets/${datasetId}/documents`, file),
  delete: (documentId: string) => api.del<void>(`/v1/documents/${documentId}`),
};

export const queryApi = {
  query: (body: QueryRequest) => api.post<QueryResponse>("/v1/query", { json: body }),
};

export const graphApi = {
  getEntity: (id: string) => api.get<EntityView>(`/v1/entities/${id}`),
  getNeighbors: (id: string, limit = 25) =>
    api.get<NeighborView[]>(`/v1/entities/${id}/neighbors`, { params: { limit } }),
  refreshAnalytics: (datasetId: string) =>
    api.post<AnalyticsRunView>(`/v1/datasets/${datasetId}/analytics/refresh`),
  getGraph: (datasetId: string, limit = 100, depth = 1) =>
    api.get<GraphSummary>(`/v1/datasets/${datasetId}/graph`, { params: { limit, depth } }),
  getExplorer: (
    datasetId: string,
    params: { node_limit?: number; relation_limit?: number; community_level?: number } = {},
  ) => api.get<ExplorerView>(`/v1/datasets/${datasetId}/graph/explorer`, { params }),
  getEvidence: (id: string) => api.get<EvidenceView>(`/v1/evidence/${id}`),
  getRun: (id: string) => api.get<GraphRunView>(`/v1/graph-runs/${id}`),
  getJob: (id: string) => api.get<GraphJobView>(`/v1/graph-jobs/${id}`),
  reviewRelation: (id: string, reviewState: "approved" | "rejected") =>
    api.patch<RelationView>(`/v1/relations/${id}/review`, { json: { review_state: reviewState } }),
  listCommunityReports: (datasetId: string, communityLevel = 0) =>
    api.get<CommunityReportView[]>(`/v1/datasets/${datasetId}/community-reports`, {
      params: { community_level: communityLevel },
    }),
  getCommunityReport: (datasetId: string, reportId: string) =>
    api.get<CommunityReportView>(`/v1/datasets/${datasetId}/community-reports/${reportId}`),
  listCommunityReportJobs: (datasetId: string) =>
    api.get<CommunityReportJobView[]>(`/v1/datasets/${datasetId}/community-report-jobs`),
};

export const memoryApi = {
  createUser: (externalId: string, displayName?: string, metadata?: Record<string, unknown>) =>
    api.post<MemoryUser>("/v1/memory/users", {
      json: { external_id: externalId, display_name: displayName, metadata: metadata ?? {} },
    }),
  createAgent: (name: string, description?: string, metadata?: Record<string, unknown>) =>
    api.post<MemoryAgent>("/v1/memory/agents", {
      json: { name, description, metadata: metadata ?? {} },
    }),
  createSession: (
    userId: string,
    agentId: string,
    title?: string,
    metadata?: Record<string, unknown>,
  ) =>
    api.post<MemorySession>("/v1/memory/sessions", {
      json: { user_id: userId, agent_id: agentId, title, metadata: metadata ?? {} },
    }),
  addMessages: (sessionId: string, body: MessageBatchInput) =>
    api.post<MessageBatchView>(`/v1/memory/sessions/${sessionId}/messages`, { json: body }),
  getSessionMemory: (sessionId: string) =>
    api.get<MemoryFact[]>(`/v1/memory/sessions/${sessionId}/memory`),
  getUserContext: (userId: string, limit = 20) =>
    api.get<MemoryFact[]>(`/v1/memory/users/${userId}/context`, { params: { limit } }),
  search: (body: MemorySearchInput) =>
    api.post<MemorySearchHit[]>("/v1/memory/search", { json: body }),
  delete: (id: string) => api.del<void>(`/v1/memory/${id}`),
};

export const healthApi = {
  health: () => api.get<HealthStatus>("/health"),
  ready: () => api.get<HealthStatus>("/ready"),
};
