import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { datasetsApi, graphApi } from "../api/endpoints";
import { ApiError } from "../api/client";
import type { Dataset, EntityView, ExplorerView, GraphSummary } from "../api/types";
import type { GraphNode, GraphState } from "../lib/graphTypes";
import { explorerToGraphState, graphSummaryToGraphState } from "../lib/graphMapping";
import { GraphCanvas } from "../components/GraphCanvas";
import { Inspector } from "../components/Inspector";
import { CommandPalette } from "../components/CommandPalette";

type Tool = "search" | "neighbors" | "path" | "subgraph" | "evidence" | "json";

const TOOLS: { id: Tool; label: string }[] = [
  { id: "search", label: "Entity search" },
  { id: "neighbors", label: "Neighbors" },
  { id: "path", label: "Path" },
  { id: "subgraph", label: "Subgraph" },
  { id: "evidence", label: "Relation evidence" },
  { id: "json", label: "Raw JSON" },
];

export default function GraphPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [view, setView] = useState<ExplorerView | null>(null);
  const [summary, setSummary] = useState<GraphSummary | null>(null);
  const [payload, setPayload] = useState<unknown>(null);
  const [level, setLevel] = useState(0);
  const [tool, setTool] = useState<Tool>("search");
  const [query, setQuery] = useState("");
  const [entityId, setEntityId] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [subgraphEntityId, setSubgraphEntityId] = useState("");
  const [relationId, setRelationId] = useState("");
  const [depth, setDepth] = useState(1);
  const [searchResults, setSearchResults] = useState<EntityView[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [physicsEnabled, setPhysicsEnabled] = useState(true);
  const [showLegend, setShowLegend] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [showHistory] = useState(false);
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set());
  const [zoom, setZoom] = useState(1);
  const explorerRequestRef = useRef(0);
  const explorerAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    void datasetsApi.list().then(setDatasets).catch(() => undefined);
  }, []);

  // Re-fetch datasets when the page becomes visible (e.g., after creating/deleting on DatasetsPage)
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        void datasetsApi.list().then(setDatasets).catch(() => undefined);
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, []);

  const graphState: GraphState | null = useMemo(() => {
    if (summary) return graphSummaryToGraphState(summary);
    if (view) return explorerToGraphState(view);
    return null;
  }, [summary, view]);

  const loadExplorer = useCallback(async (id: string, communityLevel: number) => {
    explorerAbortRef.current?.abort();
    const controller = new AbortController();
    explorerAbortRef.current = controller;
    const requestId = ++explorerRequestRef.current;
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    try {
      const response = await graphApi.getExplorer(id, {
        community_level: communityLevel,
        node_limit: 3000,
        relation_limit: 5000,
      }, controller.signal);
      const [nodes, relations] = await Promise.all([
        response.nodes.length < response.stats.entity_count
          ? loadAllExplorerNodes(id, communityLevel, controller.signal)
          : Promise.resolve(response.nodes),
        response.relations.length < response.stats.relation_count
          ? loadAllExplorerRelations(id, controller.signal)
          : Promise.resolve(response.relations),
      ]);
      if (requestId !== explorerRequestRef.current) return;
      const completeResponse = { ...response, nodes, relations };
      setView(completeResponse);
      setSummary(null);
      setPayload(completeResponse);
      setActiveFilters(new Set());
    } catch (err) {
      if (requestId !== explorerRequestRef.current || controller.signal.aborted) return;
      setError(errorMessage(err, "failed to load graph"));
      setView(null);
      setSummary(null);
    } finally {
      if (requestId === explorerRequestRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (datasetId) void loadExplorer(datasetId, level);
    else {
      explorerAbortRef.current?.abort();
      explorerRequestRef.current += 1;
      setView(null);
      setSummary(null);
      setPayload(null);
      setActiveFilters(new Set());
    }
  }, [datasetId, level, loadExplorer]);

  useEffect(() => () => explorerAbortRef.current?.abort(), []);

  const runTool = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!datasetId || tool === "json") return;
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    try {
      if (tool === "search") {
        const response = await graphApi.searchEntities(datasetId, query.trim(), undefined, 25, showHistory);
        setSearchResults(response);
        setPayload(response);
        setSelectedNode(
          response.length === 1
            ? graphState?.nodes.find((node) => node.id === response[0].id) ?? null
            : null,
        );
      } else if (tool === "neighbors") {
        const [entity, neighbors] = await Promise.all([
          graphApi.getEntity(entityId.trim()),
          graphApi.getNeighbors(entityId.trim()),
        ]);
        const nodes = uniqueEntities([entity, ...neighbors.map((neighbor) => neighbor.entity)]);
        const relations = neighbors.map((neighbor) => neighbor.relation);
        const response: GraphSummary = {
          dataset_id: datasetId,
          entity_count: nodes.length,
          relation_count: relations.length,
          nodes,
          relations,
        };
        setSummary(response);
        setPayload({ entity, neighbors });
        setActiveFilters(new Set());
      } else if (tool === "path") {
        const response = await graphApi.findPath(
          datasetId,
          sourceId.trim(),
          targetId.trim(),
          depth,
        );
        setSummary(toGraphSummary(response));
        setPayload(response);
        setActiveFilters(new Set());
      } else if (tool === "subgraph") {
        const response = await graphApi.getSubgraph(datasetId, subgraphEntityId.trim(), depth);
        setSummary(toGraphSummary(response));
        setPayload(response);
        setActiveFilters(new Set());
      } else {
        const response = await graphApi.getRelationEvidence(datasetId, relationId.trim());
        setPayload(response);
      }
    } catch (err) {
      setError(errorMessage(err, `${tool} request failed`));
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    if (!datasetId) return;
    setRefreshing(true);
    setError(null);
    try {
      await graphApi.refreshAnalytics(datasetId);
      await loadExplorer(datasetId, level);
    } catch (err) {
      setError(errorMessage(err, "analytics refresh failed"));
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) return;
      if (cmdOpen) return;
      if ((event.ctrlKey || event.metaKey) && event.key === "k") {
        event.preventDefault();
        setCmdOpen(true);
      } else if (event.key === "Escape") {
        setSelectedNode(null);
      } else if (event.key.toLowerCase() === "l") {
        setShowLegend((value) => !value);
      } else if (event.key.toLowerCase() === "f") {
        setShowFilters((value) => !value);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [cmdOpen]);

  const toggleFilter = (communityId: string) => {
    setActiveFilters((previous) => {
      const next = new Set(previous);
      if (next.has(communityId)) next.delete(communityId);
      else next.add(communityId);
      return next;
    });
  };

  const triggerCanvasEvent = (type: string) => {
    document.getElementById("graph-canvas")?.dispatchEvent(new Event(type));
  };

  return (
    <div className="relative h-screen min-h-[640px] overflow-hidden bg-ui-canvas">
      {graphState ? (
        <GraphCanvas
          state={graphState}
          physicsEnabled={physicsEnabled}
          showLabels={showLabels}
          activeFilters={activeFilters}
          selectedNodeId={selectedNode?.id ?? null}
          onNodeSelect={setSelectedNode}
          onCameraChange={setZoom}
        />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center p-8 text-sm text-foreground-muted">
          {loading ? "Loading..." : "Select dataset to open graph playground."}
        </div>
      )}

      <div className="absolute left-3 right-3 top-3 z-10 flex flex-wrap items-center gap-2 rounded-xl border border-mac bg-surface/95 px-3.5 py-2 shadow-lg backdrop-blur-md text-foreground">
        <span className="text-sm font-bold text-foreground">Graph Playground</span>
        <select
          aria-label="Dataset"
          value={datasetId}
          onChange={(event) => setDatasetId(event.target.value)}
          className="min-w-36 rounded-lg border border-mac bg-muted text-foreground px-2.5 py-1 text-sm focus:outline-none"
        >
          <option value="">Select dataset...</option>
          {datasets.map((dataset) => (
            <option key={dataset.id} value={dataset.id}>{dataset.name}</option>
          ))}
        </select>
        {view && view.available_levels.length > 0 && !summary && (
          <select
            aria-label="Community level"
            value={level}
            onChange={(event) => setLevel(Number(event.target.value))}
            className="rounded-lg border border-mac bg-muted text-foreground px-2.5 py-1 text-sm focus:outline-none"
          >
            {view.available_levels.map((item) => <option key={item} value={item}>L{item}</option>)}
          </select>
        )}
        <button
          type="button"
          onClick={() => setPanelOpen((value) => !value)}
          aria-pressed={panelOpen}
          className={`rounded-lg border px-3 py-1 text-xs font-medium transition-all ${
            panelOpen
              ? "border-mac-accent bg-mac-accent text-ui-inverse !text-white shadow-sm"
              : "border-mac bg-surface/90 text-foreground hover:bg-surface-subtle"
          }`}
        >
          {panelOpen ? "Hide tools" : "Tools"}
        </button>
        <button
          type="button"
          onClick={() => setCmdOpen(true)}
          disabled={!graphState}
          className="ml-auto rounded-lg border border-mac bg-surface/90 px-3 py-1 text-xs font-medium text-foreground hover:bg-surface-subtle disabled:opacity-40 shadow-sm"
        >
          Search <kbd className="ml-1 rounded bg-muted px-1.5 py-0.5 text-[10px] text-foreground-muted border border-mac">Ctrl+K</kbd>
        </button>
        <ToolbarButton active={showFilters || activeFilters.size > 0} onClick={() => setShowFilters((value) => !value)}>
          Filters{activeFilters.size > 0 ? ` (${activeFilters.size})` : ""}
        </ToolbarButton>
        <ToolbarButton active={showLegend} onClick={() => setShowLegend((value) => !value)}>
          Legend
        </ToolbarButton>
        <button
          type="button"
          aria-label="Refresh graph analytics"
          onClick={() => void handleRefresh()}
          disabled={!datasetId || refreshing}
          className="rounded-lg border border-mac bg-surface/90 px-2.5 py-1 text-xs font-medium text-foreground hover:bg-surface-subtle disabled:opacity-40 shadow-sm"
        >
          {refreshing ? "..." : "Refresh"}
        </button>
      </div>

      {panelOpen && (
        <section className="absolute left-3 top-16 z-10 flex max-h-[calc(100vh-5rem)] w-[min(28rem,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-2xl border border-mac bg-surface/95 shadow-xl backdrop-blur-md text-foreground">
          {/* Segmented Control Tabs */}
          <div className="flex gap-1 overflow-x-auto border-b border-mac bg-muted/50 p-1.5">
            {TOOLS.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setTool(item.id)}
                className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                  tool === item.id
                    ? "bg-mac-accent text-ui-inverse !text-white shadow-sm font-semibold"
                    : "text-foreground-muted hover:bg-surface hover:text-foreground"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
          <form onSubmit={(event) => void runTool(event)} className="space-y-3 overflow-y-auto p-4">
            <ToolFields
              tool={tool}
              query={query}
              setQuery={setQuery}
              entityId={entityId}
              setEntityId={setEntityId}
              sourceId={sourceId}
              setSourceId={setSourceId}
              targetId={targetId}
              setTargetId={setTargetId}
              subgraphEntityId={subgraphEntityId}
              setSubgraphEntityId={setSubgraphEntityId}
              relationId={relationId}
              setRelationId={setRelationId}
              depth={depth}
              setDepth={setDepth}
            />
            {tool !== "json" && (
              <button
                type="submit"
                disabled={!datasetId || loading || !toolReady(tool, { query, entityId, sourceId, targetId, subgraphEntityId, relationId })}
                className="w-full rounded-xl bg-mac-accent hover:opacity-90 px-3 py-2 text-sm font-semibold !text-white shadow-sm transition-all disabled:opacity-40"
              >
                {loading ? "Running..." : `Run ${TOOLS.find((item) => item.id === tool)?.label}`}
              </button>
            )}
            {error && <div role="alert" className="rounded-xl bg-red-500/10 border border-red-500/20 px-3 py-2 text-sm text-red-500 font-medium">{error}</div>}
            {tool === "search" && searchResults.length > 0 && (
              <div className="space-y-1 border-t border-mac pt-3">
                {searchResults.map((entity) => (
                  <button
                    key={entity.id}
                    type="button"
                    onClick={() => setEntityId(entity.id)}
                    className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-surface-subtle"
                  >
                    <span className="text-sm font-medium text-foreground">{entity.canonical_name}</span>
                    <span className="font-mono text-[10px] text-foreground-muted">{entity.entity_type} · {entity.id}</span>
                  </button>
                ))}
              </div>
            )}
            {(tool === "json" || tool === "evidence") && (
              <pre aria-label="Raw JSON result" className="max-h-80 overflow-auto rounded-xl bg-surface-subtle border border-mac p-3 font-mono text-xs text-foreground">
                {payload === null ? "No response yet." : JSON.stringify(payload, null, 2)}
              </pre>
            )}
          </form>
        </section>
      )}

      {graphState && (
        <div className="absolute bottom-3 left-3 z-10 flex flex-wrap items-center gap-1 rounded-xl border border-mac bg-surface/95 p-1.5 shadow-lg backdrop-blur-md text-foreground">
          <Stat value={`${graphState.nodes.length} nodes`} />
          <Stat value={`${graphState.edges.length} edges`} />
          <Stat value={`${graphState.communities.size} groups`} />
          <Stat value={`${zoom.toFixed(1)}x`} />
          <button type="button" onClick={() => triggerCanvasEvent("graph:fit")} className="rounded px-2 py-1 text-xs text-foreground-muted hover:text-foreground hover:bg-surface-subtle transition-colors">Fit</button>
          <button type="button" onClick={() => triggerCanvasEvent("graph:reset")} className="rounded px-2 py-1 text-xs text-foreground-muted hover:text-foreground hover:bg-surface-subtle transition-colors">Reset layout</button>
          <button
            type="button"
            aria-pressed={physicsEnabled}
            onClick={() => setPhysicsEnabled((value) => !value)}
            className={`rounded px-2 py-1 text-xs font-medium transition-all ${
              physicsEnabled
                ? "bg-mac-accent !text-white font-semibold shadow-sm"
                : "text-foreground-muted hover:text-foreground hover:bg-surface-subtle"
            }`}
          >
            Physics {physicsEnabled ? "on" : "off"}
          </button>
          <button type="button" onClick={() => setShowLabels((value) => !value)} className="rounded px-2 py-1 text-xs text-foreground-muted hover:text-foreground hover:bg-surface-subtle transition-colors">Labels {showLabels ? "on" : "off"}</button>
        </div>
      )}

      {showLegend && graphState && (
        <div className="absolute bottom-3 right-3 z-10 min-w-44 rounded-2xl border border-mac bg-surface/95 p-3 shadow-xl backdrop-blur-md text-foreground">
          <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-foreground-muted">Groups ({graphState.communities.size})</div>
          <div className="max-h-60 overflow-y-auto space-y-1">
            {[...graphState.communities.values()].map((community) => (
              <div key={community.id} className="flex items-center gap-2 py-0.5 text-xs text-foreground font-medium">
                <span className="h-2.5 w-2.5 rounded-full shrink-0 shadow-sm" style={{ background: community.color }} />
                <span className="truncate">{community.name}</span>
              </div>
            ))}
          </div>
        </div>
      )}

       {showFilters && graphState && (
         <div className="absolute right-3 top-16 z-10 flex flex-col gap-1.5 max-h-[calc(100vh-6rem)] overflow-y-auto rounded-2xl border border-mac bg-surface/95 p-3 shadow-xl backdrop-blur-md">
           <button
             type="button"
             onClick={() => setActiveFilters(new Set())}
             disabled={activeFilters.size === 0}
             className="rounded-lg border border-mac bg-surface px-3 py-1 text-xs font-medium text-foreground hover:bg-surface-subtle disabled:opacity-40 shadow-sm"
           >
             Clear filters
           </button>
           {[...graphState.communities.values()].map((community) => (
            <button
              key={community.id}
              type="button"
              onClick={() => toggleFilter(community.id)}
              aria-pressed={activeFilters.has(community.id)}
              data-active={activeFilters.has(community.id)}
              className={`rounded-lg border px-3 py-1 text-xs font-medium transition-all ${
                activeFilters.has(community.id)
                  ? "border-mac-accent bg-mac-accent !text-white shadow-sm"
                  : "border-mac bg-surface text-foreground hover:bg-surface-subtle"
              }`}
            >
              {community.name}
            </button>
          ))}
        </div>
      )}

      {graphState && (
        <Inspector node={selectedNode} state={graphState} onSelectNode={setSelectedNode} onClose={() => setSelectedNode(null)} />
      )}
      {cmdOpen && graphState && (
        <CommandPalette state={graphState} onSelectNode={setSelectedNode} onClose={() => setCmdOpen(false)} />
      )}
    </div>
  );
}

interface ToolValues {
  query: string;
  entityId: string;
  sourceId: string;
  targetId: string;
  subgraphEntityId: string;
  relationId: string;
}

function toolReady(tool: Tool, values: ToolValues): boolean {
  if (tool === "search") return Boolean(values.query.trim());
  if (tool === "neighbors") return Boolean(values.entityId.trim());
  if (tool === "path") return Boolean(values.sourceId.trim() && values.targetId.trim());
  if (tool === "subgraph") return Boolean(values.subgraphEntityId.trim());
  if (tool === "evidence") return Boolean(values.relationId.trim());
  return true;
}

function uniqueEntities(entities: EntityView[]): EntityView[] {
  return [...new Map(entities.map((entity) => [entity.id, entity])).values()];
}

function toGraphSummary(response: { dataset_id: string; nodes: EntityView[]; relations: GraphSummary["relations"] }): GraphSummary {
  return {
    dataset_id: response.dataset_id,
    entity_count: response.nodes.length,
    relation_count: response.relations.length,
    nodes: response.nodes,
    relations: response.relations,
  };
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.detail : fallback;
}

const MAX_EXPLORER_NODES = 5000;
const MAX_EXPLORER_RELATIONS = 15000;

async function loadAllExplorerNodes(datasetId: string, communityLevel: number, signal: AbortSignal) {
  const nodes: ExplorerView["nodes"] = [];
  let cursor: string | undefined;
  do {
    const page = await graphApi.getExplorerNodes(datasetId, {
      cursor,
      limit: 3000,
      community_level: communityLevel,
    }, signal);
    nodes.push(...page.nodes);
    cursor = page.next_cursor ?? undefined;
    if (nodes.length >= MAX_EXPLORER_NODES) {
      nodes.length = MAX_EXPLORER_NODES;
      break;
    }
  } while (cursor);
  return nodes;
}

async function loadAllExplorerRelations(datasetId: string, signal: AbortSignal) {
  const relations: ExplorerView["relations"] = [];
  let cursor: string | undefined;
  do {
    const page = await graphApi.getExplorerRelations(datasetId, { cursor, limit: 5000 }, signal);
    relations.push(...page.relations);
    cursor = page.next_cursor ?? undefined;
    if (relations.length >= MAX_EXPLORER_RELATIONS) {
      relations.length = MAX_EXPLORER_RELATIONS;
      break;
    }
  } while (cursor);
  return relations;
}

function ToolbarButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      data-active={active}
      onClick={onClick}
      className={`rounded-lg border px-3 py-1 text-xs font-medium transition-all shadow-sm ${
        active
          ? "border-mac-accent bg-mac-accent !text-white font-semibold"
          : "border-mac bg-surface/90 text-foreground hover:bg-surface-subtle"
      }`}
    >
      {children}
    </button>
  );
}

