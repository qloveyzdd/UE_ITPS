import type { Database, SqlJsStatic } from "sql.js";

export interface GraphSummary {
  schemaVersion: string;
  projectPath: string;
  nodeCount: number;
  edgeCount: number;
  warningCount: number;
}

export interface Evidence {
  path: string | null;
  line: number | null;
  extractor: string;
  detail: Record<string, unknown>;
}

export interface GraphNode {
  id: string;
  kind: string;
  name: string;
  path: string | null;
  properties: Record<string, unknown>;
  distance: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: string;
  certainty: string;
  resolutionStatus: string;
  properties: Record<string, unknown>;
  evidence: Evidence[];
}

export interface GraphResult {
  centerId: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
}

export interface SearchResult {
  id: string;
  kind: string;
  name: string;
  path: string | null;
}

interface RawNode {
  node_id: string;
  kind: string;
  name: string;
  path: string | null;
  properties_json: string;
}

interface RawEdge {
  edge_id: string;
  source_id: string;
  target_id: string;
  kind: string;
  certainty: string;
  resolution_status: string;
  properties_json: string;
}

interface LogicalNode {
  node_id: string;
  kind: string;
  name: string;
  canonical_key?: string;
  properties?: Record<string, unknown>;
}

interface LogicalRelation {
  relation_id: string;
  source_id: string;
  kind: string;
  target_id: string;
  certainty?: string;
  properties?: Record<string, unknown>;
}

interface LogicalEvidence {
  evidence_id: string;
  relation_id: string;
  producer?: string;
  [key: string]: unknown;
}

interface LogicalDocument {
  schema_version: string;
  graph: {
    project?: string;
    nodes: LogicalNode[];
    relations: LogicalRelation[];
    evidence: LogicalEvidence[];
  };
  validation?: { problem_count?: number };
}

const REQUIRED_TABLES = ["metadata", "nodes", "edges", "edge_evidence"];
let runtimePromise: Promise<SqlJsStatic> | null = null;

function runtime(): Promise<SqlJsStatic> {
  if (runtimePromise) return runtimePromise;
  runtimePromise = new Promise((resolve, reject) => {
    const initialize = () => {
      const initializer = (window as unknown as { initSqlJs?: () => Promise<SqlJsStatic> }).initSqlJs;
      if (!initializer) {
        reject(new Error("本地 SQLite 运行库没有正确加载。"));
        return;
      }
      initializer().then(resolve, reject);
    };
    if ((window as unknown as { initSqlJs?: () => Promise<SqlJsStatic> }).initSqlJs) {
      initialize();
      return;
    }
    const script = document.createElement("script");
    script.src = "/vendor/sql-asm.js";
    script.async = true;
    script.addEventListener("load", initialize, { once: true });
    script.addEventListener("error", () => reject(new Error("无法加载本地 SQLite 运行库。")), { once: true });
    document.head.appendChild(script);
  });
  return runtimePromise;
}

