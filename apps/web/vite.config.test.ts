import { describe, it, expect } from "vitest";
import config from "./vite.config";

describe("vite.config dev server port", () => {
  it("configures the dev server on port 5000", () => {
    expect(config.server?.port).toBe(5000);
  });

  it("no longer uses the previous default port", () => {
    expect(config.server?.port).not.toBe(5173);
  });
});