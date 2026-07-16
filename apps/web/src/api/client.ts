import { useAuthStore } from "../store/auth";

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

const BASE_URL = "/api";

type HeadersProvider = () => Record<string, string>;

function defaultHeaders(admin: boolean): Record<string, string> {
  const { apiKey, projectId, adminKey } = useAuthStore.getState();
  const key = admin && adminKey ? adminKey : apiKey;
  if (!key) {
    throw new ApiError(401, "missing API key");
  }
  const headers: Record<string, string> = { "X-API-Key": key };
  if (!admin) {
    if (!projectId) {
      throw new ApiError(401, "missing project ID");
    }
    headers["X-Project-Id"] = projectId;
  }
  return headers;
}

async function parseError(response: Response): Promise<ApiError> {
  let detail = `request failed with status ${response.status}`;
  try {
    const body = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      detail = String((body as { detail: unknown }).detail);
    }
  } catch {
    // Non-JSON error body; keep default detail.
  }
  return new ApiError(response.status, detail);
}

interface RequestOptions {
  admin?: boolean;
  json?: unknown;
  params?: Record<string, string | number | boolean | undefined>;
  signal?: AbortSignal;
  headersProvider?: HeadersProvider;
}

function buildUrl(path: string, params?: RequestOptions["params"]): string {
  const url = `${BASE_URL}${path}`;
  if (!params) return url;
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `${url}?${qs}` : url;
}

async function request<T>(
  method: string,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const provider = options.headersProvider ?? (() => defaultHeaders(options.admin ?? false));
  const headers = provider();
  let body: BodyInit | undefined;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }
  const response = await fetch(buildUrl(path, options.params), {
    method,
    headers,
    body,
    signal: options.signal,
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>("GET", path, options),
  post: <T>(path: string, options?: RequestOptions) => request<T>("POST", path, options),
  patch: <T>(path: string, options?: RequestOptions) => request<T>("PATCH", path, options),
  del: <T>(path: string, options?: RequestOptions) => request<T>("DELETE", path, options),

  upload: async <T>(
    path: string,
    file: File,
    options: { admin?: boolean; signal?: AbortSignal } = {},
  ): Promise<T> => {
    const provider = () => defaultHeaders(options.admin ?? false);
    const headers = provider();
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(buildUrl(path), {
      method: "POST",
      headers,
      body: form,
      signal: options.signal,
    });
    if (!response.ok) {
      throw await parseError(response);
    }
    return (await response.json()) as T;
  },
};

export { BASE_URL, defaultHeaders, buildUrl, request };
