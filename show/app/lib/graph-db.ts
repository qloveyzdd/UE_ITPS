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
  memberRelationCount: number;
  memberRelations: MemberRelation[];
}

export interface MemberRelation {
  relationId: string;
  sourceId: string;
  sourceName: string;
  targetId: string;
  targetName: string;
}

export interface MemberExpansion {
  nodes: GraphNode[];
  edges: GraphEdge[];
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
  evidence_relation_ids?: string[];
}

interface RelationArc {
  edgeId: string;
  targetId: string;
}

interface RelationIndex {
  edgeById: Map<string, RawEdgeRow>;
  adjacency: Map<string, RelationArc[]>;
}

const SEMANTIC_RELATION_KINDS = [
  "CALLS",
  "INHERITS",
  "USES_TYPE",
  "INCLUDES",
  "BINDS_CALLBACK",
  "TAKES_ADDRESS",
] as const;

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
  private semanticIndexCache = new Map<string, RelationIndex>();

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
    const center = this.rows<{ node_id: string; kind: string }>(
      "SELECT node_id, kind FROM nodes WHERE node_id = ? LIMIT 1",
      [centerId],
    )[0];
    if (!center) throw new Error("中心节点不存在或数据库已经更换。");

    const index = this.semanticIndex(
      center.kind === "class" || center.kind === "struct",
    );

    const visited = new Set<string>([centerId]);
    const distances = new Map<string, number>([[centerId, 0]]);
    let frontier = [centerId];
    let truncated = false;

    for (let distance = 1; distance <= safeDepth && frontier.length > 0; distance += 1) {
      const next = new Set<string>();
      for (const id of frontier) {
        for (const arc of index.adjacency.get(id) ?? []) {
          if (visited.has(arc.targetId)) continue;
          if (visited.size >= safeMaxNodes) {
            truncated = true;
            continue;
          }
          visited.add(arc.targetId);
          distances.set(arc.targetId, distance);
          next.add(arc.targetId);
        }
      }
      frontier = [...next].sort();
    }

    const edgeRows = new Map<string, RawEdgeRow>();
    for (const [edgeId, row] of index.edgeById) {
      if (visited.has(String(row.source_id)) && visited.has(String(row.target_id))) {
        edgeRows.set(edgeId, row);
      }
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
    const existing = new Map<string, string>();
    for (const group of chunks(uniqueFocusIds)) {
      const rows = this.rows<{ node_id: string; kind: string }>(
        `SELECT node_id, kind FROM nodes WHERE node_id IN (${placeholders(group.length)})`,
        group,
      );
      for (const row of rows) existing.set(String(row.node_id), String(row.kind));
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

    const projectMembers = uniqueFocusIds.every((id) => {
      const kind = existing.get(id);
      return kind === "class" || kind === "struct";
    });
    const { edgeById, adjacency } = this.semanticIndex(projectMembers);
    const relevantEdgeIds = new Set<string>();
    const visibleIds = new Set(uniqueFocusIds);
    const requestedConnectionCount = uniqueFocusIds.length * (uniqueFocusIds.length - 1) / 2;
    let connectionCount = 0;
    for (let left = 0; left < uniqueFocusIds.length; left += 1) {
      for (let right = left + 1; right < uniqueFocusIds.length; right += 1) {
        const startId = uniqueFocusIds[left];
        const targetId = uniqueFocusIds[right];
        const queue = [startId];
        const predecessor = new Map<string, string>();
        const seen = new Set<string>([startId]);
        for (let index = 0; index < queue.length && !seen.has(targetId); index += 1) {
          for (const arc of adjacency.get(queue[index]) ?? []) {
            if (seen.has(arc.targetId)) continue;
            seen.add(arc.targetId);
            predecessor.set(arc.targetId, queue[index]);
            queue.push(arc.targetId);
          }
        }
        if (!seen.has(targetId)) continue;
        connectionCount += 1;
        const path = [targetId];
        while (path[path.length - 1] !== startId) {
          path.push(predecessor.get(path[path.length - 1])!);
        }
        path.reverse();
        for (let index = 0; index + 1 < path.length; index += 1) {
          const sourceId = path[index];
          const targetPathId = path[index + 1];
          visibleIds.add(sourceId);
          visibleIds.add(targetPathId);
          for (const arc of adjacency.get(sourceId) ?? []) {
            if (arc.targetId === targetPathId) relevantEdgeIds.add(arc.edgeId);
          }
        }
      }
    }

    const edgeRows = new Map<string, RawEdgeRow>();
    for (const edgeId of relevantEdgeIds) {
      const row = edgeById.get(edgeId);
      if (row) edgeRows.set(edgeId, row);
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

  queryMemberRelations(relationIds: string[]): MemberExpansion {
    const uniqueRelationIds = [...new Set(relationIds.map((id) => id.trim()).filter(Boolean))];
    if (uniqueRelationIds.length === 0) return { nodes: [], edges: [] };
    const rawEdges: RawEdgeRow[] = [];
    for (const group of chunks(uniqueRelationIds)) {
      rawEdges.push(
        ...this.rows<RawEdgeRow>(
          `SELECT relation_id, source_id, target_id, kind, certainty,
                  resolution_status, confidence, properties_json
           FROM relations
           WHERE relation_id IN (${placeholders(group.length)})
             AND resolution_status = 'resolved'
             AND kind IN (${placeholders(SEMANTIC_RELATION_KINDS.length)})`,
          [...group, ...SEMANTIC_RELATION_KINDS],
        ),
      );
    }
    const edgeRows = new Map(rawEdges.map((row) => [String(row.relation_id), row]));
    const nodeIds = [...new Set(rawEdges.flatMap((row) => [
      String(row.source_id),
      String(row.target_id),
    ]))];
    if (nodeIds.length === 0) return { nodes: [], edges: [] };
    const result = this.buildGraphResult({
      centerId: nodeIds[0],
      focusIds: [],
      nodeIds,
      distances: new Map(nodeIds.map((id) => [id, 1])),
      edgeRows,
      connectionCount: 0,
      requestedConnectionCount: 0,
      truncated: false,
    });
    return { nodes: result.nodes, edges: result.edges };
  }

  private semanticIndex(projectMembers: boolean): RelationIndex {
    const cacheKey = projectMembers ? "types" : "symbols";
    const cached = this.semanticIndexCache.get(cacheKey);
    if (cached) return cached;
    const nodeRows = this.rows<RawNodeRow>(
      `SELECT node_id, kind, name, qualified_name, namespace, owner,
              signature, linkage, properties_json FROM nodes`,
    );
    const nodesById = new Map(nodeRows.map((row) => [String(row.node_id), row]));
    const ownerIds = new Map(
      nodeRows
        .filter((row) => row.kind === "class" || row.kind === "struct")
        .map((row) => [String(row.qualified_name ?? row.name), String(row.node_id)]),
    );
    const projectNode = (nodeId: string): string => {
      if (!projectMembers) return nodeId;
      const row = nodesById.get(nodeId);
      if (!row || (row.kind !== "member_function" && row.kind !== "member_variable")) {
        return nodeId;
      }
      const qualifiedName = String(row.qualified_name ?? "");
      const qualifiedOwner = qualifiedName.includes("::")
        ? qualifiedName.slice(0, qualifiedName.lastIndexOf("::"))
        : "";
      return ownerIds.get(qualifiedOwner) ?? ownerIds.get(String(row.owner ?? "")) ?? nodeId;
    };
    const rows = this.rows<RawEdgeRow>(
      `SELECT relation_id, source_id, target_id, kind, certainty,
              resolution_status, confidence, properties_json
       FROM relations
       WHERE resolution_status = 'resolved'
         AND kind IN (${placeholders(SEMANTIC_RELATION_KINDS.length)})
       ORDER BY
         CASE certainty WHEN 'observed' THEN 0 WHEN 'resolved' THEN 1 ELSE 2 END,
         confidence DESC,
         kind,
         relation_id`,
      [...SEMANTIC_RELATION_KINDS],
    );
    const groups = new Map<string, {
      sourceId: string;
      targetId: string;
      kind: string;
      rows: RawEdgeRow[];
    }>();
    for (const row of rows) {
      const sourceId = projectNode(String(row.source_id));
      const targetId = projectNode(String(row.target_id));
      if (sourceId === targetId) continue;
      const key = `${sourceId}\u0000${String(row.kind)}\u0000${targetId}`;
      const group = groups.get(key) ?? { sourceId, targetId, kind: String(row.kind), rows: [] };
      group.rows.push(row);
      groups.set(key, group);
    }
    if (projectMembers) {
      for (const [key, group] of groups) {
        if (group.kind !== "USES_TYPE") continue;
        const callKey = `${group.sourceId}\u0000CALLS\u0000${group.targetId}`;
        if (groups.has(callKey)) groups.delete(key);
      }
    }
    const edgeById = new Map<string, RawEdgeRow>();
    const adjacency = new Map<string, RelationArc[]>();
    const addArc = (sourceId: string, targetId: string, edgeId: string) => {
      const arcs = adjacency.get(sourceId) ?? [];
      arcs.push({ edgeId, targetId });
      adjacency.set(sourceId, arcs);
    };
    let aggregateIndex = 0;
    for (const key of [...groups.keys()].sort()) {
      const group = groups.get(key)!;
      const representative = group.rows[0];
      const unchanged = group.rows.length === 1
        && String(representative.source_id) === group.sourceId
        && String(representative.target_id) === group.targetId;
      const edgeId = unchanged
        ? String(representative.relation_id)
        : `semantic:${aggregateIndex++}`;
      const memberRelations: MemberRelation[] = group.rows.map((row) => ({
        relationId: String(row.relation_id),
        sourceId: String(row.source_id),
        sourceName: String(nodesById.get(String(row.source_id))?.qualified_name ?? row.source_id),
        targetId: String(row.target_id),
        targetName: String(nodesById.get(String(row.target_id))?.qualified_name ?? row.target_id),
      }));
      const prepared: RawEdgeRow = {
        ...representative,
        relation_id: edgeId,
        source_id: group.sourceId,
        target_id: group.targetId,
        confidence: Math.max(...group.rows.map((row) => Number(row.confidence))),
        properties_json: JSON.stringify({
          ...parseJson(representative.properties_json),
          memberRelationCount: memberRelations.length,
          memberRelations,
        }),
        evidence_relation_ids: group.rows.map((row) => String(row.relation_id)),
      };
      edgeById.set(edgeId, prepared);
      addArc(group.sourceId, group.targetId, edgeId);
      addArc(group.targetId, group.sourceId, edgeId);
    }
    for (const arcs of adjacency.values()) {
      arcs.sort((left, right) =>
        left.targetId.localeCompare(right.targetId) || left.edgeId.localeCompare(right.edgeId),
      );
    }
    const result = { edgeById, adjacency };
    this.semanticIndexCache.set(cacheKey, result);
    return result;
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

    const edgeIds = [...new Set(
      [...edgeRows.values()].flatMap((row) =>
        row.evidence_relation_ids ?? [String(row.relation_id)],
      ),
    )];
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
      .map<GraphEdge>((row) => {
        const properties = parseJson(row.properties_json);
        const memberRelations = Array.isArray(properties.memberRelations)
          ? properties.memberRelations as MemberRelation[]
          : [];
        const evidenceIds = row.evidence_relation_ids ?? [String(row.relation_id)];
        return {
          id: String(row.relation_id),
          source: String(row.source_id),
          target: String(row.target_id),
          kind: String(row.kind),
          certainty: String(row.certainty) as Certainty,
          resolutionStatus: String(row.resolution_status),
          confidence: Number(row.confidence),
          properties,
          evidence: evidenceIds.flatMap((id) => evidence.get(id) ?? []),
          memberRelationCount: Number(properties.memberRelationCount ?? memberRelations.length),
          memberRelations,
        };
      })
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