function Stat({ value }: { value: string }) {
  return <span className="px-2 py-1 font-mono text-[10px] font-medium text-foreground-muted">{value}</span>;
}

interface ToolFieldsProps extends ToolValues {
  tool: Tool;
  setQuery: (value: string) => void;
  setEntityId: (value: string) => void;
  setSourceId: (value: string) => void;
  setTargetId: (value: string) => void;
  setSubgraphEntityId: (value: string) => void;
  setRelationId: (value: string) => void;
  depth: number;
  setDepth: (value: number) => void;
}

function ToolFields(props: ToolFieldsProps) {
  if (props.tool === "search") return <TextField label="Entity name" value={props.query} onChange={props.setQuery} placeholder="Alice or neural network" />;
  if (props.tool === "neighbors") return <TextField label="Entity ID" value={props.entityId} onChange={props.setEntityId} placeholder="ent_..." />;
  if (props.tool === "path") return (
    <div className="grid grid-cols-2 gap-2">
      <TextField label="Source entity ID" value={props.sourceId} onChange={props.setSourceId} placeholder="ent_source" />
      <TextField label="Target entity ID" value={props.targetId} onChange={props.setTargetId} placeholder="ent_target" />
      <DepthField value={props.depth} onChange={props.setDepth} />
    </div>
  );
  if (props.tool === "subgraph") return (
    <div className="grid grid-cols-[1fr_6rem] gap-2">
      <TextField label="Entity ID" value={props.subgraphEntityId} onChange={props.setSubgraphEntityId} placeholder="ent_root" />
      <DepthField value={props.depth} onChange={props.setDepth} max={2} />
    </div>
  );
  if (props.tool === "evidence") return <TextField label="Relation ID" value={props.relationId} onChange={props.setRelationId} placeholder="rel_..." />;
  return <p className="text-sm text-foreground-muted">Latest graph response and evidence payload.</p>;
}

function TextField({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder: string }) {
  return (
    <label className="block text-xs font-medium text-foreground-muted">
      {label}
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="mt-1 block w-full rounded-lg border border-mac bg-muted text-foreground placeholder:text-foreground-muted/60 px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-mac-accent"
      />
    </label>
  );
}

function DepthField({ value, onChange, max = 4 }: { value: number; onChange: (value: number) => void; max?: number }) {
  return (
    <label className="block text-xs font-medium text-foreground-muted">
      Max depth
      <input
        type="number"
        min={1}
        max={max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-1 block w-full rounded-lg border border-mac bg-muted text-foreground px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-mac-accent"
      />
    </label>
  );
}
