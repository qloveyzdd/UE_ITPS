import type { GraphResult } from "./graph-db";

export function filterGraphByKinds(
  graph: GraphResult,
  hiddenKinds: ReadonlySet<string>,
): GraphResult {
  if (hiddenKinds.size === 0) return graph;
  const nodes = graph.nodes.filter((node) => !hiddenKinds.has(node.kind));
  const nodeIds = new Set(nodes.map((node) => node.id));
  return {
    ...graph,
    nodes,
    edges: graph.edges.filter(
      (edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target),
    ),
  };
}
