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
  community_level: 1,
  available_levels: [0, 1, 2],
  analytics: null,
  refresh_required: true,
  stats: { entity_count: 2, relation_count: 1, density: 1 },
  communities: [{ id: "parent", entity_count: 2, parent_id: null, child_ids: ["child"], internal_edges: 1, external_edges: 0, density: 1, importance: 0.8 }],
  nodes: [
    { id: "one", canonical_name: "Ada Lovelace", entity_type: "person", community_id: "parent", degree: 1, weighted_degree: 0.9, importance: 0.8 },
    { id: "two", canonical_name: "Analytical Engine", entity_type: "concept", community_id: "parent", degree: 1, weighted_degree: 0.9, importance: 0.7 },
  ],
  relations: [{ id: "rel_1", source: "one", target: "two", type: "created", weight: 1, confidence: 0.92 }],
};

describe("GraphExplorer", () => {
  it("searches, selects, shows relation evidence, and exposes viewport controls", () => {
    render(<GraphExplorer graph={graph} loading={false} levelLocked={false} refreshingAnalytics={false} onRefresh={vi.fn()} onCommunityLevelChange={vi.fn()} onCommunityLevelLockChange={vi.fn()} onRefreshAnalytics={vi.fn()} />);

    fireEvent.change(screen.getByRole("textbox", { name: "Find entity" }), { target: { value: "Ada" } });
    expect(screen.getByLabelText("Selected entity")).toHaveTextContent("Ada Lovelace");
    expect(screen.getByLabelText("Entity relations")).toHaveTextContent("created · 0.92");
    expect(screen.getByRole("button", { name: "Close entity details" })).toBeEnabled();
  });

  it("shows hierarchy details and selects level", () => {
    const onLevel = vi.fn();
    render(<GraphExplorer graph={graph} loading={false} levelLocked={false} refreshingAnalytics={false} onRefresh={vi.fn()} onCommunityLevelChange={onLevel} onCommunityLevelLockChange={vi.fn()} onRefreshAnalytics={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Community level"), { target: { value: "2" } });
    expect(onLevel).toHaveBeenCalledWith(2);
    fireEvent.change(screen.getByRole("textbox", { name: "Find entity" }), { target: { value: "Ada" } });
    expect(screen.getByLabelText("Community hierarchy details")).toHaveTextContent("parent");
  });
});
