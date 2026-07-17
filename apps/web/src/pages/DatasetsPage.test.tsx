import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import DatasetsPage from "./DatasetsPage";
import { useAuthStore } from "../store/auth";

function ok(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function makeFetch(handlers: {
  datasets?: unknown[];
  created?: unknown;
  docs?: () => unknown[];
  uploadedDoc?: unknown;
}) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url === "/api/v1/datasets" && method === "GET") return ok(handlers.datasets ?? []);
    if (url === "/api/v1/datasets" && method === "POST")
      return ok(handlers.created ?? { id: "ds_new", project_id: "p", name: "x", description: null, status: "active", error_message: null, metadata: {} }, 201);
    if (url.endsWith("/documents") && method === "GET") return ok(handlers.docs?.() ?? []);
    if (url.endsWith("/documents") && method === "POST")
      return ok(handlers.uploadedDoc ?? { id: "doc_1" }, 201);
    if (method === "DELETE") return ok(null, 204);
    return ok([]);
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <DatasetsPage />
    </MemoryRouter>,
  );
}

describe("DatasetsPage", () => {
  beforeEach(() => {
    useAuthStore.setState({
      apiKey: "ogm_key",
      projectId: "11111111-2222-3333-4444-555555555555",
      adminKey: "",
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
    useAuthStore.setState({ apiKey: "", projectId: "", adminKey: "" });
  });

  it("renders datasets from API", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetch({
        datasets: [
          { id: "ds_1", project_id: "p", name: "Research", description: null, status: "active", error_message: null, metadata: {} },
        ],
      }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("Research")).toBeInTheDocument());
  });

  it("creates a dataset and selects it", async () => {
    const fetchMock = makeFetch({
      datasets: [],
      created: { id: "ds_new", project_id: "p", name: "Notes", description: null, status: "active", error_message: null, metadata: {} },
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await waitFor(() => expect(screen.getByText("No datasets yet.")).toBeInTheDocument());
    await userEvent.type(screen.getByPlaceholderText("Dataset name"), "Notes");
    await userEvent.click(screen.getByRole("button", { name: "Create Dataset" }));
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Notes" })).toBeInTheDocument(),
    );
  });

  it("loads documents when a dataset is selected", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetch({
        datasets: [
          { id: "ds_1", project_id: "p", name: "Research", description: null, status: "active", error_message: null, metadata: {} },
        ],
        docs: () => [
          {
            id: "doc_1",
            project_id: "p",
            dataset_id: "ds_1",
            filename: "report.pdf",
            mime_type: "application/pdf",
            size_bytes: 2048,
            content_hash: "abc",
            object_key: "k",
            status: "indexed",
            error_message: null,
            graph_stage: "complete",
            duplicate: false,
            created_at: "t",
            updated_at: "t",
          },
        ],
      }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("Research")).toBeInTheDocument());
    await userEvent.click(screen.getByText("Research"));
    await waitFor(() => expect(screen.getByText("report.pdf")).toBeInTheDocument());
    expect(screen.getByText("indexed")).toBeInTheDocument();
  });

  it("uploads selected file with multipart auth request and refreshes documents", async () => {
    const uploadedDocument = {
      id: "doc_1",
      project_id: "p",
      dataset_id: "ds_1",
      filename: "notes.txt",
      mime_type: "text/plain",
      size_bytes: 12,
      content_hash: "abc",
      object_key: "k",
      status: "queued",
      error_message: null,
      graph_stage: null,
      duplicate: false,
      created_at: "t",
      updated_at: "t",
    };
    const fetchMock = makeFetch({
      datasets: [
        { id: "ds_1", project_id: "p", name: "Research", description: null, status: "active", error_message: null, metadata: {} },
      ],
      uploadedDoc: uploadedDocument,
      docs: () => {
        const uploadCall = fetchMock.mock.calls.some(
          ([url, init]) => url === "/api/v1/datasets/ds_1/documents" && init?.method === "POST",
        );
        return uploadCall ? [uploadedDocument] : [];
      },
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("Research"));
    const input = screen.getByLabelText("Select document to upload");
    const file = new File(["hello upload"], "notes.txt", { type: "text/plain" });
    await user.upload(input, file);

    await waitFor(() => expect(screen.getByText("notes.txt")).toBeInTheDocument());
    const [url, init] = fetchMock.mock.calls.find(
      ([requestUrl, requestInit]) => requestUrl === "/api/v1/datasets/ds_1/documents" && requestInit?.method === "POST",
    ) as [string, RequestInit];
    expect(url).toBe("/api/v1/datasets/ds_1/documents");
    expect(init.headers).toMatchObject({
      "X-API-Key": "ogm_key",
      "X-Project-Id": "11111111-2222-3333-4444-555555555555",
    });
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBe(file);
  });

  it("shows upload error and allows selecting same file again", async () => {
    let uploads = 0;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url === "/api/v1/datasets" && method === "GET") {
        return ok([
          { id: "ds_1", project_id: "p", name: "Research", description: null, status: "active", error_message: null, metadata: {} },
        ]);
      }
      if (url === "/api/v1/datasets/ds_1/documents" && method === "GET") return ok([]);
      if (url === "/api/v1/datasets/ds_1/documents" && method === "POST") {
        uploads += 1;
        return uploads === 1 ? ok({ detail: "invalid file" }, 415) : ok({ id: "doc_1" }, 201);
      }
      return ok([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("Research"));
    const input = screen.getByLabelText("Select document to upload");
    const file = new File(["hello upload"], "notes.txt", { type: "text/plain" });
    await user.upload(input, file);
    await waitFor(() => expect(screen.getByText("invalid file")).toBeInTheDocument());

    await user.upload(input, file);
    await waitFor(() => expect(uploads).toBe(2));
  });

  it("polls documents while a document is processing", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let docCalls = 0;
    const fetchMock = makeFetch({
      datasets: [
        { id: "ds_1", project_id: "p", name: "Research", description: null, status: "active", error_message: null, metadata: {} },
      ],
      docs: () => {
        docCalls += 1;
        return [
          {
            id: "doc_1",
            project_id: "p",
            dataset_id: "ds_1",
            filename: "report.pdf",
            mime_type: "application/pdf",
            size_bytes: 2048,
            content_hash: "abc",
            object_key: "k",
            status: docCalls <= 1 ? "queued" : "indexed",
            error_message: null,
            graph_stage: "complete",
            duplicate: false,
            created_at: "t",
            updated_at: "t",
          },
        ];
      },
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    // Initial dataset + first document load.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      // select dataset triggers document load
    });
    // Select the dataset.
    await act(async () => {
      screen.getByText("Research").click();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(docCalls).toBeGreaterThanOrEqual(1);
    // Advance past poll interval; should re-fetch and converge to indexed.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(docCalls).toBeGreaterThanOrEqual(2);
  });
});
