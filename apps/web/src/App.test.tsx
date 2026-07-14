import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { ApiError } from "./lib/api";
import { App } from "./App";

// Mock @xyflow/react to avoid SVG/canvas issues in jsdom.
vi.mock("@xyflow/react", () => ({
  ReactFlow: ({ nodes }: { nodes: { id: string; type?: string }[] }) => {
    const visibleNodes = nodes.filter((node) => node.type !== "bubble");
    return visibleNodes.length ? (
      <div data-testid="react-flow-mock">{visibleNodes.length} nodes</div>
    ) : (
      <div data-testid="react-flow-empty" />
    );
  },
  Background: () => null,
  Controls: () => null,
}));

function jsonResponse(data: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => data,
  };
}

function mockFetch(impl: (url: string, init?: RequestInit) => unknown): Mock {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const data = impl(url, init);
    if (data instanceof ApiError) {
      return jsonResponse({ detail: data.message }, false, data.status);
    }
    if (init?.method === "DELETE") {
      return { ok: true, status: 204, headers: new Headers(), json: async () => ({}) };
    }
    return jsonResponse(data);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function defaultFetchMock(): Mock {
  return mockFetch((url) => {
    if (url.endsWith("/v1/datasets")) return [];
    if (url.includes("/graph")) return { entity_count: 0, relation_count: 0, nodes: [], relations: [] };
    if (url.includes("/documents")) return [];
    return [];
  });
}

function connect() {
  fireEvent.change(screen.getByLabelText("Project ID"), { target: { value: "test-project-id" } });
  fireEvent.change(screen.getByLabelText("API Key"), { target: { value: "test-api-key" } });
  fireEvent.click(screen.getByRole("button", { name: /connect/i }));
}

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("App", () => {
  it("renders the dashboard title when not connected", () => {
    render(<App />);
    expect(
      screen.getByRole("heading", { name: "Dashboard & Trace Explorer", level: 1 }),
    ).toBeInTheDocument();
  });

  it("shows a connect prompt when no credentials are saved", () => {
    render(<App />);
    expect(screen.getByText("Connect to your project")).toBeInTheDocument();
  });

  it("stores credentials and loads datasets on connect", async () => {
    const fetchMock = defaultFetchMock();
    render(<App />);

    fireEvent.change(screen.getByLabelText("Project ID"), { target: { value: "my-project" } });
    fireEvent.change(screen.getByLabelText("API Key"), { target: { value: "ogm_secret" } });
    fireEvent.click(screen.getByRole("button", { name: /connect/i }));

    expect(localStorage.getItem("ogm.projectId")).toBe("my-project");
    expect(localStorage.getItem("ogm.apiKey")).toBe("ogm_secret");

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/v1/datasets"),
        expect.objectContaining({
          headers: expect.objectContaining({
            "X-Project-ID": "my-project",
            "X-API-Key": "ogm_secret",
          }),
        }),
      );
    });
  });

  it("sends auth headers on API requests after connecting", async () => {
    const fetchMock = defaultFetchMock();
    render(<App />);
    connect();

    await waitFor(() => {
      const datasetsCall = fetchMock.mock.calls.find(
        (c: unknown[]) => String(c[0]).includes("/v1/datasets"),
      );
      expect(datasetsCall).toBeTruthy();
      const [, init] = datasetsCall as [string, RequestInit];
      expect(init?.headers).toMatchObject({
        "X-Project-ID": "test-project-id",
        "X-API-Key": "test-api-key",
      });
    });
  });

  it("displays error banner when API returns an error", async () => {
    mockFetch(() => {
      throw new ApiError("Invalid project API key", 401);
    });
    render(<App />);

    fireEvent.change(screen.getByLabelText("Project ID"), { target: { value: "bad-project" } });
    fireEvent.change(screen.getByLabelText("API Key"), { target: { value: "bad-key" } });
    fireEvent.click(screen.getByRole("button", { name: /connect/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Invalid project API key");
    });
  });

  it("shows a clear error when /api returns HTML instead of JSON", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "text/html" }),
      json: async () => {
        throw new SyntaxError("Unexpected token '<'");
      },
    }));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    connect();

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("API returned HTML instead of JSON");
    });
  });

  it("shows query playground, trace inspector, documents, and graph sections after connect", async () => {
    defaultFetchMock();
    render(<App />);
    connect();

    await waitFor(() => {
      expect(screen.getByText("Ask the corpus")).toBeInTheDocument();
    });
    expect(screen.getByText("Run Inspector")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Documents", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Entity Network", level: 2 })).toBeInTheDocument();
  });

  it("disables the run query button when no dataset is selected", async () => {
    defaultFetchMock();
    render(<App />);
    connect();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /run query/i })).toBeDisabled();
    });
  });

  it("displays empty states for documents and graph", async () => {
    defaultFetchMock();
    render(<App />);
    connect();

    await waitFor(() => {
      expect(screen.getByText(/No documents yet/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Graph projection will appear/i)).toBeInTheDocument();
  });

  it("supports switching retrieval modes", async () => {
    defaultFetchMock();
    render(<App />);
    connect();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /run query/i })).toBeInTheDocument();
    });

    const vectorBtn = screen.getByRole("radio", { name: "Vector" });
    fireEvent.click(vectorBtn);
    expect(vectorBtn).toHaveAttribute("aria-checked", "true");
  });

  it("can dismiss the error banner", async () => {
    mockFetch(() => {
      throw new ApiError("Connection refused", 401);
    });
    render(<App />);

    fireEvent.change(screen.getByLabelText("Project ID"), { target: { value: "p" } });
    fireEvent.change(screen.getByLabelText("API Key"), { target: { value: "k" } });
    fireEvent.click(screen.getByRole("button", { name: /connect/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText("Dismiss error"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders query results with citations after a successful query", async () => {
    const fetchMock = mockFetch((url) => {
      if (url.endsWith("/v1/datasets"))
        return [{ id: "ds_1", project_id: "p", name: "Test DS", description: null, metadata: {}, status: "active", error_message: null }];
      if (url.includes("/graph"))
        return { dataset_id: "ds_1", entity_count: 2, relation_count: 1, nodes: [], relations: [] };
      if (url.includes("/documents")) return [];
      if (url.endsWith("/v1/query"))
        return {
          answer: "The answer is [1] based on the evidence.",
          citations: [
            { index: 1, chunk_id: "chk_1", document_id: "doc_1", score: 0.95, text: "Evidence text here." },
          ],
          retrieval_trace: {
            trace_id: "abc12345",
            mode: "hybrid",
            channel_candidates: { vector: [{ chunk_id: "chk_1", score: 0.9 }], graph: [] },
            fusion: [{ chunk_id: "chk_1", score: 0.88, channels: ["vector"] }],
            graph: { status: "not_requested", paths: [] },
            chunk_ids: ["chk_1"],
            scores: [0.88],
            latency_ms: 42.5,
          },
          usage: { prompt_tokens: 100, completion_tokens: 50, total_tokens: 150, estimated_cost_usd: 0.001 },
        };
      return [];
    });

    render(<App />);
    connect();

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Test DS" })).toBeInTheDocument();
    });

    const textarea = screen.getByLabelText("Question");
    fireEvent.change(textarea, { target: { value: "What is the answer?" } });
    fireEvent.click(screen.getByRole("button", { name: /run query/i }));

    await waitFor(() => {
      expect(screen.getAllByText((_, node) => node?.textContent === "The answer is [1] based on the evidence.").length).toBeGreaterThan(0);
    });
    expect(screen.getByText("Evidence text here.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/v1/query"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("preserves the last graph and updates documents when graph refresh fails", async () => {
    let graphCalls = 0;
    let documentCalls = 0;
    mockFetch((url) => {
      if (url.endsWith("/v1/datasets"))
        return [{ id: "ds_1", project_id: "p", name: "Test DS", description: null, metadata: {}, status: "active", error_message: null }];
      if (url.includes("/documents")) {
        documentCalls += 1;
        const first = { id: "doc_1", project_id: "p", dataset_id: "ds_1", filename: "source.pdf", mime_type: "application/pdf", size_bytes: 100, content_hash: "one", object_key: "one", status: "indexed", error_message: null, duplicate: false, created_at: "2026-01-01", updated_at: "2026-01-01" };
        const second = { ...first, id: "doc_2", filename: "new.txt", content_hash: "two" };
        return documentCalls === 1 ? [first] : [first, second];
      }
      if (url.includes("/graph")) {
        graphCalls += 1;
        if (graphCalls > 1) throw new ApiError("Graph projection unavailable", 503);
        return {
          dataset_id: "ds_1",
          entity_count: 2,
          relation_count: 0,
          nodes: [
            { id: "e1", dataset_id: "ds_1", canonical_name: "LBM", entity_type: "method", confidence: 1, version: 1, review_state: "accepted" },
            { id: "e2", dataset_id: "ds_1", canonical_name: "Darcy", entity_type: "method", confidence: 1, version: 1, review_state: "accepted" },
          ],
          relations: [],
        };
      }
      return [];
    });

    render(<App />);
    connect();

    await waitFor(() => expect(screen.getByTestId("react-flow-mock")).toHaveTextContent("2 nodes"));
    fireEvent.click(screen.getByTitle("Refresh graph"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Graph projection unavailable");
      expect(screen.getByText("new.txt")).toBeInTheDocument();
    });
    expect(screen.getByTestId("react-flow-mock")).toHaveTextContent("2 nodes");
    expect(screen.getByText("2 entities · 0 relations")).toBeInTheDocument();
  });

  it("preserves the last graph when a transient empty graph arrives during extraction", async () => {
    let graphCalls = 0;
    let documentCalls = 0;
    mockFetch((url) => {
      if (url.endsWith("/v1/datasets"))
        return [{ id: "ds_1", project_id: "p", name: "Test DS", description: null, metadata: {}, status: "active", error_message: null }];
      if (url.includes("/documents")) {
        documentCalls += 1;
        const doc = { id: "doc_1", project_id: "p", dataset_id: "ds_1", filename: "source.pdf", mime_type: "application/pdf", size_bytes: 100, content_hash: "one", object_key: "one", status: "indexed", error_message: null, graph_stage: documentCalls === 1 ? "complete" : "extracting", duplicate: false, created_at: "2026-01-01", updated_at: "2026-01-01" };
        return [doc];
      }
      if (url.includes("/graph")) {
        graphCalls += 1;
        return graphCalls === 1
          ? { dataset_id: "ds_1", entity_count: 1, relation_count: 0, nodes: [{ id: "e1", dataset_id: "ds_1", canonical_name: "LBM", entity_type: "method", confidence: 1, version: 1, review_state: "accepted" }], relations: [] }
          : { dataset_id: "ds_1", entity_count: 0, relation_count: 0, nodes: [], relations: [] };
      }
      return [];
    });

    render(<App />);
    connect();

    await waitFor(() => expect(screen.getByTestId("react-flow-mock")).toHaveTextContent("1 nodes"));
    fireEvent.click(screen.getByTitle("Refresh graph"));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("showing last available graph"));
    expect(screen.getByTestId("react-flow-mock")).toHaveTextContent("1 nodes");
  });

  it("keeps documents visible when initial graph loading fails", async () => {
    mockFetch((url) => {
      if (url.endsWith("/v1/datasets"))
        return [{ id: "ds_1", project_id: "p", name: "Test DS", description: null, metadata: {}, status: "active", error_message: null }];
      if (url.includes("/documents"))
        return [{ id: "doc_1", project_id: "p", dataset_id: "ds_1", filename: "source.pdf", mime_type: "application/pdf", size_bytes: 100, content_hash: "one", object_key: "one", status: "indexed", error_message: null, duplicate: false, created_at: "2026-01-01", updated_at: "2026-01-01" }];
      if (url.includes("/graph")) throw new ApiError("Graph service timed out", 504);
      return [];
    });

    render(<App />);
    connect();

    await waitFor(() => {
      expect(screen.getByText("source.pdf")).toBeInTheDocument();
      expect(screen.getByRole("alert")).toHaveTextContent("Graph service timed out");
    });
  });

  it("disables the delete dataset button when no dataset is selected", async () => {
    defaultFetchMock();
    render(<App />);
    connect();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /delete active dataset/i })).toBeDisabled();
    });
  });

  it("deletes the active dataset after confirmation and reloads the list", async () => {
    let listCall = 0;
    const fetchMock = mockFetch((url, init) => {
      if (init?.method === "DELETE") return;
      if (url.endsWith("/v1/datasets")) {
        listCall++;
        return listCall === 1
          ? [
              { id: "ds_1", project_id: "p", name: "Alpha", description: null, metadata: {}, status: "active", error_message: null },
              { id: "ds_2", project_id: "p", name: "Beta", description: null, metadata: {}, status: "active", error_message: null },
            ]
          : [
              { id: "ds_2", project_id: "p", name: "Beta", description: null, metadata: {}, status: "active", error_message: null },
            ];
      }
      if (url.includes("/graph"))
        return { dataset_id: "ds_1", entity_count: 0, relation_count: 0, nodes: [], relations: [] };
      if (url.includes("/documents")) return [];
      return [];
    });

    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);
    connect();

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Alpha" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /delete active dataset/i }));

    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining("Delete this dataset"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/v1/datasets/ds_1"),
        expect.objectContaining({ method: "DELETE" }),
      );
    });

    await waitFor(() => {
      expect(screen.queryByRole("option", { name: "Alpha" })).not.toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Beta" })).toBeInTheDocument();
    });

    confirmSpy.mockRestore();
  });

  it("does not send DELETE when the dataset deletion confirmation is cancelled", async () => {
    const fetchMock = mockFetch((url) => {
      if (url.endsWith("/v1/datasets"))
        return [{ id: "ds_1", project_id: "p", name: "Alpha", description: null, metadata: {}, status: "active", error_message: null }];
      if (url.includes("/graph"))
        return { dataset_id: "ds_1", entity_count: 0, relation_count: 0, nodes: [], relations: [] };
      if (url.includes("/documents")) return [];
      return [];
    });

    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<App />);
    connect();

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Alpha" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /delete active dataset/i }));

    const deleteCall = fetchMock.mock.calls.find(
      (c: unknown[]) => (c[1] as RequestInit | undefined)?.method === "DELETE",
    );
    expect(deleteCall).toBeUndefined();
    expect(screen.getByRole("option", { name: "Alpha" })).toBeInTheDocument();

    confirmSpy.mockRestore();
  });

  it("shows an error banner when dataset deletion fails", async () => {
    mockFetch((url, init) => {
      if (init?.method === "DELETE" && url.includes("/v1/datasets/"))
        throw new ApiError("dataset object deletion failed", 503);
      if (url.endsWith("/v1/datasets"))
        return [{ id: "ds_1", project_id: "p", name: "Alpha", description: null, metadata: {}, status: "active", error_message: null }];
      if (url.includes("/graph"))
        return { dataset_id: "ds_1", entity_count: 0, relation_count: 0, nodes: [], relations: [] };
      if (url.includes("/documents")) return [];
      return [];
    });

    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);
    connect();

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Alpha" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /delete active dataset/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("dataset object deletion failed");
    });

    confirmSpy.mockRestore();
  });

  it("clears the query result when the active dataset is deleted", async () => {
    let listCall = 0;
    mockFetch((url, init) => {
      if (init?.method === "DELETE") return;
      if (url.endsWith("/v1/datasets")) {
        listCall++;
        return listCall === 1
          ? [{ id: "ds_1", project_id: "p", name: "Alpha", description: null, metadata: {}, status: "active", error_message: null }]
          : [];
      }
      if (url.endsWith("/v1/query"))
        return {
          answer: "The answer is [1].",
          citations: [
            { index: 1, chunk_id: "chk_1", document_id: "doc_1", score: 0.9, text: "Evidence." },
          ],
          retrieval_trace: {
            trace_id: "abc12345",
            mode: "hybrid",
            channel_candidates: { vector: [{ chunk_id: "chk_1", score: 0.9 }], graph: [] },
            fusion: [{ chunk_id: "chk_1", score: 0.88, channels: ["vector"] }],
            graph: { status: "not_requested", paths: [] },
            chunk_ids: ["chk_1"],
            scores: [0.88],
            latency_ms: 10,
          },
          usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15, estimated_cost_usd: 0.001 },
        };
      if (url.includes("/graph"))
        return { dataset_id: "ds_1", entity_count: 0, relation_count: 0, nodes: [], relations: [] };
      if (url.includes("/documents")) return [];
      return [];
    });

    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);
    connect();

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Alpha" })).toBeInTheDocument();
    });

    const textarea = screen.getByLabelText("Question");
    fireEvent.change(textarea, { target: { value: "What is the answer?" } });
    fireEvent.click(screen.getByRole("button", { name: /run query/i }));

    await waitFor(() => {
      expect(screen.getAllByText((_, node) => node?.textContent === "The answer is [1].").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole("button", { name: /delete active dataset/i }));

    await waitFor(() => {
      expect(screen.queryAllByText((_, node) => node?.textContent === "The answer is [1].")).toHaveLength(0);
    });

    confirmSpy.mockRestore();
  });
});
