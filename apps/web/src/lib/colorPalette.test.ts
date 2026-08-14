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
    expect(dark).toMatch(/^#[0-9a-f]{6}$/);
    expect(light).toMatch(/^#[0-9a-f]{6}$/);
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

  describe("communityIndex-based hue rotation", () => {
    it("ignores the community id and uses the index when one is provided", () => {
      const first = vividNodeColorForCommunity("z", true, 0);
      const second = vividNodeColorForCommunity("a", true, 0);
      expect(first).toBe(second);
    });

    it("produces different colors for different community indexes", () => {
      const a = vividNodeColorForCommunity("x", true, 0);
      const b = vividNodeColorForCommunity("x", true, 1);
      expect(a).not.toBe(b);
    });

    it("falls back to hash-based hue when communityIndex is omitted or negative", () => {
      const withoutIndex = vividNodeColorForCommunity("c0", true);
      const withNegativeIndex = vividNodeColorForCommunity("c0", true, -1);
      expect(withoutIndex).toBe(withNegativeIndex);
    });

    it("colorForCommunity forwards communityIndex to vividNodeColorForCommunity", () => {
      const info = colorForCommunity("any-id", 3);
      expect(info.color).toBe(vividNodeColorForCommunity("any-id", true, 3));
      expect(info.darkColor).toBe(vividNodeColorForCommunity("any-id", false, 3));
    });

    it("produces valid, distinct hex colors for dark and light neon variants", () => {
      const dark = vividNodeColorForCommunity("neon", true, 2);
      const light = vividNodeColorForCommunity("neon", false, 2);
      expect(dark).toMatch(/^#[0-9a-f]{6}$/);
      expect(light).toMatch(/^#[0-9a-f]{6}$/);
      expect(dark).not.toBe(light);
    });
  });

  describe("buildCommunityPalette sorted assignment", () => {
    it("assigns colors based on sorted id order, independent of input order", () => {
      const ordered = buildCommunityPalette(["a", "b", "c"]);
      const shuffled = buildCommunityPalette(["c", "a", "b"]);
      expect(ordered.get("a")?.color).toBe(shuffled.get("a")?.color);
      expect(ordered.get("b")?.color).toBe(shuffled.get("b")?.color);
      expect(ordered.get("c")?.color).toBe(shuffled.get("c")?.color);
    });

    it("matches the index-based color for each sorted community", () => {
      const palette = buildCommunityPalette(["banana", "apple", "cherry"]);
      // sorted order: apple(0), banana(1), cherry(2)
      expect(palette.get("apple")?.color).toBe(vividNodeColorForCommunity("apple", true, 0));
      expect(palette.get("banana")?.color).toBe(vividNodeColorForCommunity("banana", true, 1));
      expect(palette.get("cherry")?.color).toBe(vividNodeColorForCommunity("cherry", true, 2));
    });
  });
});
