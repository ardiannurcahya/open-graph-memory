import { api } from "./client";
import type {
  AnalyticsRunView,
  Dataset,
  DatasetInput,
  DatasetPatch,
  Document,
  EntityView,
  EvidenceView,
  ExplorerView,
  GraphJobView,
  GraphPathView,
  GraphRunView,
  GraphSummary,
  GraphSubgraphView,
  HealthStatus,
  NeighborView,
  ProjectCreated,
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

export const graphApi = {
  searchEntities: (datasetId: string, q: string, entityType?: string, limit = 25) =>
    api.get<EntityView[]>(`/v1/datasets/${datasetId}/entities/search`, {
      params: { q, entity_type: entityType, limit },
    }),
  getEntity: (id: string) => api.get<EntityView>(`/v1/entities/${id}`),
  getNeighbors: (id: string, limit = 25) =>
    api.get<NeighborView[]>(`/v1/entities/${id}/neighbors`, { params: { limit } }),
  refreshAnalytics: (datasetId: string) =>
    api.post<AnalyticsRunView>(`/v1/datasets/${datasetId}/analytics/refresh`),
  getGraph: (datasetId: string, limit = 100, depth = 1) =>
    api.get<GraphSummary>(`/v1/datasets/${datasetId}/graph`, { params: { limit, depth } }),
  findPath: (datasetId: string, sourceEntityId: string, targetEntityId: string, maxDepth = 3, relationLimit = 100) =>
    api.get<GraphPathView>(`/v1/datasets/${datasetId}/graph/path`, {
      params: {
        source_entity_id: sourceEntityId,
        target_entity_id: targetEntityId,
        max_depth: maxDepth,
        relation_limit: relationLimit,
      },
    }),
  getSubgraph: (datasetId: string, entityId: string, depth = 1, nodeLimit = 100, relationLimit = 200) =>
    api.get<GraphSubgraphView>(`/v1/datasets/${datasetId}/graph/subgraph`, {
      params: { entity_id: entityId, depth, node_limit: nodeLimit, relation_limit: relationLimit },
    }),
  getExplorer: (
    datasetId: string,
    params: { node_limit?: number; relation_limit?: number; community_level?: number } = {},
  ) => api.get<ExplorerView>(`/v1/datasets/${datasetId}/graph/explorer`, { params }),
  getEvidence: (id: string) => api.get<EvidenceView>(`/v1/evidence/${id}`),
  getRelationEvidence: (datasetId: string, relationId: string, limit = 25) =>
    api.get<EvidenceView[]>(`/v1/datasets/${datasetId}/relations/${relationId}/evidence`, {
      params: { limit },
    }),
  getRun: (id: string) => api.get<GraphRunView>(`/v1/graph-runs/${id}`),
  getJob: (id: string) => api.get<GraphJobView>(`/v1/graph-jobs/${id}`),
  reviewRelation: (id: string, reviewState: "approved" | "rejected") =>
    api.patch<RelationView>(`/v1/relations/${id}/review`, { json: { review_state: reviewState } }),
};

export const healthApi = {
  health: () => api.get<HealthStatus>("/health"),
  ready: () => api.get<HealthStatus>("/ready"),
};
