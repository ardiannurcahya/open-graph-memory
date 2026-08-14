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

  describe("vividNodeColorForCommunity with communityIndex", () => {
    it("derives hue from the index using the golden ratio step, ignoring the id hash", () => {
      const expectedDark = hslToHex((3 * 137.507764) % 360, 100, 68);
      const expectedLight = hslToHex((3 * 137.507764) % 360, 100, 44);
      expect(vividNodeColorForCommunity("zzz", true, 3)).toBe(expectedDark);
      expect(vividNodeColorForCommunity("completely-different-id", true, 3)).toBe(expectedDark);
      expect(vividNodeColorForCommunity("another-id", false, 3)).toBe(expectedLight);
    });

    it("produces identical colors for different community ids sharing an index", () => {
      const a = vividNodeColorForCommunity("id-a", true, 7);
      const b = vividNodeColorForCommunity("id-b", true, 7);
      expect(a).toBe(b);
    });

    it("falls back to the hash-based hue when index is undefined or negative", () => {
      const hashBased = vividNodeColorForCommunity("abc", true);
      expect(vividNodeColorForCommunity("abc", true, -1)).toBe(hashBased);
      expect(vividNodeColorForCommunity("abc", true, undefined)).toBe(hashBased);
    });

    it("uses 100% saturation with neon lightness for both backgrounds", () => {
      const hue = (5 * 137.507764) % 360;
      expect(vividNodeColorForCommunity("x", true, 5)).toBe(hslToHex(hue, 100, 68));
      expect(vividNodeColorForCommunity("x", false, 5)).toBe(hslToHex(hue, 100, 44));
    });

    it("index 0 maps to hue 0", () => {
      expect(vividNodeColorForCommunity("anything", true, 0)).toBe(hslToHex(0, 100, 68));
    });
  });

  describe("colorForCommunity with communityIndex", () => {
    it("forwards the index to both the light and dark colors", () => {
      const info = colorForCommunity("q", 2);
      expect(info.color).toBe(vividNodeColorForCommunity("q", true, 2));
      expect(info.darkColor).toBe(vividNodeColorForCommunity("q", false, 2));
    });
  });

  describe("buildCommunityPalette id sorting", () => {
    it("assigns indices based on sorted community ids, not input order", () => {
      const palette = buildCommunityPalette(["zebra", "apple", "mango"]);
      expect(palette.get("apple")?.color).toBe(vividNodeColorForCommunity("apple", true, 0));
      expect(palette.get("mango")?.color).toBe(vividNodeColorForCommunity("mango", true, 1));
      expect(palette.get("zebra")?.color).toBe(vividNodeColorForCommunity("zebra", true, 2));
    });

    it("produces the same colors regardless of the order ids are passed in", () => {
      const first = buildCommunityPalette(["b", "a", "c"]);
      const second = buildCommunityPalette(["c", "b", "a"]);
      expect(first.get("a")?.color).toBe(second.get("a")?.color);
      expect(first.get("b")?.color).toBe(second.get("b")?.color);
      expect(first.get("c")?.color).toBe(second.get("c")?.color);
    });

    it("does not mutate the input array while sorting", () => {
      const ids = ["zebra", "apple", "mango"];
      buildCommunityPalette(ids);
      expect(ids).toEqual(["zebra", "apple", "mango"]);
    });
  });
});
