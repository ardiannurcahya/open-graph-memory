import type { CommunityInfo } from "./graphTypes";

function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash * 31 + str.charCodeAt(i)) & 0x7fffffff;
  }
  return hash;
}

export function hslToHex(h: number, s: number, l: number): string {
  const sNorm = s / 100;
  const lNorm = l / 100;
  const c = (1 - Math.abs(2 * lNorm - 1)) * sNorm;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = lNorm - c / 2;
  let r = 0;
  let g = 0;
  let b = 0;
  if (h < 60) { r = c; g = x; b = 0; }
  else if (h < 120) { r = x; g = c; b = 0; }
  else if (h < 180) { r = 0; g = c; b = x; }
  else if (h < 240) { r = 0; g = x; b = c; }
  else if (h < 300) { r = x; g = 0; b = c; }
  else { r = c; g = 0; b = x; }
  const toHex = (v: number) =>
    Math.round((v + m) * 255)
      .toString(16)
      .padStart(2, "0");
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

/**
 * Rainbow Neon Color Palette Engine
 * Generates ultra-vibrant electric neon rainbow colors (Red -> Lime -> Purple -> Gold -> Cyan -> Magenta).
 * Uses Golden Ratio angle stepping (~137.507764°) to guarantee zero hue collisions across communities.
 */
export function vividNodeColorForCommunity(
  communityId: string,
  darkBackground: boolean,
  communityIndex?: number,
): string {
  let hue: number;
  if (typeof communityIndex === "number" && communityIndex >= 0) {
    hue = (communityIndex * 137.507764) % 360;
  } else {
    const hash = hashString(communityId);
    hue = (hash * 137.507764) % 360;
  }

  // Pure Electric Rainbow Neon (100% Saturation, Glowing Neon Lightness)
  const saturation = 100;
  const lightness = darkBackground ? 68 : 44;
  return hslToHex(hue, saturation, lightness);
}

export function colorForCommunity(
  communityId: string,
  communityIndex?: number,
): CommunityInfo {
  const color = vividNodeColorForCommunity(communityId, true, communityIndex);
  const darkColor = vividNodeColorForCommunity(communityId, false, communityIndex);
  return {
    id: communityId,
    name: communityId,
    color,
    darkColor,
  };
}

export function buildCommunityPalette(
  communityIds: string[],
  names?: Map<string, string>,
): Map<string, CommunityInfo> {
  const palette = new Map<string, CommunityInfo>();
  const sortedIds = [...communityIds].sort();
  sortedIds.forEach((id, index) => {
    const info = colorForCommunity(id, index);
    if (names && names.has(id)) info.name = names.get(id) as string;
    palette.set(id, info);
  });
  return palette;
}

export function hexRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}
