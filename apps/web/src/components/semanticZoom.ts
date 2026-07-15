export type CommunityLevel = 0 | 1 | 2;

export function levelForZoom(scale: number): CommunityLevel {
  if (scale < 0.75) return 2;
  if (scale < 1.35) return 1;
  return 0;
}
