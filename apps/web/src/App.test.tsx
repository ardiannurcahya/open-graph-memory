import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { useAuthStore } from "./store/auth";

function renderApp(initial = "/") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <App />
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
    expect(screen.getByText("Datasets", { selector: "h3" })).toBeInTheDocument();
  });
});
