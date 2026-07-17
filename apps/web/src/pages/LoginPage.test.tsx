import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import LoginPage from "./LoginPage";
import { useAuthStore } from "../store/auth";
import { ThemeProvider } from "../theme";

describe("LoginPage", () => {
  beforeEach(() => {
    useAuthStore.setState({ apiKey: "", projectId: "", adminKey: "" });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ apiKey: "", projectId: "", adminKey: "" });
  });

  it("shows error when fields empty on connect", async () => {
    render(
      <MemoryRouter>
        <ThemeProvider><LoginPage /></ThemeProvider>
      </MemoryRouter>,
    );
    expect(screen.getByRole("group", { name: "Theme" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign In" }));
    expect(screen.getByText("API key and project ID are required")).toBeInTheDocument();
  });

  it("connects and stores credentials", async () => {
    render(
      <MemoryRouter>
        <ThemeProvider><LoginPage /></ThemeProvider>
      </MemoryRouter>,
    );
    await userEvent.type(screen.getByLabelText("Project ID"), "11111111-2222-3333-4444-555555555555");
    await userEvent.type(screen.getByLabelText("API Key"), "ogm_secretkey");
    await userEvent.click(screen.getByRole("button", { name: "Sign In" }));
    const { apiKey, projectId } = useAuthStore.getState();
    expect(apiKey).toBe("ogm_secretkey");
    expect(projectId).toBe("11111111-2222-3333-4444-555555555555");
  });

  it("creates a project via admin key", async () => {
    const fetchMock = vi.fn(async () =>
      ({
        ok: true,
        status: 201,
        json: async () => ({ id: "proj-1", name: "demo", api_key: "ogm_newkey" }),
      }) as Response,
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <MemoryRouter>
        <ThemeProvider><LoginPage /></ThemeProvider>
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Create New" }));
    await userEvent.type(screen.getByLabelText("Admin Key"), "admin-secret");
    await userEvent.type(screen.getByLabelText("Project Name"), "demo");
    await userEvent.click(screen.getByRole("button", { name: "Create Project" }));
    const { apiKey, projectId, adminKey } = useAuthStore.getState();
    expect(apiKey).toBe("ogm_newkey");
    expect(projectId).toBe("proj-1");
    expect(adminKey).toBe("admin-secret");
  });
});
