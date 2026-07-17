declare module "graphology-layout-forceatlas2" {
  import type Graph from "graphology";

  interface ForceAtlas2Settings {
    barnesHutOptimize?: boolean;
    barnesHutTheta?: number;
    adjustSizes?: boolean;
    gravity?: number;
    strongGravityMode?: boolean;
    slowDown?: number;
    linLogMode?: boolean;
    outboundAttractionDistribution?: boolean;
    scalingRatio?: number;
    edgeWeightInfluence?: number;
    alignNodeSiblings?: boolean;
  }

  interface ForceAtlas2Params {
    iterations?: number;
    settings?: ForceAtlas2Settings;
    getWeight?: string | ((edge: string, a: unknown, b: unknown, e: unknown) => number);
  }

  type ForceAtlas2Layout = {
    (graph: Graph, params: number | ForceAtlas2Params): Record<string, { x: number; y: number }>;
    assign(graph: Graph, params: number | ForceAtlas2Params): void;
    inferSettings(graph: Graph | number): ForceAtlas2Settings;
  };

  const forceAtlas2: ForceAtlas2Layout;
  export = forceAtlas2;
}
