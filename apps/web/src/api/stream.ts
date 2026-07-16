import { ApiError, defaultHeaders } from "./client";
import type { QueryRequest, QueryResponse } from "./types";

const BASE_URL = "/api";

export interface StreamEvent {
  event: string;
  data: unknown;
}

export function parseSseChunk(chunk: string): StreamEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (dataLines.length === 0) return null;
  const raw = dataLines.join("\n");
  try {
    return { event, data: JSON.parse(raw) };
  } catch {
    return { event, data: raw };
  }
}

export async function* streamQuery(
  body: QueryRequest,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const headers = defaultHeaders(false);
  headers["Content-Type"] = "application/json";
  const response = await fetch(`${BASE_URL}/v1/query/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    let detail = `request failed with status ${response.status}`;
    try {
      const errorBody = await response.json();
      if (typeof errorBody === "object" && errorBody && "detail" in errorBody) {
        detail = String((errorBody as { detail: unknown }).detail);
      }
    } catch {
      // Non-JSON error body.
    }
    throw new ApiError(response.status, detail);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let separator: number;
    while ((separator = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, separator);
      buffer = buffer.slice(separator + 2);
      const event = parseSseChunk(chunk);
      if (event) yield event;
    }
  }
}

export type { QueryResponse };
