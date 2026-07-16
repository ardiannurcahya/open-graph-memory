import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { parseSseChunk, streamQuery } from "./stream";
import { useAuthStore } from "../store/auth";

describe("parseSseChunk", () => {
  it("parses event and JSON data", () => {
    const chunk = 'event: token\ndata: {"text":"Hello"}';
    const event = parseSseChunk(chunk);
    expect(event).toEqual({ event: "token", data: { text: "Hello" } });
  });

  it("defaults event to message", () => {
    const chunk = 'data: {"status":"ok"}';
    expect(parseSseChunk(chunk)).toEqual({ event: "message", data: { status: "ok" } });
  });

  it("joins multiline data", () => {
    const chunk = 'event: complete\ndata: {"a":1}\ndata: {"b":2}';
    const event = parseSseChunk(chunk);
    expect(event?.event).toBe("complete");
    // Joined raw string is not valid JSON, so data stays as string.
    expect(typeof event?.data).toBe("string");
  });

  it("returns null when no data line", () => {
    expect(parseSseChunk("event: status")).toBeNull();
  });
});

describe("streamQuery", () => {
  beforeEach(() => {
    useAuthStore.setState({
      apiKey: "ogm_key",
      projectId: "11111111-2222-3333-4444-555555555555",
      adminKey: "",
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ apiKey: "", projectId: "", adminKey: "" });
  });

  it("yields parsed events from the response stream", async () => {
    const encoder = new TextEncoder();
    const chunks = [
      'event: status\ndata: {"stage":"retrieving"}\n\n',
      'event: token\ndata: {"text":"Hi"}\n\n',
      'event: complete\ndata: {"answer":"Hi","citations":[],"retrieval_trace":{},"usage":{}}\n\n',
    ];
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        chunks.forEach((c) => controller.enqueue(encoder.encode(c)));
        controller.close();
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, body: stream }) as Response),
    );

    const events = [];
    for await (const event of streamQuery({ dataset_id: "ds", query: "q" })) {
      events.push(event);
    }
    expect(events.map((e) => e.event)).toEqual(["status", "token", "complete"]);
    expect(events[1].data).toEqual({ text: "Hi" });
  });

  it("throws ApiError on non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 401, json: async () => ({ detail: "bad" }) }) as Response),
    );
    await expect(streamQuery({ dataset_id: "ds", query: "q" }).next()).rejects.toMatchObject({
      status: 401,
      detail: "bad",
    });
  });
});
