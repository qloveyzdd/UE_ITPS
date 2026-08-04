import type { Database, SqlJsStatic } from "sql.js";

export type Certainty = "observed" | "resolved" | "inferred";

export interface Occurrence {
  role: string;
  root: string;
  path: string;
  line: number;
  endLine: number | null;
  probeSchema: string;
}

export interface Evidence {
  root: string | null;
  path: string | null;
  line: number | null;
  endLine: number | null;
  probeSchema: string;
  detail: Record<string, unknown>;
}

export interface GraphNode {
  id: string;
  kind: string;
  name: string;
  qualifiedName: string;
  namespace: string | null;
  owner: string | null;
  signature: string | null;
  linkage: string | null;
  properties: Record<string, unknown>;
  occurrences: Occurrence[];
  distance: number;
}

export interface SearchCandidate {
  id: string;
  kind: string;
  name: string;
  qualifiedName: string;
  signature: string | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: string;
  certainty: Certainty;
  resolutionStatus: string;
  confidence: number;
  properties: Record<string, unknown>;
  evidence: Evidence[];
}

export interface GraphResult {
  centerId: string;
  focusIds: string[];
  nodes: GraphNode[];
  edges: GraphEdge[];
  connectionCount: number;
  requestedConnectionCount: number;
  truncated: boolean;
}

export interface DatabaseSummary {
  schemaVersion: string;
  projectKey: string;
  createdAt: string;
  nodeCount: number;
  relationCount: number;
  warningCount: number;
}

interface RawNodeRow {
  node_id: string;
  kind: string;
  name: string;
  qualified_name: string | null;
  namespace: string | null;
  owner: string | null;
  signature: string | null;
  linkage: string | null;
  properties_json: string;
}

interface RawEdgeRow {
  relation_id: string;
  source_id: string;
  target_id: string;
  kind: string;
  certainty: Certainty;
  resolution_status: string;
  confidence: number;
  properties_json: string;
}

interface RelationArc {
  edgeId: string;
  targetId: string;
}

interface RelationIndex {
  edgeById: Map<string, RawEdgeRow>;
  adjacency: Map<string, RelationArc[]>;
}

const REQUIRED_TABLES = [
  "metadata",
  "snapshot",
  "nodes",
  "occurrences",
  "relations",
  "relation_evidence",
];

let sqlRuntime: Promise<SqlJsStatic> | null = null;

function runtime(): Promise<SqlJsStatic> {
  if (sqlRuntime) return sqlRuntime;
  sqlRuntime = new Promise<SqlJsStatic>((resolve, reject) => {
    const start = () => {
      const initializer = window.initSqlJs;
      if (!initializer) {
        reject(new Error("本地 SQLite 引擎没有正确加载。"));
        return;
      }
      initializer().then(resolve, reject);
    };
    if (window.initSqlJs) {
      start();
      return;
    }
    const script = document.createElement("script");
    script.src = "/vendor/sql-asm.js";
    script.async = true;
    script.dataset.ueItpsSqlite = "true";
    script.addEventListener("load", start, { once: true });
    script.addEventListener(
      "error",
      () => reject(new Error("无法加载 show 内置的 SQLite 引擎。")),
      { once: true },
    );
    document.head.appendChild(script);
  });
  return sqlRuntime;
}

