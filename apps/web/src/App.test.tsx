import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { useAuthStore } from "./store/auth";
import { ThemeProvider } from "./theme";

function renderApp(initial = "/") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <ThemeProvider><App /></ThemeProvider>
    </MemoryRouter>,
  );
}

describe("App routing", () => {
  beforeEach(() => {
    act(() => useAuthStore.setState({ apiKey: "", projectId: "", adminKey: "" }));
  });

  afterEach(() => {
    act(() => useAuthStore.setState({ apiKey: "", projectId: "", adminKey: "" }));
  });

  it("redirects to login when unauthenticated", () => {
    renderApp("/");
    expect(screen.getByRole("group", { name: "Theme" })).toBeInTheDocument();
    expect(screen.getByText("Enter project credentials to access the dashboard.")).toBeInTheDocument();
  });

  it("renders dashboard when authenticated", () => {
    act(() => {
      useAuthStore.setState({
        apiKey: "ogm_key",
        projectId: "11111111-2222-3333-4444-555555555555",
        adminKey: "",
      });
    });
    renderApp("/");
    expect(screen.getByRole("group", { name: "Theme" }).closest(".hidden")).toBeNull();
    expect(screen.getByText("Datasets", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByText("Graph Playground", { selector: "h3" })).toBeInTheDocument();
    expect(screen.queryByText("Query Playground")).not.toBeInTheDocument();
    expect(screen.queryByText("Memory")).not.toBeInTheDocument();
  });

  it("redirects removed product routes", async () => {
    act(() => {
      useAuthStore.setState({
        apiKey: "ogm_key",
        projectId: "11111111-2222-3333-4444-555555555555",
        adminKey: "",
      });
    });
    renderApp("/query");
    await waitFor(() => expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument());
    expect(screen.queryByText("Query Playground")).not.toBeInTheDocument();
  });
});
