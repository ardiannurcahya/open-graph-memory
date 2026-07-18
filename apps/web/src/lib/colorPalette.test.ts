import { describe, it, expect } from "vitest";
import { colorForCommunity, buildCommunityPalette, hexRgba, hslToHex, vividNodeColorForCommunity } from "./colorPalette";

describe("colorPalette", () => {
  it("generates deterministic color for same community id", () => {
    const a = colorForCommunity("c0");
    const b = colorForCommunity("c0");
    expect(a.color).toBe(b.color);
    expect(a.darkColor).toBe(b.darkColor);
  });

  it("generates different colors for different community ids", () => {
    const a = colorForCommunity("c0");
    const b = colorForCommunity("c1");
    expect(a.color).not.toBe(b.color);
  });

  it("produces valid hex colors", () => {
    const c = colorForCommunity("test");
    expect(c.color).toMatch(/^#[0-9a-f]{6}$/);
    expect(c.darkColor).toMatch(/^#[0-9a-f]{6}$/);
  });

  it("uses stable neon node colors", () => {
    const dark = vividNodeColorForCommunity("c0", true);
    const light = vividNodeColorForCommunity("c0", false);
    expect(dark).toBe(light);
    expect(dark).toMatch(/^#[0-9a-f]{6}$/);
    expect(vividNodeColorForCommunity("c1", true)).not.toBe(dark);
  });

  it("builds palette with spread hues", () => {
    const palette = buildCommunityPalette(["a", "b", "c", "d", "e"]);
    expect(palette.size).toBe(5);
    const colors = [...palette.values()].map((v) => v.color);
    const unique = new Set(colors);
    expect(unique.size).toBe(5);
  });

  it("applies names when provided", () => {
    const names = new Map([["c0", "Academic Research"]]);
    const palette = buildCommunityPalette(["c0"], names);
    expect(palette.get("c0")?.name).toBe("Academic Research");
  });

  it("hslToHex produces valid hex", () => {
    expect(hslToHex(0, 100, 50)).toBe("#ff0000");
    expect(hslToHex(120, 100, 50)).toBe("#00ff00");
    expect(hslToHex(240, 100, 50)).toBe("#0000ff");
  });

  it("hexRgba converts hex + alpha to rgba string", () => {
    expect(hexRgba("#38bdf8", 0.5)).toBe("rgba(56,189,248,0.5)");
    expect(hexRgba("#ff0000", 1)).toBe("rgba(255,0,0,1)");
  });
});
