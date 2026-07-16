import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { api, ApiError, defaultHeaders } from "./client";
import { useAuthStore } from "../store/auth";

const fakeResponse = (body: unknown, status = 200): Response =>
  ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }) as Response;

type FetchCall = [string, { headers: Record<string, string>; body?: string; method: string }];

describe("api client", () => {
  beforeEach(() => {
    useAuthStore.setState({
      apiKey: "ogm_testkey123456",
      projectId: "11111111-2222-3333-4444-555555555555",
      adminKey: "",
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ apiKey: "", projectId: "", adminKey: "" });
  });

  it("injects project auth headers on GET", async () => {
    const fetchMock = vi.fn(async () => fakeResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);
    await api.get("/health");
    const [url, init] = fetchMock.mock.calls[0] as unknown as FetchCall;
    expect(url).toBe("/api/health");
    expect(init.headers["X-API-Key"]).toBe("ogm_testkey123456");
    expect(init.headers["X-Project-Id"]).toBe("11111111-2222-3333-4444-555555555555");
  });

  it("sends JSON body with content type on POST", async () => {
    const fetchMock = vi.fn(async () => fakeResponse({ id: "ds_1" }, 201));
    vi.stubGlobal("fetch", fetchMock);
    await api.post("/v1/datasets", { json: { name: "docs" } });
    const [, init] = fetchMock.mock.calls[0] as unknown as FetchCall;
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({ name: "docs" });
  });

  it("uses admin key and omits project id for admin calls", () => {
    useAuthStore.setState({ adminKey: "admin-secret-key" });
    const headers = defaultHeaders(true);
    expect(headers["X-API-Key"]).toBe("admin-secret-key");
    expect(headers["X-Project-Id"]).toBeUndefined();
  });

  it("throws ApiError with detail on error response", async () => {
    const fetchMock = vi.fn(async () => fakeResponse({ detail: "dataset not found" }, 404));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.get("/v1/datasets/ds_missing")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      detail: "dataset not found",
    });
  });

  it("returns undefined for 204 no-content", async () => {
    const fetchMock = vi.fn(async () => fakeResponse(null, 204));
    vi.stubGlobal("fetch", fetchMock);
    const result = await api.del("/v1/datasets/ds_1");
    expect(result).toBeUndefined();
  });

  it("throws 401 ApiError when API key missing", () => {
    useAuthStore.setState({ apiKey: "", projectId: "" });
    expect(() => defaultHeaders(false)).toThrow(ApiError);
  });

  it("appends query params for GET requests", async () => {
    const fetchMock = vi.fn(async () => fakeResponse([]));
    vi.stubGlobal("fetch", fetchMock);
    await api.get("/v1/datasets/ds_1/documents", { params: { limit: 10, offset: undefined } });
    const [url] = fetchMock.mock.calls[0] as unknown as FetchCall;
    expect(url).toBe("/api/v1/datasets/ds_1/documents?limit=10");
  });
});