function parseJson(value: unknown): Record<string, unknown> {
  if (typeof value !== "string" || value.length === 0) return {};
  try {
    const parsed: unknown = JSON.parse(value);
    return parsed !== null && typeof parsed === "object"
      ? (parsed as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}

function chunks<T>(values: T[], size = 400): T[][] {
  const result: T[][] = [];
  for (let index = 0; index < values.length; index += size) {
    result.push(values.slice(index, index + size));
  }
  return result;
}

function placeholders(count: number): string {
  return Array.from({ length: count }, () => "?").join(",");
}

function escapeLike(value: string): string {
  return value.replace(/[\\%_]/g, "\\$&");
}

export class GraphDatabase {
  private relationIndexCache: RelationIndex | null = null;

  private constructor(private readonly db: Database) {}

  static async open(bytes: Uint8Array): Promise<GraphDatabase> {
    const SQL = await runtime();
    const graphDb = new GraphDatabase(new SQL.Database(bytes));
    graphDb.validate();
    return graphDb;
  }

  close(): void {
    this.db.close();
  }

  private validate(): void {
    const rows = this.rows<{ name: string }>(
      "SELECT name FROM sqlite_master WHERE type = 'table'",
    );
    const names = new Set(rows.map((row) => String(row.name)));
    const missing = REQUIRED_TABLES.filter((name) => !names.has(name));
    if (missing.length > 0) {
      this.close();
      throw new Error(`不是有效的 UE ITPS 信息池快照，缺少表：${missing.join("、")}`);
    }
  }

  summary(): DatabaseSummary {
    const schema = this.rows<{ value: string }>(
      "SELECT value FROM metadata WHERE key = 'schema_version' LIMIT 1",
    )[0];
    const scan = this.rows<{
      project_key: string;
      created_at: string;
      node_count: number;
      relation_count: number;
      warning_count: number;
    }>(
      `SELECT project_key, created_at, node_count, relation_count, warning_count
       FROM snapshot LIMIT 1`,
    )[0];

    if (!scan) throw new Error("数据库中没有可用的扫描记录。");
    return {
      schemaVersion: String(schema?.value ?? "unknown"),
      projectKey: String(scan.project_key),
      createdAt: String(scan.created_at),
      nodeCount: Number(scan.node_count),
      relationCount: Number(scan.relation_count),
      warningCount: Number(scan.warning_count),
    };
  }

  search(selector: string, limit = 30): SearchCandidate[] {
    const value = selector.trim();
    if (!value) return [];
    const contains = `%${escapeLike(value)}%`;
    const startsWith = `${escapeLike(value)}%`;
    const rows = this.rows<RawNodeRow>(
      `SELECT node_id, kind, name, qualified_name, namespace, owner,
              signature, linkage, properties_json
       FROM nodes
       WHERE name LIKE ? ESCAPE '\\' COLLATE NOCASE
          OR qualified_name LIKE ? ESCAPE '\\' COLLATE NOCASE
       ORDER BY
         CASE
           WHEN qualified_name = ? COLLATE NOCASE THEN 0
           WHEN name = ? COLLATE NOCASE THEN 1
           WHEN qualified_name LIKE ? ESCAPE '\\' COLLATE NOCASE THEN 2
           WHEN name LIKE ? ESCAPE '\\' COLLATE NOCASE THEN 3
           ELSE 4
         END,
         kind,
         qualified_name COLLATE NOCASE,
         signature COLLATE NOCASE
       LIMIT ?`,
      [contains, contains, value, value, startsWith, startsWith, limit],
    );
    return rows.map((row) => ({
      id: String(row.node_id),
      kind: String(row.kind),
      name: String(row.name),
      qualifiedName: String(row.qualified_name ?? row.name),
      signature: row.signature === null ? null : String(row.signature),
    }));
  }

  queryGraph(centerId: string, depth: number, maxNodes: number): GraphResult {
    const safeDepth = Math.min(4, Math.max(1, Math.trunc(depth)));
    const safeMaxNodes = Math.min(300, Math.max(10, Math.trunc(maxNodes)));
    const centerExists = this.rows<{ node_id: string }>(
      "SELECT node_id FROM nodes WHERE node_id = ? LIMIT 1",
      [centerId],
    )[0];
    if (!centerExists) throw new Error("中心节点不存在或数据库已经更换。");

    const visited = new Set<string>([centerId]);
    const distances = new Map<string, number>([[centerId, 0]]);
    const edgeRows = new Map<string, RawEdgeRow>();
    let frontier = [centerId];
    let truncated = false;

    for (let distance = 1; distance <= safeDepth && frontier.length > 0; distance += 1) {
      const marks = placeholders(frontier.length);
      const rows = this.rows<RawEdgeRow>(
        `SELECT relation_id, source_id, target_id, kind, certainty,
                resolution_status, confidence, properties_json
         FROM relations
         WHERE source_id IN (${marks}) OR target_id IN (${marks})
         ORDER BY
           CASE certainty WHEN 'observed' THEN 0 WHEN 'resolved' THEN 1 ELSE 2 END,
           confidence DESC,
           kind,
           relation_id
         LIMIT ?`,
        [...frontier, ...frontier, safeMaxNodes * 12],
      );
      const next = new Set<string>();

      for (const row of rows) {
        const source = String(row.source_id);
        const target = String(row.target_id);
        const neighbor = frontier.includes(source) ? target : source;
        if (!visited.has(neighbor)) {
          if (visited.size >= safeMaxNodes) {
            truncated = true;
            continue;
          }
          visited.add(neighbor);
          distances.set(neighbor, distance);
          next.add(neighbor);
        }
        if (visited.has(source) && visited.has(target)) {
          edgeRows.set(String(row.relation_id), row);
        }
      }
      if (rows.length >= safeMaxNodes * 12) truncated = true;
      frontier = [...next].sort();
    }

    return this.buildGraphResult({
      centerId,
      focusIds: [centerId],
      nodeIds: [...visited],
      distances,
      edgeRows,
      connectionCount: 0,
      requestedConnectionCount: 0,
      truncated,
    });
  }

  queryRelevantGraph(focusIds: string[]): GraphResult {
    const uniqueFocusIds = [...new Set(focusIds.map((id) => id.trim()).filter(Boolean))];
    if (uniqueFocusIds.length === 0) throw new Error("请至少选择一个关注节点。");
    const existing = new Set<string>();
    for (const group of chunks(uniqueFocusIds)) {
      const rows = this.rows<{ node_id: string }>(
        `SELECT node_id FROM nodes WHERE node_id IN (${placeholders(group.length)})`,
        group,
      );
      for (const row of rows) existing.add(String(row.node_id));
    }
    if (existing.size !== uniqueFocusIds.length) {
      throw new Error("部分关注节点不存在或数据库已经更换。");
    }
    if (uniqueFocusIds.length === 1) {
      return this.buildGraphResult({
        centerId: uniqueFocusIds[0],
        focusIds: uniqueFocusIds,
        nodeIds: uniqueFocusIds,
        distances: new Map([[uniqueFocusIds[0], 0]]),
        edgeRows: new Map(),
        connectionCount: 0,
        requestedConnectionCount: 0,
        truncated: false,
      });
    }

    const { edgeById, adjacency } = this.relationIndex();

    let rootId = "__ue_itps_focus_root__";
    while (existing.has(rootId) || adjacency.has(rootId)) rootId += "_";
    const syntheticEdges = new Set<string>();
    const syntheticAdjacency = new Map<string, RelationArc[]>();
    const addSyntheticArc = (sourceId: string, targetId: string, edgeId: string) => {
      const arcs = syntheticAdjacency.get(sourceId) ?? [];
      arcs.push({ edgeId, targetId });
      syntheticAdjacency.set(sourceId, arcs);
    };
    uniqueFocusIds.forEach((focusId, index) => {
      let edgeId = `__ue_itps_focus_edge_${index}__`;
      while (edgeById.has(edgeId) || syntheticEdges.has(edgeId)) edgeId += "_";
      syntheticEdges.add(edgeId);
      addSyntheticArc(rootId, focusId, edgeId);
      addSyntheticArc(focusId, rootId, edgeId);
    });
    const arcsFor = (nodeId: string): RelationArc[] => {
      const baseArcs = adjacency.get(nodeId) ?? [];
      const extraArcs = syntheticAdjacency.get(nodeId) ?? [];
      return extraArcs.length === 0 ? baseArcs : [...baseArcs, ...extraArcs];
    };

    const discovery = new Map<string, number>();
    const low = new Map<string, number>();
    const edgeStack: string[] = [];
    const relevantEdgeIds = new Set<string>();
    let discoveryIndex = 0;

    const collectComponent = (boundaryEdgeId: string) => {
      const componentEdgeIds: string[] = [];
      let syntheticCount = 0;
      while (edgeStack.length > 0) {
        const edgeId = edgeStack.pop()!;
        componentEdgeIds.push(edgeId);
        if (syntheticEdges.has(edgeId)) syntheticCount += 1;
        if (edgeId === boundaryEdgeId) break;
      }
      if (syntheticCount < 2) return;
      for (const edgeId of componentEdgeIds) {
        if (!syntheticEdges.has(edgeId)) relevantEdgeIds.add(edgeId);
      }
    };

    type DfsFrame = {
      nodeId: string;
      parentId: string | null;
      parentEdgeId: string | null;
      nextArcIndex: number;
    };
    const roots = [rootId, ...adjacency.keys()];
    for (const startId of roots) {
      if (discovery.has(startId)) continue;
      discoveryIndex += 1;
      discovery.set(startId, discoveryIndex);
      low.set(startId, discoveryIndex);
      const frames: DfsFrame[] = [{
        nodeId: startId,
        parentId: null,
        parentEdgeId: null,
        nextArcIndex: 0,
      }];

      while (frames.length > 0) {
        const frame = frames[frames.length - 1];
        const arcs = arcsFor(frame.nodeId);
        if (frame.nextArcIndex < arcs.length) {
          const arc = arcs[frame.nextArcIndex];
          frame.nextArcIndex += 1;
          if (arc.edgeId === frame.parentEdgeId) continue;
          if (!discovery.has(arc.targetId)) {
            edgeStack.push(arc.edgeId);
            discoveryIndex += 1;
            discovery.set(arc.targetId, discoveryIndex);
            low.set(arc.targetId, discoveryIndex);
            frames.push({
              nodeId: arc.targetId,
              parentId: frame.nodeId,
              parentEdgeId: arc.edgeId,
              nextArcIndex: 0,
            });
          } else if ((discovery.get(arc.targetId) ?? 0) < (discovery.get(frame.nodeId) ?? 0)) {
            edgeStack.push(arc.edgeId);
            low.set(
              frame.nodeId,
              Math.min(low.get(frame.nodeId) ?? 0, discovery.get(arc.targetId) ?? 0),
            );
          }
          continue;
        }

        frames.pop();
        if (frame.parentId === null || frame.parentEdgeId === null) continue;
        low.set(
          frame.parentId,
          Math.min(low.get(frame.parentId) ?? 0, low.get(frame.nodeId) ?? 0),
        );
        if ((low.get(frame.nodeId) ?? 0) >= (discovery.get(frame.parentId) ?? 0)) {
          collectComponent(frame.parentEdgeId);
        }
      }
    }

    const edgeRows = new Map<string, RawEdgeRow>();
    const visibleIds = new Set(uniqueFocusIds);
    for (const edgeId of relevantEdgeIds) {
      const row = edgeById.get(edgeId);
      if (!row) continue;
      edgeRows.set(edgeId, row);
      visibleIds.add(String(row.source_id));
      visibleIds.add(String(row.target_id));
    }

    const requestedConnectionCount = uniqueFocusIds.length * (uniqueFocusIds.length - 1) / 2;
    let connectionCount = 0;
    const remainingFocusIds = new Set(uniqueFocusIds);
    while (remainingFocusIds.size > 0) {
      const startId = remainingFocusIds.values().next().value as string;
      const componentFocusIds = new Set<string>();
      const componentVisited = new Set<string>([startId]);
      const componentFrontier = [startId];
      for (let index = 0; index < componentFrontier.length; index += 1) {
        const id = componentFrontier[index];
        if (remainingFocusIds.has(id)) componentFocusIds.add(id);
        for (const arc of adjacency.get(id) ?? []) {
          const neighbor = arc.targetId;
          if (componentVisited.has(neighbor)) continue;
          componentVisited.add(neighbor);
          componentFrontier.push(neighbor);
        }
      }
      for (const id of componentFocusIds) remainingFocusIds.delete(id);
      connectionCount += componentFocusIds.size * (componentFocusIds.size - 1) / 2;
    }

    const distances = new Map(uniqueFocusIds.map((id) => [id, 0]));
    let distanceFrontier = [...uniqueFocusIds];
    while (distanceFrontier.length > 0) {
      const next: string[] = [];
      for (const id of distanceFrontier) {
        const distance = distances.get(id) ?? 0;
        for (const arc of adjacency.get(id) ?? []) {
          const neighbor = arc.targetId;
          if (!visibleIds.has(neighbor)) continue;
          if (distances.has(neighbor)) continue;
          distances.set(neighbor, distance + 1);
          next.push(neighbor);
        }
      }
      distanceFrontier = next;
    }

    return this.buildGraphResult({
      centerId: uniqueFocusIds[0],
      focusIds: uniqueFocusIds,
      nodeIds: [...visibleIds],
      distances,
      edgeRows,
      connectionCount,
      requestedConnectionCount,
      truncated: false,
    });
  }

  private relationIndex(): RelationIndex {
    if (this.relationIndexCache) return this.relationIndexCache;
    const rows = this.rows<RawEdgeRow>(
      `SELECT relation_id, source_id, target_id, kind, certainty,
              resolution_status, confidence, properties_json
       FROM relations
       ORDER BY
         CASE certainty WHEN 'observed' THEN 0 WHEN 'resolved' THEN 1 ELSE 2 END,
         confidence DESC,
         kind,
         relation_id`,
    );
    const edgeById = new Map<string, RawEdgeRow>();
    const adjacency = new Map<string, RelationArc[]>();
    const addArc = (sourceId: string, targetId: string, edgeId: string) => {
      const arcs = adjacency.get(sourceId) ?? [];
      arcs.push({ edgeId, targetId });
      adjacency.set(sourceId, arcs);
    };
    for (const row of rows) {
      const edgeId = String(row.relation_id);
      const sourceId = String(row.source_id);
      const targetId = String(row.target_id);
      edgeById.set(edgeId, row);
      if (sourceId === targetId) continue;
      addArc(sourceId, targetId, edgeId);
      addArc(targetId, sourceId, edgeId);
    }
    this.relationIndexCache = { edgeById, adjacency };
    return this.relationIndexCache;
  }

  private buildGraphResult({
    centerId,
    focusIds,
    nodeIds,
    distances,
    edgeRows,
    connectionCount,
    requestedConnectionCount,
    truncated,
  }: {
    centerId: string;
    focusIds: string[];
    nodeIds: string[];
    distances: Map<string, number>;
    edgeRows: Map<string, RawEdgeRow>;
    connectionCount: number;
    requestedConnectionCount: number;
    truncated: boolean;
  }): GraphResult {
    const rawNodes: RawNodeRow[] = [];
    for (const group of chunks(nodeIds)) {
      rawNodes.push(
        ...this.rows<RawNodeRow>(
          `SELECT node_id, kind, name, qualified_name, namespace, owner,
                  signature, linkage, properties_json
           FROM nodes WHERE node_id IN (${placeholders(group.length)})`,
          group,
        ),
      );
    }

    const occurrences = new Map<string, Occurrence[]>();
    for (const group of chunks(nodeIds)) {
      const rows = this.rows<{
        node_id: string;
        role: string;
        root: string;
        path: string;
        line: number;
        end_line: number | null;
        probe_schema: string;
      }>(
        `SELECT node_id, role, root, path, line, end_line, probe_schema
         FROM occurrences WHERE node_id IN (${placeholders(group.length)})
         ORDER BY path COLLATE NOCASE, line, role`,
        group,
      );
      for (const row of rows) {
        const id = String(row.node_id);
        const values = occurrences.get(id) ?? [];
        values.push({
          role: String(row.role),
          root: String(row.root),
          path: String(row.path),
          line: Number(row.line),
          endLine: row.end_line === null ? null : Number(row.end_line),
          probeSchema: String(row.probe_schema),
        });
        occurrences.set(id, values);
      }
    }

    const edgeIds = [...edgeRows.keys()];
    const evidence = new Map<string, Evidence[]>();
    for (const group of chunks(edgeIds)) {
      if (group.length === 0) continue;
      const rows = this.rows<{
        relation_id: string;
        root: string | null;
        path: string | null;
        line: number | null;
        end_line: number | null;
        probe_schema: string;
        detail_json: string;
      }>(
        `SELECT relation_id, root, path, line, end_line, probe_schema, detail_json
         FROM relation_evidence
         WHERE relation_id IN (${placeholders(group.length)})
         ORDER BY path COLLATE NOCASE, line`,
        group,
      );
      for (const row of rows) {
        const id = String(row.relation_id);
        const values = evidence.get(id) ?? [];
        values.push({
          root: row.root === null ? null : String(row.root),
          path: row.path === null ? null : String(row.path),
          line: row.line === null ? null : Number(row.line),
          endLine: row.end_line === null ? null : Number(row.end_line),
          probeSchema: String(row.probe_schema),
          detail: parseJson(row.detail_json),
        });
        evidence.set(id, values);
      }
    }

    const nodes = rawNodes
      .map<GraphNode>((row) => ({
        id: String(row.node_id),
        kind: String(row.kind),
        name: String(row.name),
        qualifiedName: String(row.qualified_name ?? row.name),
        namespace: row.namespace === null ? null : String(row.namespace),
        owner: row.owner === null ? null : String(row.owner),
        signature: row.signature === null ? null : String(row.signature),
        linkage: row.linkage === null ? null : String(row.linkage),
        properties: parseJson(row.properties_json),
        occurrences: occurrences.get(String(row.node_id)) ?? [],
        distance: distances.get(String(row.node_id)) ?? 0,
      }))
      .sort((left, right) =>
        left.distance - right.distance || left.qualifiedName.localeCompare(right.qualifiedName),
      );

    const edges = [...edgeRows.values()]
      .map<GraphEdge>((row) => ({
        id: String(row.relation_id),
        source: String(row.source_id),
        target: String(row.target_id),
        kind: String(row.kind),
        certainty: String(row.certainty) as Certainty,
        resolutionStatus: String(row.resolution_status),
        confidence: Number(row.confidence),
        properties: parseJson(row.properties_json),
        evidence: evidence.get(String(row.relation_id)) ?? [],
      }))
      .sort((left, right) =>
        left.kind.localeCompare(right.kind) || left.id.localeCompare(right.id),
      );

    return {
      centerId,
      focusIds,
      nodes,
      edges,
      connectionCount,
      requestedConnectionCount,
      truncated,
    };
  }

  private rows<T extends object>(sql: string, parameters: unknown[] = []): T[] {
    const statement = this.db.prepare(sql);
    try {
      statement.bind(parameters as (string | number | null | Uint8Array)[]);
      const result: T[] = [];
      while (statement.step()) result.push(statement.getAsObject() as T);
      return result;
    } finally {
      statement.free();
    }
  }
}
