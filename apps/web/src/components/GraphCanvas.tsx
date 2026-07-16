import { useCallback, useEffect, useRef } from "react";
import type { GraphState, CameraState, GraphNode } from "../lib/graphTypes";
import { DEFAULT_PHYSICS, physicsStep, fitAll, highlightConnected } from "../lib/graphPhysics";
import { render, hitTest, toWorld } from "../lib/graphRender";

interface GraphCanvasProps {
  state: GraphState;
  physicsEnabled: boolean;
  showLabels: boolean;
  activeFilters: Set<string>;
  onNodeSelect: (node: GraphNode | null) => void;
  onCameraChange?: (zoom: number) => void;
}

export function GraphCanvas({
  state,
  physicsEnabled,
  showLabels,
  activeFilters,
  onNodeSelect,
  onCameraChange,
}: GraphCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const camRef = useRef<CameraState>({ x: 0, y: 0, zoom: 1 });
  const rafRef = useRef<number>(0);
  const dprRef = useRef(window.devicePixelRatio || 1);

  const dragRef = useRef<GraphNode | null>(null);
  const panRef = useRef<{ x: number; y: number; cx: number; cy: number } | null>(null);
  const hoveredRef = useRef<GraphNode | null>(null);
  const selectedRef = useRef<GraphNode | null>(null);
  const hlRef = useRef<{ nodes: Set<string>; edges: Set<string> }>({ nodes: new Set(), edges: new Set() });

  const physicsRef = useRef(physicsEnabled);
  const labelsRef = useRef(showLabels);
  const filtersRef = useRef(activeFilters);
  const selectCbRef = useRef(onNodeSelect);
  const camCbRef = useRef(onCameraChange);

  physicsRef.current = physicsEnabled;
  labelsRef.current = showLabels;
  filtersRef.current = activeFilters;
  selectCbRef.current = onNodeSelect;
  camCbRef.current = onCameraChange;

  const getSize = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return [0, 0] as const;
    const rect = canvas.getBoundingClientRect();
    return [rect.width, rect.height] as const;
  }, []);

  const resize = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const [w, h] = getSize();
    if (w === 0 || h === 0) return;
    const dpr = dprRef.current;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
  }, [getSize]);

  const doFitAll = useCallback(() => {
    const [w, h] = getSize();
    if (w === 0 || h === 0) return;
    const cam = fitAll(state.nodes, w, h, dprRef.current);
    camRef.current = cam;
    camCbRef.current?.(cam.zoom);
  }, [state.nodes, getSize]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    resize();
    const parent = canvas.parentElement;
    const ro = new ResizeObserver(() => resize());
    if (parent) ro.observe(parent);

    const loop = () => {
      if (physicsRef.current) {
        physicsStep(state, DEFAULT_PHYSICS, dragRef.current?.id ?? null);
      }
      render(ctx, state, camRef.current, {
        darkTheme: false,
        showLabels: labelsRef.current,
        hlNodes: hlRef.current.nodes,
        hlEdges: hlRef.current.edges,
        hovered: hoveredRef.current,
        selected: selectedRef.current,
        activeFilters: filtersRef.current,
        physicsEnabled: physicsRef.current,
      });
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);

    return () => {
      ro.disconnect();
      cancelAnimationFrame(rafRef.current);
    };
  }, [state, resize]);

  useEffect(() => {
    if (state.nodes.length > 0) {
      const timer = setTimeout(doFitAll, 50);
      return () => clearTimeout(timer);
    }
  }, [state.nodes, doFitAll]);

  const getRel = useCallback((e: React.MouseEvent): [number, number] => {
    const canvas = canvasRef.current;
    if (!canvas) return [0, 0];
    const rect = canvas.getBoundingClientRect();
    return [e.clientX - rect.left, e.clientY - rect.top];
  }, []);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const [sx, sy] = getRel(e);
      const hit = hitTest(state, sx, sy, camRef.current, dprRef.current, canvas.width, canvas.height, filtersRef.current);
      if (hit) {
        dragRef.current = hit;
        selectedRef.current = hit;
        hlRef.current = highlightConnected(state, hit.id);
        selectCbRef.current(hit);
      } else {
        selectedRef.current = null;
        hlRef.current = { nodes: new Set(), edges: new Set() };
        selectCbRef.current(null);
        panRef.current = { x: sx, y: sy, cx: camRef.current.x, cy: camRef.current.y };
      }
    },
    [state, getRel, selectCbRef],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const [sx, sy] = getRel(e);
      if (dragRef.current) {
        const [wx, wy] = toWorld(sx, sy, camRef.current, dprRef.current, canvas.width, canvas.height);
        dragRef.current.x = wx;
        dragRef.current.y = wy;
        dragRef.current.vx = 0;
        dragRef.current.vy = 0;
      } else if (panRef.current) {
        camRef.current.x = panRef.current.cx + (sx - panRef.current.x) * dprRef.current;
        camRef.current.y = panRef.current.cy + (sy - panRef.current.y) * dprRef.current;
      } else {
        const hit = hitTest(state, sx, sy, camRef.current, dprRef.current, canvas.width, canvas.height, filtersRef.current);
        hoveredRef.current = hit;
        canvas.style.cursor = hit ? "pointer" : "grab";
        if (hit && !selectedRef.current) {
          hlRef.current = highlightConnected(state, hit.id);
        } else if (!hit && !selectedRef.current) {
          hlRef.current = { nodes: new Set(), edges: new Set() };
        }
      }
    },
    [state, getRel],
  );

  const handleMouseUp = useCallback(() => {
    dragRef.current = null;
    panRef.current = null;
  }, []);

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      const z = camRef.current.zoom * (e.deltaY > 0 ? 0.92 : 1.08);
      camRef.current.zoom = Math.max(0.12, Math.min(5, z));
      camCbRef.current?.(camRef.current.zoom);
    },
    [camCbRef],
  );

  const handleDoubleClick = useCallback(() => doFitAll(), [doFitAll]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const fitHandler = () => doFitAll();
    const resetHandler = () => {
      camRef.current = { x: 0, y: 0, zoom: 1 };
      camCbRef.current?.(1);
    };
    canvas.addEventListener("graph:fit", fitHandler);
    canvas.addEventListener("graph:reset", resetHandler);
    return () => {
      canvas.removeEventListener("graph:fit", fitHandler);
      canvas.removeEventListener("graph:reset", resetHandler);
    };
  }, [doFitAll, camCbRef]);

  return (
    <canvas
      ref={canvasRef}
      id="graph-canvas"
      className="absolute inset-0 h-full w-full cursor-grab"
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={() => {
        dragRef.current = null;
        panRef.current = null;
        hoveredRef.current = null;
      }}
      onWheel={handleWheel}
      onDoubleClick={handleDoubleClick}
    />
  );
}
