import type { CommunityInfo } from "./graphTypes";

const NEON_NODE_COLORS = [
  "#00f5ff",
  "#ff00e5",
  "#39ff14",
  "#ffe600",
  "#8a2bff",
  "#ff5f1f",
  "#00ff9d",
  "#ff1744",
  "#00b0ff",
  "#d7ff00",
  "#ff2d95",
  "#7cff00",
] as const;

function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash * 31 + str.charCodeAt(i)) % 360;
  }
  return Math.abs(hash);
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

export function colorForCommunity(communityId: string): CommunityInfo {
  const hue = hashString(communityId) % 360;
  const color = hslToHex(hue, 48, 58);
  const darkColor = hslToHex(hue, 38, 32);
  return {
    id: communityId,
    name: communityId,
    color,
    darkColor,
  };
}

export function vividNodeColorForCommunity(communityId: string, _darkBackground: boolean): string {
  return NEON_NODE_COLORS[hashString(communityId) % NEON_NODE_COLORS.length];
}

export function buildCommunityPalette(
  communityIds: string[],
  names?: Map<string, string>,
): Map<string, CommunityInfo> {
  const palette = new Map<string, CommunityInfo>();
  const usedHues: number[] = [];
  for (const id of communityIds) {
    let hue = hashString(id) % 360;
    // Spread hues to avoid near-duplicates
    let attempts = 0;
    while (attempts < 36 && usedHues.some((h) => Math.abs(h - hue) < 30)) {
      hue = (hue + 37) % 360;
      attempts += 1;
    }
    usedHues.push(hue);
    const info = colorForCommunity(id);
    info.color = hslToHex(hue, 48, 58);
    info.darkColor = hslToHex(hue, 38, 32);
    if (names && names.has(id)) info.name = names.get(id) as string;
    palette.set(id, info);
  }
  return palette;
}

export function hexRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}
