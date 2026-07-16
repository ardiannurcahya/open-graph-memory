import type { GraphNode, GraphState, CameraState, EntityType } from "./graphTypes";
import { SHAPE_MAP } from "./graphTypes";
import { hexRgba } from "./colorPalette";

export interface RenderOptions {
  darkTheme: boolean;
  showLabels: boolean;
  hlNodes: Set<string>;
  hlEdges: Set<string>;
  hovered: GraphNode | null;
  selected: GraphNode | null;
  activeFilters: Set<string>;
  physicsEnabled: boolean;
}

export function toWorld(
  sx: number,
  sy: number,
  cam: CameraState,
  dpr: number,
  canvasW: number,
  canvasH: number,
): [number, number] {
  return [
    (sx * dpr - cam.x - canvasW / 2) / cam.zoom,
    (sy * dpr - cam.y - canvasH / 2) / cam.zoom,
  ];
}

export function toScreen(
  wx: number,
  wy: number,
  cam: CameraState,
  canvasW: number,
  canvasH: number,
): [number, number] {
  return [
    wx * cam.zoom + cam.x + canvasW / 2,
    wy * cam.zoom + cam.y + canvasH / 2,
  ];
}

export function drawNodeShape(ctx: CanvasRenderingContext2D, type: EntityType, r: number): void {
  switch (SHAPE_MAP[type] ?? "circle") {
    case "circle":
      ctx.beginPath();
      ctx.arc(0, 0, r, 0, Math.PI * 2);
      break;
    case "roundRect": {
      ctx.beginPath();
      ctx.moveTo(-r + 3, -r * 0.8);
      ctx.lineTo(r - 3, -r * 0.8);
      ctx.quadraticCurveTo(r, -r * 0.8, r, -r * 0.8 + 3);
      ctx.lineTo(r, r * 0.8 - 3);
      ctx.quadraticCurveTo(r, r * 0.8, r - 3, r * 0.8);
      ctx.lineTo(-r + 3, r * 0.8);
      ctx.quadraticCurveTo(-r, r * 0.8, -r, r * 0.8 - 3);
      ctx.lineTo(-r, -r * 0.8 + 3);
      ctx.quadraticCurveTo(-r, -r * 0.8, -r + 3, -r * 0.8);
      ctx.closePath();
      break;
    }
    case "star":
      ctx.beginPath();
      for (let i = 0; i < 5; i++) {
        const a = (i * Math.PI * 2) / 5 - Math.PI / 2;
        if (i) ctx.lineTo(Math.cos(a) * r, Math.sin(a) * r);
        else ctx.moveTo(Math.cos(a) * r, Math.sin(a) * r);
      }
      ctx.closePath();
      break;
    case "diamond":
      ctx.beginPath();
      ctx.moveTo(0, -r);
      ctx.lineTo(r * 0.85, 0);
      ctx.lineTo(0, r);
      ctx.lineTo(-r * 0.85, 0);
      ctx.closePath();
      break;
    case "rect": {
      ctx.beginPath();
      const rw = r * 1.3;
      const rh = r * 0.9;
      ctx.moveTo(-rw + 2, -rh);
      ctx.lineTo(rw - 2, -rh);
      ctx.quadraticCurveTo(rw, -rh, rw, -rh + 2);
      ctx.lineTo(rw, rh - 2);
      ctx.quadraticCurveTo(rw, rh, rw - 2, rh);
      ctx.lineTo(-rw + 2, rh);
      ctx.quadraticCurveTo(-rw, rh, -rw, rh - 2);
      ctx.lineTo(-rw, -rh + 2);
      ctx.quadraticCurveTo(-rw, -rh, -rw + 2, -rh);
      ctx.closePath();
      break;
    }
    default:
      ctx.beginPath();
      ctx.arc(0, 0, r, 0, Math.PI * 2);
  }
}