function parseJson(value: unknown): Record<string, unknown> {
  if (typeof value !== "string" || value.length === 0) return {};
  try {
    const parsed: unknown = JSON.parse(value);
    return parsed !== null && typeof parsed === "object" ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

function placeholders(count: number): string {
  return Array.from({ length: count }, () => "?").join(",");
}

function chunks<T>(items: T[], size = 350): T[][] {
  const result: T[][] = [];
  for (let index = 0; index < items.length; index += size) result.push(items.slice(index, index + size));
  return result;
}

function escapeLike(value: string): string {
  return value.replace(/[\\%_]/g, "\\$&");
}

type SearchableNode = Pick<LogicalNode, "node_id" | "kind" | "name" | "canonical_key" | "properties"> & {
  path?: string | null;
};

function searchValues(node: SearchableNode): string[] {
  const properties = node.properties ?? {};
  return [
    node.name,
    node.canonical_key ?? "",
    node.path ?? "",
    typeof properties.path === "string" ? properties.path : "",
    typeof properties.qualified_name === "string" ? properties.qualified_name : "",
    Array.isArray(properties.files) ? properties.files.join(" ") : "",
  ];
}

function compareSearchNodes(left: SearchableNode, right: SearchableNode, foldedQuery: string): number {
  return (left.name.toLocaleLowerCase() === foldedQuery ? 0 : 1)
    - (right.name.toLocaleLowerCase() === foldedQuery ? 0 : 1)
    || left.kind.localeCompare(right.kind)
    || left.name.localeCompare(right.name)
    || left.node_id.localeCompare(right.node_id);
}

export class GraphDatabase {
  public constructor(
    private readonly db: Database | null,
    private readonly logical: LogicalDocument | null = null,
  ) {
    this.validate();
  }

  static async open(bytes: Uint8Array, filename = ""): Promise<GraphDatabase> {
    if (filename.toLowerCase().endsWith(".json")) {
      let parsed: unknown;
      try {
        parsed = JSON.parse(new TextDecoder().decode(bytes));
      } catch {
        throw new Error("JSON 图谱无法解析。请确认文件完整且使用 UTF-8 编码。");
      }
      return GraphDatabase.fromLogicalDocument(parsed);
    }
    const SQL = await runtime();
    return new GraphDatabase(new SQL.Database(bytes));
  }

  static fromLogicalDocument(value: unknown): GraphDatabase {
    if (value === null || typeof value !== "object") throw new Error("不是有效的 JSON 图谱对象。");
    const document = value as Partial<LogicalDocument>;
    if (document.schema_version !== "ue_build_knowledge_graph" || !document.graph) {
      throw new Error("不支持的 JSON 图谱版本：需要 ue_build_knowledge_graph。");
    }
    const graph = document.graph as LogicalDocument["graph"];
    if (!Array.isArray(graph.nodes) || !Array.isArray(graph.relations) || !Array.isArray(graph.evidence)) {
      throw new Error("JSON 图谱缺少 nodes、relations 或 evidence。");
    }
    return new GraphDatabase(null, {
      schema_version: document.schema_version,
      graph,
      validation: document.validation,
    });
  }

  close(): void {
    this.db?.close();
  }

  private validate(): void {
    if (this.logical) {
      const nodeIds = new Set(this.logical.graph.nodes.map((node) => node.node_id));
      if (this.logical.graph.nodes.some((node) => !node.node_id || !node.name || !node.kind)) {
        throw new Error("JSON 图谱包含不完整的节点记录。");
      }
      if (this.logical.graph.relations.some((relation) => !nodeIds.has(relation.source_id) || !nodeIds.has(relation.target_id))) {
        throw new Error("JSON 图谱包含指向不存在节点的关系。");
      }
      return;
    }
    const tableNames = new Set(
      this.rows<{ name: string }>("SELECT name FROM sqlite_master WHERE type = 'table'")
        .map((row) => String(row.name)),
    );
    const missing = REQUIRED_TABLES.filter((table) => !tableNames.has(table));
    if (missing.length > 0) throw new Error(`不是第一阶段文件图谱，缺少表：${missing.join("、")}`);
    const schema = this.metadata().schema_version;
    if (schema !== "ue-itps.file-graph.v1") throw new Error(`不支持的文件图谱版本：${schema ?? "未知"}`);
  }

  private metadata(): Record<string, string> {
    return Object.fromEntries(
      this.rows<{ key: string; value: string }>("SELECT key, value FROM metadata")
        .map((row) => [String(row.key), String(row.value)]),
    );
  }

  summary(): GraphSummary {
    if (this.logical) {
      return {
        schemaVersion: this.logical.schema_version,
        projectPath: this.logical.graph.project ?? "",
        nodeCount: this.logical.graph.nodes.length,
        edgeCount: this.logical.graph.relations.length,
        warningCount: Number(this.logical.validation?.problem_count ?? 0),
      };
    }
    const values = this.metadata();
    return {
      schemaVersion: values.schema_version,
      projectPath: values.project_path,
      nodeCount: Number(values.node_count),
      edgeCount: Number(values.edge_count),
      warningCount: Number(values.warning_count),
    };
  }

  rootNodeId(): string {
    if (this.logical) {
      const preferred = ["project_file", "project", "uproject"];
      const node = [...this.logical.graph.nodes]
        .sort((left, right) => {
          const leftRank = preferred.indexOf(left.kind);
          const rightRank = preferred.indexOf(right.kind);
          return (leftRank < 0 ? preferred.length : leftRank) - (rightRank < 0 ? preferred.length : rightRank)
            || left.name.localeCompare(right.name)
            || left.node_id.localeCompare(right.node_id);
        })[0];
      if (!node) throw new Error("JSON 图谱中没有节点。");
      return node.node_id;
    }
    const row = this.rows<{ node_id: string }>(
      "SELECT node_id FROM nodes WHERE kind = 'project_file' ORDER BY path LIMIT 1",
    )[0];
    if (!row) throw new Error("图谱中没有 .uproject 根节点。");
    return String(row.node_id);
  }

  search(query: string, limit = 30): SearchResult[] {
    const value = query.trim();
    if (!value) return [];
    if (this.logical) {
      const folded = value.toLocaleLowerCase();
      return this.logical.graph.nodes
        .filter((node) => searchValues(node).some((candidate) => candidate.toLocaleLowerCase().includes(folded)))
        .sort((left, right) => compareSearchNodes(left, right, folded))
        .slice(0, limit)
        .map((node) => ({ id: node.node_id, kind: node.kind, name: node.name, path: this.nodePath(node) }));
    }
    const pattern = `%${escapeLike(value)}%`;
    const rows = this.rows<RawNode>(
      `SELECT node_id, kind, name, path, properties_json
       FROM nodes
       WHERE name LIKE ? ESCAPE '\\' COLLATE NOCASE
          OR path LIKE ? ESCAPE '\\' COLLATE NOCASE
          OR properties_json LIKE ? ESCAPE '\\' COLLATE NOCASE`,
      [pattern, pattern, pattern],
    ).map((row) => ({
      node_id: String(row.node_id),
      kind: String(row.kind),
      name: String(row.name),
      path: row.path === null ? null : String(row.path),
      properties: parseJson(row.properties_json),
    }));
    const folded = value.toLocaleLowerCase();
    return rows
      .filter((node) => searchValues(node).some((candidate) => candidate.toLocaleLowerCase().includes(folded)))
      .sort((left, right) => compareSearchNodes(left, right, folded))
      .slice(0, limit)
      .map((node) => ({ id: node.node_id, kind: node.kind, name: node.name, path: node.path ?? null }));
  }

  queryGraph(centerId: string, depth: number, maxNodes: number): GraphResult {
    const safeDepth = Math.max(1, Math.min(5, Math.trunc(depth)));
    const safeMaxNodes = Math.max(20, Math.min(600, Math.trunc(maxNodes)));
    const distances = new Map<string, number>([[centerId, 0]]);
    const edgeRows = new Map<string, RawEdge>();
    let frontier = [centerId];
    let truncated = false;

    if (this.logical) {
      const relations = this.logical.graph.relations;
      for (let level = 0; level < safeDepth && frontier.length > 0; level += 1) {
        const next: string[] = [];
        const frontierSet = new Set(frontier);
        for (const relation of relations) {
          const touches = frontierSet.has(relation.source_id) || frontierSet.has(relation.target_id);
          if (!touches) continue;
          const candidate = distances.has(relation.source_id) ? relation.target_id : relation.source_id;
          if (!distances.has(candidate)) {
            if (distances.size >= safeMaxNodes) {
              truncated = true;
              continue;
            }
            distances.set(candidate, level + 1);
            next.push(candidate);
          }
        }
        frontier = [...new Set(next)];
      }
      const nodeById = new Map(this.logical.graph.nodes.map((node) => [node.node_id, node]));
      const nodeRows = [...distances.keys()]
        .map((id) => nodeById.get(id))
        .filter((node): node is LogicalNode => Boolean(node));
      const evidenceByRelation = new Map<string, Evidence[]>();
      for (const item of this.logical.graph.evidence) {
        const values = evidenceByRelation.get(item.relation_id) ?? [];
        const path = typeof item.path === "string" ? item.path : null;
        const line = typeof item.line === "number" ? item.line : null;
        const detail = Object.fromEntries(Object.entries(item).filter(([key]) => !["evidence_id", "relation_id", "producer", "path", "line"].includes(key)));
        values.push({ path, line, extractor: String(item.producer ?? "knowledge_graph"), detail });
        evidenceByRelation.set(item.relation_id, values);
      }
      const visibleIds = new Set(distances.keys());
      const edges = relations
        .filter((relation) => visibleIds.has(relation.source_id) && visibleIds.has(relation.target_id))
        .map<GraphEdge>((relation) => ({
          id: relation.relation_id,
          source: relation.source_id,
          target: relation.target_id,
          kind: relation.kind,
          certainty: relation.certainty ?? "confirmed",
          resolutionStatus: relation.certainty === "confirmed" ? "resolved" : relation.certainty ?? "unresolved",
          properties: relation.properties ?? {},
          evidence: evidenceByRelation.get(relation.relation_id) ?? [],
        }));
      const nodes = nodeRows.map<GraphNode>((node) => ({
        id: node.node_id,
        kind: node.kind,
        name: node.name,
        path: this.nodePath(node),
        properties: node.properties ?? {},
        distance: distances.get(node.node_id) ?? 0,
      })).sort((left, right) => left.distance - right.distance || left.name.localeCompare(right.name));
      return { centerId, nodes, edges, truncated };
    }

    for (let level = 0; level < safeDepth && frontier.length > 0; level += 1) {
      const next: string[] = [];
      for (const group of chunks(frontier)) {
        const rows = this.rows<RawEdge>(
          `SELECT edge_id, source_id, target_id, kind, certainty, resolution_status, properties_json
           FROM edges
           WHERE source_id IN (${placeholders(group.length)})
              OR target_id IN (${placeholders(group.length)})
           ORDER BY kind, edge_id`,
          [...group, ...group],
        );
        for (const row of rows) {
          const source = String(row.source_id);
          const target = String(row.target_id);
          const touchesVisited = distances.has(source) || distances.has(target);
          if (!touchesVisited) continue;
          const candidate = distances.has(source) ? target : source;
          if (!distances.has(candidate)) {
            if (distances.size >= safeMaxNodes) {
              truncated = true;
              continue;
            }
            distances.set(candidate, level + 1);
            next.push(candidate);
          }
          if (distances.has(source) && distances.has(target)) edgeRows.set(String(row.edge_id), row);
        }
      }
      frontier = [...new Set(next)];
    }

    const nodeRows: RawNode[] = [];
    const nodeIds = [...distances.keys()];
    for (const group of chunks(nodeIds)) {
      nodeRows.push(...this.rows<RawNode>(
        `SELECT node_id, kind, name, path, properties_json FROM nodes
         WHERE node_id IN (${placeholders(group.length)})`,
        group,
      ));
    }

    const evidenceByEdge = new Map<string, Evidence[]>();
    const edgeIds = [...edgeRows.keys()];
    for (const group of chunks(edgeIds)) {
      const rows = this.rows<{
        edge_id: string;
        path: string | null;
        line: number | null;
        extractor: string;
        detail_json: string;
      }>(
        `SELECT edge_id, path, line, extractor, detail_json FROM edge_evidence
         WHERE edge_id IN (${placeholders(group.length)})
         ORDER BY path COLLATE NOCASE, line`,
        group,
      );
      for (const row of rows) {
        const id = String(row.edge_id);
        const values = evidenceByEdge.get(id) ?? [];
        values.push({
          path: row.path === null ? null : String(row.path),
          line: row.line === null ? null : Number(row.line),
          extractor: String(row.extractor),
          detail: parseJson(row.detail_json),
        });
        evidenceByEdge.set(id, values);
      }
    }

    const nodes = nodeRows.map<GraphNode>((row) => ({
      id: String(row.node_id),
      kind: String(row.kind),
      name: String(row.name),
      path: row.path === null ? null : String(row.path),
      properties: parseJson(row.properties_json),
      distance: distances.get(String(row.node_id)) ?? 0,
    })).sort((left, right) => left.distance - right.distance || left.name.localeCompare(right.name));
    const edges = [...edgeRows.values()].map<GraphEdge>((row) => ({
      id: String(row.edge_id),
      source: String(row.source_id),
      target: String(row.target_id),
      kind: String(row.kind),
      certainty: String(row.certainty),
      resolutionStatus: String(row.resolution_status),
      properties: parseJson(row.properties_json),
      evidence: evidenceByEdge.get(String(row.edge_id)) ?? [],
    }));
    return { centerId, nodes, edges, truncated };
  }

  private rows<T extends object>(sql: string, parameters: unknown[] = []): T[] {
    if (!this.db) throw new Error("当前图谱不是 SQLite 数据库。");
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

  private nodePath(node: LogicalNode): string | null {
    const properties = node.properties ?? {};
    if (typeof properties.path === "string") return properties.path;
    if (Array.isArray(properties.files) && typeof properties.files[0] === "string") return properties.files[0];
    return null;
  }
}
