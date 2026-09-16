import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import PlaygroundPage from "./PlaygroundPage";
import { useAuthStore } from "../store/auth";

function ok(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

const mockDatasets = [
  {
    id: "ds_engineering",
    project_id: "11111111-2222-3333-4444-555555555555",
    name: "Engineering Docs",
    description: "Technical specs",
    status: "active",
    error_message: null,
    metadata: {},
  },
];

const mockComparisonResult = {
  query: "How does pgvector work?",
  dataset_id: "ds_engineering",
  mode: "hybrid",
  latency_ms: 12.5,
  result: {
    mode: "hybrid",
    latency_ms: 4.2,
    total_chunks: 2,
    entities_found: ["PostgreSQL", "pgvector"],
    relations_found: ["PostgreSQL -[SUPPORTS]-> pgvector"],
    chunks: [
      {
        chunk_id: "chk_fused_1",
        document_id: "doc_1",
        content: "PostgreSQL pgvector provides HNSW index for high speed semantic similarity search.",
        score: 0.96,
        source: "hybrid",
        vector_score: 0.94,
        graph_score: 0.98,
        entities: ["PostgreSQL", "pgvector"],
        relations: ["PostgreSQL -[SUPPORTS]-> pgvector"],
      },
    ],
  },
  comparison: {
    vector: {
      mode: "vector",
      latency_ms: 2.1,
      total_chunks: 1,
      entities_found: [],
      relations_found: [],
      chunks: [
        {
          chunk_id: "chk_vec_1",
          document_id: "doc_1",
          content: "pgvector adds vector similarity search capabilities to PostgreSQL.",
          score: 0.91,
          source: "vector",
          vector_score: 0.91,
          entities: [],
          relations: [],
        },
      ],
    },
    graph: {
      mode: "graph",
      latency_ms: 6.2,
      total_chunks: 1,
      entities_found: ["PostgreSQL", "pgvector"],
      relations_found: ["PostgreSQL -[SUPPORTS]-> pgvector"],
      chunks: [
        {
          chunk_id: "chk_graph_1",
          document_id: "doc_1",
          content: "PostgreSQL knowledge graph tracks database extensions.",
          score: 0.88,
          source: "graph",
          graph_score: 0.88,
          entities: ["PostgreSQL"],
          relations: [],
        },
      ],
    },
    hybrid: {
      mode: "hybrid",
      latency_ms: 4.2,
      total_chunks: 1,
      entities_found: ["PostgreSQL", "pgvector"],
      relations_found: ["PostgreSQL -[SUPPORTS]-> pgvector"],
      chunks: [
        {
          chunk_id: "chk_fused_1",
          document_id: "doc_1",
          content: "PostgreSQL pgvector provides HNSW index for high speed semantic similarity search.",
          score: 0.96,
          source: "hybrid",
          vector_score: 0.94,
          graph_score: 0.98,
          entities: ["PostgreSQL", "pgvector"],
          relations: ["PostgreSQL -[SUPPORTS]-> pgvector"],
        },
      ],
    },
  },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <PlaygroundPage />
    </MemoryRouter>,
  );
}

describe("PlaygroundPage", () => {
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

  it("renders header and loads datasets", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/v1/datasets") return ok(mockDatasets);
        return ok([]);
      }),
    );

    renderPage();

    expect(screen.getByText("RAG Comparison Playground")).toBeInTheDocument();
    expect(screen.getByText("Explore the Power of Hybrid Retrieval")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Engineering Docs/i })).toBeInTheDocument();
    });
  });

  it("performs side-by-side compare retrieval and displays 3 columns", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/datasets") return ok(mockDatasets);
      if (url === "/api/v1/retrieval/query" && init?.method === "POST") {
        return ok(mockComparisonResult);
      }
      return ok([]);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Engineering Docs/i })).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText(/Enter prompt or technical question/i);
    await user.type(input, "How does pgvector work?");

    const retrieveBtn = screen.getByRole("button", { name: /Retrieve/i });
    await user.click(retrieveBtn);

    // Wait for search response
    await waitFor(() => {
      expect(screen.getByText("Overall Execution Latency:")).toBeInTheDocument();
    });

    // Check all 3 columns rendered
    expect(screen.getByRole("heading", { name: "Vector RAG" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "GraphRAG" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Hybrid RAG" })).toBeInTheDocument();

    // Check attribution badge on fused chunk
    expect(screen.getByText("Fused (Both)")).toBeInTheDocument();
  });

  it("populates search query when clicking an example preset", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/v1/datasets") return ok(mockDatasets);
        if (url === "/api/v1/retrieval/query") return ok(mockComparisonResult);
        return ok([]);
      }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Engineering Docs/i })).toBeInTheDocument();
    });

    const exampleBtn = screen.getByRole("button", { name: /How does pgvector dense semantic search work\?/i });
    await user.click(exampleBtn);

    const input = screen.getByPlaceholderText(/Enter prompt or technical question/i) as HTMLInputElement;
    expect(input.value).toBe("How does pgvector dense semantic search work?");
  });
});
