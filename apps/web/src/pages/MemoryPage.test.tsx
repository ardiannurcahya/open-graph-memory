import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import MemoryPage from "./MemoryPage";
import { useAuthStore } from "../store/auth";
import { useMemoryStore } from "../store/memory";

function ok(body: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <MemoryPage />
    </MemoryRouter>,
  );
}

describe("MemoryPage", () => {
  beforeEach(() => {
    useAuthStore.setState({
      apiKey: "ogm_key",
      projectId: "11111111-2222-3333-4444-555555555555",
      adminKey: "",
    });
    useMemoryStore.setState({ users: [], agents: [], sessions: [] });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ apiKey: "", projectId: "", adminKey: "" });
    useMemoryStore.setState({ users: [], agents: [], sessions: [] });
  });

  it("switches between tabs", async () => {
    renderPage();
    expect(screen.getByText("Create User")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Session" }));
    expect(screen.getByText("Add Message")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(screen.getByText("Search Memory")).toBeInTheDocument();
  });

  it("creates a user and lists it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url === "/api/v1/memory/users" && init?.method === "POST")
          return ok({
            id: "usr_1",
            project_id: "p",
            external_id: "u-100",
            display_name: "Alice",
            metadata: {},
          }, 201);
        return ok([]);
      }),
    );
    renderPage();
    await userEvent.type(screen.getByPlaceholderText("External ID"), "u-100");
    await userEvent.type(screen.getByPlaceholderText("Display name (optional)"), "Alice");
    await userEvent.click(screen.getAllByRole("button", { name: "Create" })[0]);
    await waitFor(() =>
      expect(screen.getAllByText("u-100").length).toBeGreaterThanOrEqual(1),
    );
  });

  it("searches memory and shows results", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url === "/api/v1/memory/search" && init?.method === "POST")
          return ok([
            {
              id: "mem_1",
              project_id: "p",
              user_id: null,
              agent_id: null,
              session_id: null,
              scope: "user",
              subject: "Alice",
              predicate: "likes",
              value: "tea",
              content: "Alice likes: tea",
              confidence: 100,
              status: "active",
              supersedes_id: null,
              source_message_id: null,
              provenance: { source: "api" },
              metadata: {},
              valid_from: "2026-01-01T00:00:00",
              valid_until: null,
              deleted_at: null,
              score: 1.0,
              matched_terms: ["alice", "tea"],
            },
          ]);
        return ok([]);
      }),
    );
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await userEvent.type(screen.getByPlaceholderText("Search query"), "alice tea");
    await userEvent.click(screen.getByRole("button", { name: "Run Search" }));
    await waitFor(() => expect(screen.getByText(/score 1\.00/)).toBeInTheDocument());
    expect(screen.getByText(/Alice likes: tea/)).toBeInTheDocument();
  });

  it("adds a message to a session and shows memory", async () => {
    useMemoryStore.setState({
      users: [{ id: "usr_1", external_id: "u-100", display_name: "Alice" }],
      agents: [{ id: "agt_1", name: "bot" }],
      sessions: [{ id: "ses_1", user_id: "usr_1", agent_id: "agt_1", title: "chat" }],
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.includes("/messages") && init?.method === "POST")
          return ok({ messages: [], facts: [] }, 201);
        if (url.includes("/memory") && (init?.method ?? "GET") === "GET")
          return ok([
            {
              id: "mem_1",
              project_id: "p",
              user_id: "usr_1",
              agent_id: "agt_1",
              session_id: "ses_1",
              scope: "user",
              subject: "Alice",
              predicate: "likes",
              value: "tea",
              content: "Alice likes: tea",
              confidence: 100,
              status: "active",
              supersedes_id: null,
              source_message_id: null,
              provenance: { source: "message" },
              metadata: {},
              valid_from: "2026-01-01T00:00:00",
              valid_until: null,
              deleted_at: null,
            },
          ]);
        return ok([]);
      }),
    );
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: "Session" }));
    await userEvent.selectOptions(screen.getByDisplayValue("Select session…"), "ses_1");
    await waitFor(() => expect(screen.getByText(/Alice likes: tea/)).toBeInTheDocument());
    await userEvent.type(screen.getByPlaceholderText("Message content"), "hello");
    await userEvent.click(screen.getByRole("button", { name: "Send Message" }));
    await waitFor(() => {
      const fetchMock = vi.mocked(fetch);
      expect(fetchMock.mock.calls.some(([u, i]) => String(u).includes("/messages") && (i as RequestInit)?.method === "POST")).toBe(true);
    });
  });
});
