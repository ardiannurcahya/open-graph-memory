/** Typed API client for the OpenGraphRAG backend, preserving M0-M4 contracts. */

import type {
  Dataset,
  DatasetInput,
  DocumentItem,
  GraphSummary,
  QueryRequest,
  QueryResponse,
  ReadinessCheck,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getApiBase(): string {
  return API_BASE;
}

interface ClientOptions {
  projectId: string;
  apiKey: string;
}

export type QueryStreamEvent =
  | { event: "status"; data: { stage: string } }
  | { event: "token"; data: { text: string } }
  | { event: "complete"; data: QueryResponse }
  | { event: "error"; data: { message: string; status: number } };

export function createApiClient(opts: ClientOptions) {
  const headers = (body?: BodyInit | null): Record<string, string> => ({
    "X-Project-ID": opts.projectId,
    "X-API-Key": opts.apiKey,
    ...(body instanceof FormData ? {} : { "Content-Type": "application/json" }),
  });

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { ...headers(init.body), ...init.headers },
    });
    const contentType = response.headers.get("content-type") ?? "";
    if (!response.ok) {
      const body = contentType.includes("application/json") ? await response.json().catch(() => ({})) : {};
      const detail =
        typeof body.detail === "string"
          ? body.detail
          : Array.isArray(body.detail)
            ? body.detail.map((d: { msg?: string }) => d.msg ?? String(d)).join("; ")
            : `Request failed (${response.status})`;
      throw new ApiError(detail, response.status);
    }
    if (response.status === 204) return undefined as T;
    if (!contentType.includes("application/json")) {
      throw new ApiError("API returned HTML instead of JSON. Check that the web proxy is routing /api to the backend.", 502);
    }
    return (await response.json()) as T;
  }

  async function streamQuery(input: QueryRequest, onEvent: (event: QueryStreamEvent) => void) {
    const response = await fetch(`${API_BASE}/v1/query/stream`, {
      method: "POST",
      body: JSON.stringify(input),
      headers: headers(JSON.stringify(input)),
    });
    if (!response.ok || !response.body) {
      const contentType = response.headers.get("content-type") ?? "";
      const body = contentType.includes("application/json") ? await response?.json?.().catch(() => ({})) : {};
      throw new ApiError(typeof body.detail === "string" ? body.detail : "Streaming query failed", response.status);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        const event = part.match(/^event: (.+)$/m)?.[1];
        const data = part.match(/^data: (.+)$/m)?.[1];
        if (!event || !data) continue;
        onEvent({ event, data: JSON.parse(data) } as QueryStreamEvent);
      }
    }
  }

  return {
    // Health
    readiness: () => request<ReadinessCheck>("/ready"),

    // Datasets
    listDatasets: () => request<Dataset[]>("/v1/datasets"),
    createDataset: (input: DatasetInput) =>
      request<Dataset>("/v1/datasets", { method: "POST", body: JSON.stringify(input) }),
    deleteDataset: (id: string) =>
      request<void>(`/v1/datasets/${id}`, { method: "DELETE" }),

    // Documents
    listDocuments: (datasetId: string) =>
      request<DocumentItem[]>(`/v1/datasets/${datasetId}/documents`),
    uploadDocument: (datasetId: string, file: File) => {
      const body = new FormData();
      body.append("file", file);
      return request<DocumentItem>(`/v1/datasets/${datasetId}/documents`, {
        method: "POST",
        body,
      });
    },
    deleteDocument: (id: string) =>
      request<void>(`/v1/documents/${id}`, { method: "DELETE" }),

    // Query
    query: (input: QueryRequest) =>
      request<QueryResponse>("/v1/query", { method: "POST", body: JSON.stringify(input) }),
    streamQuery,

    // Graph
    graph: (datasetId: string, limit = 100, depth = 1) =>
      request<GraphSummary>(`/v1/datasets/${datasetId}/graph?limit=${limit}&depth=${depth}`),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Unexpected request failure";
}
