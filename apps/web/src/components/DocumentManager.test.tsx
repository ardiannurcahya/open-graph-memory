import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DocumentManager } from "./DocumentManager";

describe("DocumentManager", () => {
  it("shows JSON uploads and passes every selected file in order", async () => {
    const onUpload = vi.fn(async () => undefined);
    render(
      <DocumentManager
        documents={[]}
        loading={false}
        uploading={false}
        onUpload={onUpload}
        onDelete={vi.fn(async () => undefined)}
        onRefresh={vi.fn()}
      />,
    );
    const input = screen.getByLabelText("Upload files");
    const files = [
      new File(["%PDF-1.7\n%%EOF"], "report.pdf", { type: "application/pdf" }),
      new File(['{"service":"OpenGraphRAG"}'], "config.json", { type: "application/json" }),
      new File(["notes"], "notes.txt", { type: "text/plain" }),
    ];

    expect(input).toHaveAttribute("accept", ".txt,.md,.html,.json,.pdf,.csv");
    expect(input).toHaveAttribute("multiple");
    expect(screen.getByText(/\.json/)).toBeInTheDocument();
    fireEvent.change(input, { target: { files } });

    await waitFor(() => expect(onUpload).toHaveBeenCalledWith(files));
  });
});
