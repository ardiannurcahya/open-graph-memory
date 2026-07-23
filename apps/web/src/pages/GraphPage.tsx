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
  const [showHistory, setShowHistory] = useState(false);
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set());
  const [zoom, setZoom] = useState(1);
  const explorerRequestRef = useRef(0);
  const explorerAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    void datasetsApi.list().then(setDatasets).catch(() => undefined);
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
        <div className="absolute inset-0 flex items-center justify-center p-8 text-sm text-stone-400">
          {loading ? "Loading..." : "Select dataset to open graph playground."}
        </div>
      )}

      <div className="absolute left-3 right-3 top-3 z-10 flex flex-wrap items-center gap-2 rounded-lg border border-stone-200 bg-white/95 px-3 py-2 shadow-sm backdrop-blur">
        <span className="text-sm font-semibold text-stone-900">Graph Playground</span>
        <select
          aria-label="Dataset"
          value={datasetId}
          onChange={(event) => setDatasetId(event.target.value)}
          className="min-w-36 rounded-md border border-stone-300 px-2 py-1 text-sm"
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
            className="rounded-md border border-stone-300 px-2 py-1 text-sm"
          >
            {view.available_levels.map((item) => <option key={item} value={item}>L{item}</option>)}
          </select>
        )}
        <button
          type="button"
          onClick={() => setPanelOpen((value) => !value)}
          className="rounded-md border border-stone-900 bg-stone-900 px-3 py-1 text-xs text-ui-inverse"
        >
          {panelOpen ? "Hide tools" : "Show tools"}
        </button>
        <button
          type="button"
          onClick={() => setCmdOpen(true)}
          disabled={!graphState}
          className="ml-auto rounded-md border border-stone-200 px-3 py-1 text-xs text-stone-600 disabled:opacity-40"
        >
          Visible search <kbd className="ml-1 rounded bg-stone-100 px-1">Ctrl+K</kbd>
        </button>
        <ToolbarButton active={showFilters || activeFilters.size > 0} onClick={() => setShowFilters((value) => !value)}>Filters{activeFilters.size > 0 ? ` (${activeFilters.size})` : ""}</ToolbarButton>
        <ToolbarButton active={showLegend} onClick={() => setShowLegend((value) => !value)}>Legend</ToolbarButton>
        <button
          type="button"
          aria-label="Refresh graph analytics"
          onClick={() => void handleRefresh()}
          disabled={!datasetId || refreshing}
          className="rounded-md border border-stone-200 px-2 py-1 text-xs text-stone-600 disabled:opacity-40"
        >
          {refreshing ? "..." : "Refresh"}
        </button>
      </div>

      {panelOpen && (
        <section className="absolute left-3 top-16 z-10 flex max-h-[calc(100vh-5rem)] w-[min(28rem,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-xl border border-stone-200 bg-white/95 shadow-lg backdrop-blur">
          <div className="flex gap-1 overflow-x-auto border-b border-stone-200 p-2">
            {TOOLS.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setTool(item.id)}
                className={`whitespace-nowrap rounded-md px-2.5 py-1.5 text-xs font-medium ${
                  tool === item.id ? "bg-amber-600 text-ui-inverse" : "text-stone-600 hover:bg-stone-100"
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
                className="w-full rounded-md bg-stone-900 px-3 py-2 text-sm font-semibold text-ui-inverse disabled:opacity-40"
              >
                {loading ? "Running..." : `Run ${TOOLS.find((item) => item.id === tool)?.label}`}
              </button>
            )}
            {error && <div role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
            {tool === "search" && searchResults.length > 0 && (
              <div className="space-y-1 border-t border-stone-200 pt-3">
                {searchResults.map((entity) => (
                  <button
                    key={entity.id}
                    type="button"
                    onClick={() => setEntityId(entity.id)}
                    className="flex w-full items-center justify-between rounded-md px-2 py-2 text-left hover:bg-stone-100"
                  >
                    <span className="text-sm font-medium text-stone-800">{entity.canonical_name}</span>
                    <span className="font-mono text-[10px] text-stone-400">{entity.entity_type} · {entity.id}</span>
                  </button>
                ))}
              </div>
            )}
            {(tool === "json" || tool === "evidence") && (
              <pre aria-label="Raw JSON result" className="max-h-80 overflow-auto rounded-md bg-stone-950 p-3 text-xs text-stone-100">
                {payload === null ? "No response yet." : JSON.stringify(payload, null, 2)}
              </pre>
            )}
          </form>
        </section>
      )}

      {graphState && (
        <div className="absolute bottom-3 left-3 z-10 flex flex-wrap gap-1 rounded-lg border border-stone-200 bg-white/95 p-1.5 shadow-sm">
          <Stat value={`${graphState.nodes.length} nodes`} />
          <Stat value={`${graphState.edges.length} edges`} />
          <Stat value={`${graphState.communities.size} groups`} />
          <Stat value={`${zoom.toFixed(1)}x`} />
          <button type="button" onClick={() => triggerCanvasEvent("graph:fit")} className="px-2 py-1 text-xs text-stone-600">Fit</button>
          <button type="button" onClick={() => triggerCanvasEvent("graph:reset")} className="px-2 py-1 text-xs text-stone-600">Reset layout</button>
          <button
            type="button"
            aria-pressed={physicsEnabled}
            onClick={() => setPhysicsEnabled((value) => !value)}
            className={`rounded px-2 py-1 text-xs ${physicsEnabled ? "bg-stone-900 text-ui-inverse" : "text-stone-600"}`}
          >
            Physics {physicsEnabled ? "on" : "off"}
          </button>
          <button type="button" onClick={() => setShowLabels((value) => !value)} className="px-2 py-1 text-xs text-stone-600">Labels {showLabels ? "on" : "off"}</button>
        </div>
      )}

      {showLegend && graphState && (
        <div className="absolute bottom-3 right-3 z-10 min-w-44 rounded-lg border border-stone-200 bg-white p-3 shadow-sm">
          <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-stone-400">Groups</div>
          {[...graphState.communities.values()].map((community) => (
            <div key={community.id} className="flex items-center gap-2 py-0.5 text-xs text-stone-600">
              <span className="h-2 w-2 rounded-full" style={{ background: community.color }} />
              {community.name}
            </div>
          ))}
        </div>
      )}

       {showFilters && graphState && (
         <div className="absolute right-3 top-16 z-10 flex flex-col gap-1">
           <button type="button" onClick={() => setActiveFilters(new Set())} disabled={activeFilters.size === 0} className="rounded-full border border-stone-200 bg-white px-3 py-1 text-xs text-stone-600 disabled:opacity-40">Clear filters</button>
           {[...graphState.communities.values()].map((community) => (
            <button
              key={community.id}
              type="button"
              onClick={() => toggleFilter(community.id)}
              aria-pressed={activeFilters.has(community.id)}
              data-active={activeFilters.has(community.id)}
              className={`rounded-full border px-3 py-1 text-xs ${activeFilters.has(community.id) ? "border-stone-900 bg-stone-900 text-ui-inverse" : "border-stone-200 bg-white text-stone-600"}`}
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
  } while (cursor);
  return relations;
}

function ToolbarButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={active} data-active={active} onClick={onClick} className={`rounded-md border px-2 py-1 text-xs ${active ? "border-stone-900 bg-stone-900 text-ui-inverse" : "border-stone-200 text-stone-600"}`}>
      {children}
    </button>
  );
}

function Stat({ value }: { value: string }) {
  return <span className="px-2 py-1 font-mono text-[10px] text-stone-500">{value}</span>;
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
  return <p className="text-sm text-stone-500">Latest graph response and evidence payload.</p>;
}

function TextField({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder: string }) {
  return (
    <label className="block text-xs font-medium text-stone-600">
      {label}
      <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} className="mt-1 block w-full rounded-md border border-stone-300 px-3 py-2 text-sm text-stone-900" />
    </label>
  );
}

function DepthField({ value, onChange, max = 4 }: { value: number; onChange: (value: number) => void; max?: number }) {
  return (
    <label className="block text-xs font-medium text-stone-600">
      Max depth
      <input type="number" min={1} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))} className="mt-1 block w-full rounded-md border border-stone-300 px-3 py-2 text-sm" />
    </label>
  );
}
