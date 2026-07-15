import { describe, expect, it, vi } from "vitest";
import { createApiClient } from "./api";

describe("explorer API", () => {
  it("sends selected community level", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }), json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    await createApiClient({ projectId: "p", apiKey: "k" }).explorer("ds", 100, 200, 2);
    expect(fetchMock.mock.calls[0][0]).toContain("community_level=2");
  });
});
