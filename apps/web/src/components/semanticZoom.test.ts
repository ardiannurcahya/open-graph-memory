import { describe, expect, it } from "vitest";
import { levelForZoom } from "./semanticZoom";

describe("levelForZoom", () => {
  it("maps zoom scales from overview to detail", () => {
    expect(levelForZoom(0.5)).toBe(2);
    expect(levelForZoom(1)).toBe(1);
    expect(levelForZoom(2)).toBe(0);
  });
});
