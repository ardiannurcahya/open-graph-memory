import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GraphExplorer } from "./GraphExplorer";

class ResizeObserverMock {
  observe() {}
  disconnect() {}
}

vi.stubGlobal("ResizeObserver", ResizeObserverMock);

const graph = {
  dataset_id: "ds_1",
  analytics: null,
  refresh_required: true,
  stats: { entity_count: 2, relation_count: 1, density: 1 },
  communities: [],
  nodes: [
    { id: "one", canonical_name: "Ada Lovelace", entity_type: "person", community_id: null, degree: 1, weighted_degree: 0.9, importance: 0.8 },
    { id: "two", canonical_name: "Analytical Engine", entity_type: "concept", community_id: null, degree: 1, weighted_degree: 0.9, importance: 0.7 },
  ],
  relations: [{ id: "rel_1", source: "one", target: "two", type: "created", weight: 1, confidence: 0.92 }],
};

describe("GraphExplorer", () => {
  it("searches, selects, shows relation evidence, and exposes viewport controls", () => {
    render(<GraphExplorer graph={graph} loading={false} refreshingAnalytics={false} onRefresh={vi.fn()} onRefreshAnalytics={vi.fn()} />);

    fireEvent.change(screen.getByRole("textbox", { name: "Find entity" }), { target: { value: "Ada" } });
    expect(screen.getByLabelText("Selected entity")).toHaveTextContent("Ada Lovelace");
    expect(screen.getByLabelText("Entity relations")).toHaveTextContent("created · 0.92");
    expect(screen.getByRole("button", { name: "Close entity details" })).toBeEnabled();
  });
});