export function render(
  ctx: CanvasRenderingContext2D,
  state: GraphState,
  cam: CameraState,
  opts: RenderOptions,
): void {
  const W = ctx.canvas.width;
  const H = ctx.canvas.height;
  const hasQ = opts.hlNodes.size > 0;
  const isDark = opts.darkTheme;
  const nodeMap = new Map(state.nodes.map((n) => [n.id, n]));

  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = isDark ? "#0e1116" : "#f5f3f0";
  ctx.fillRect(0, 0, W, H);

  // Grid
  const gs = 80 * cam.zoom;
  const ox = (cam.x + W / 2) % gs;
  const oy = (cam.y + H / 2) % gs;
  ctx.strokeStyle = isDark ? "rgba(212,160,86,0.02)" : "rgba(120,100,60,0.025)";
  ctx.lineWidth = 1;
  for (let x = ox; x < W; x += gs) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, H);
    ctx.stroke();
  }
  for (let y = oy; y < H; y += gs) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(W, y);
    ctx.stroke();
  }

  ctx.save();
  ctx.translate(W / 2 + cam.x, H / 2 + cam.y);
  ctx.scale(cam.zoom, cam.zoom);

  // Community halos
  const groups: Record<string, GraphNode[]> = {};
  for (const n of state.nodes) {
    if (opts.activeFilters.size > 0 && !opts.activeFilters.has(n.community)) continue;
    if (!groups[n.community]) groups[n.community] = [];
    groups[n.community].push(n);
  }
  for (const k in groups) {
    const ns = groups[k];
    const col = state.communities.get(k)?.color ?? "#555";
    const cx = ns.reduce((a, n) => a + n.x, 0) / ns.length;
    const cy = ns.reduce((a, n) => a + n.y, 0) / ns.length;
    const md = Math.max(100, ...ns.map((n) => Math.sqrt((n.x - cx) ** 2 + (n.y - cy) ** 2) + 60));
    const gr = ctx.createRadialGradient(cx, cy, 0, cx, cy, md);
    gr.addColorStop(0, hexRgba(col, isDark ? 0.08 : 0.05));
    gr.addColorStop(0.6, hexRgba(col, isDark ? 0.02 : 0.01));
    gr.addColorStop(1, "transparent");
    ctx.fillStyle = gr;
    ctx.beginPath();
    ctx.arc(cx, cy, md, 0, Math.PI * 2);
    ctx.fill();
  }

  // Edges
  for (const e of state.edges) {
    const s = nodeMap.get(e.source);
    const t = nodeMap.get(e.target);
    if (!s || !t) continue;
    if (opts.activeFilters.size > 0 && (!opts.activeFilters.has(s.community) || !opts.activeFilters.has(t.community))) continue;

    const hl = opts.hlEdges.has(e.id);
    const dim = hasQ && !hl;
    const isHov = opts.hovered && (e.source === opts.hovered.id || e.target === opts.hovered.id);

    ctx.beginPath();
    ctx.moveTo(s.x, s.y);
    ctx.lineTo(t.x, t.y);

    if (dim) {
      ctx.strokeStyle = isDark ? "rgba(30,35,45,0.2)" : "rgba(120,110,100,0.12)";
      ctx.lineWidth = 0.6;
    } else if (hl) {
      ctx.strokeStyle = "#d4a056";
      ctx.lineWidth = 2.2;
      ctx.shadowColor = "#d4a056";
      ctx.shadowBlur = 8;
    } else {
      ctx.strokeStyle = isHov
        ? isDark ? "rgba(150,160,180,0.4)" : "rgba(140,120,80,0.35)"
        : isDark ? "rgba(70,80,100,0.12)" : "rgba(100,90,80,0.12)";
      ctx.lineWidth = isHov ? 1.6 : 0.8;
    }
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Edge label
    if (hl || isHov) {
      const mx = (s.x + t.x) / 2;
      const my = (s.y + t.y) / 2;
      ctx.font = `500 ${9 / Math.max(cam.zoom, 0.3)}px 'JetBrains Mono', monospace`;
      ctx.fillStyle = hl ? "#d4a056" : isDark ? "#6b7585" : "#7a7568";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(e.label.replace(/_/g, " "), mx, my - 7);
    }

    // Particles
    if (!dim) {
      for (let i = 0; i < e.particles.length; i++) {
        e.particles[i] = (e.particles[i] + 0.002 * (0.5 + e.weight * 0.12)) % 1;
        const p = e.particles[i];
        const px = s.x + (t.x - s.x) * p;
        const py = s.y + (t.y - s.y) * p;
        ctx.beginPath();
        ctx.arc(px, py, hl ? 2.5 : 1.5, 0, Math.PI * 2);
        ctx.fillStyle = hl ? "#d4a056" : hexRgba(state.communities.get(s.community)?.color ?? "#555", 0.35);
        ctx.fill();
      }
    }
  }

  // Nodes
  for (const n of state.nodes) {
    if (opts.activeFilters.size > 0 && !opts.activeFilters.has(n.community)) continue;
    const hl = opts.hlNodes.has(n.id);
    const dim = hasQ && !hl;
    const isHov = opts.hovered && opts.hovered.id === n.id;
    const isSel = opts.selected && opts.selected.id === n.id;
    const col = state.communities.get(n.community)?.color ?? "#555";
    const r = n.radius;

    ctx.save();
    ctx.translate(n.x, n.y);

    // Glow ring for high-degree
    if (n.degFrac > 0.35 && !dim) {
      ctx.beginPath();
      ctx.arc(0, 0, r + 4, 0, Math.PI * 2);
      ctx.strokeStyle = hexRgba(col, 0.12 + n.degFrac * 0.2);
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Selected ring
    if (isSel) {
      ctx.beginPath();
      ctx.arc(0, 0, r + 6, 0, Math.PI * 2);
      ctx.strokeStyle = col;
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    if (hl || isHov || isSel) {
      ctx.shadowColor = hl ? "#d4a056" : col;
      ctx.shadowBlur = hl ? 24 : 16;
    }

    ctx.fillStyle = dim ? (isDark ? "#161b22" : "#e8e4de") : hl ? col : hexRgba(col, isDark ? 0.7 : 0.6);
    ctx.strokeStyle = dim ? (isDark ? "#1c2128" : "#d0ccc4") : hl ? "#fff" : col;
    ctx.lineWidth = isSel || hl ? 2.5 : 1;
    drawNodeShape(ctx, n.type, r);
    ctx.fill();
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Degree badge
    if (!dim && n.degree > 0) {
      const bx = r * 0.75;
      const by = -r * 0.75;
      ctx.beginPath();
      ctx.arc(bx, by, 5.5, 0, Math.PI * 2);
      ctx.fillStyle = hl || isHov ? "#fff" : isDark ? "#161b22" : "#f5f3f0";
      ctx.fill();
      ctx.font = 'bold 7px "JetBrains Mono", monospace';
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = hl || isHov ? "#000" : col;
      ctx.fillText(String(n.degree), bx, by + 0.5);
    }

    // Label
    if (opts.showLabels && (cam.zoom > 0.35 || hl || isHov || isSel)) {
      const fs = Math.max(8, n.degFrac > 0.5 ? 10 : 9);
      ctx.font = `${hl || isHov ? 600 : 400} ${fs}px 'JetBrains Mono', monospace`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillStyle = dim ? (isDark ? "#252b36" : "#a8a298") : isDark ? "#d4dae4" : "#292524";
      ctx.fillText(n.label, 0, r + 5);
    }

    ctx.restore();
  }

  ctx.restore();
}

export function hitTest(
  state: GraphState,
  sx: number,
  sy: number,
  cam: CameraState,
  dpr: number,
  canvasW: number,
  canvasH: number,
  activeFilters: Set<string>,
): GraphNode | null {
  const [wx, wy] = toWorld(sx, sy, cam, dpr, canvasW, canvasH);
  return (
    state.nodes.find((n) => {
      if (activeFilters.size > 0 && !activeFilters.has(n.community)) return false;
      return Math.sqrt((n.x - wx) ** 2 + (n.y - wy) ** 2) < n.radius + 8 / cam.zoom;
    }) ?? null
  );
}
