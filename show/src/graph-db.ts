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

export class GraphDatabase {
  public constructor(private readonly db: Database) {
    this.validate();
  }

  static async open(bytes: Uint8Array): Promise<GraphDatabase> {
    const SQL = await runtime();
    return new GraphDatabase(new SQL.Database(bytes));
  }

  close(): void {
    this.db.close();
  }

  private validate(): void {
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
    const row = this.rows<{ node_id: string }>(
      "SELECT node_id FROM nodes WHERE kind = 'project_file' ORDER BY path LIMIT 1",
    )[0];
    if (!row) throw new Error("图谱中没有 .uproject 根节点。");
    return String(row.node_id);
  }

  search(query: string, limit = 30): SearchResult[] {
    const value = query.trim();
    if (!value) return [];
    const pattern = `%${escapeLike(value)}%`;
    return this.rows<RawNode>(
      `SELECT node_id, kind, name, path, properties_json
       FROM nodes
       WHERE name LIKE ? ESCAPE '\\' COLLATE NOCASE
          OR path LIKE ? ESCAPE '\\' COLLATE NOCASE
       ORDER BY CASE WHEN name = ? COLLATE NOCASE THEN 0 ELSE 1 END,
                kind, name COLLATE NOCASE
       LIMIT ?`,
      [pattern, pattern, value, limit],
    ).map((row) => ({
      id: String(row.node_id),
      kind: String(row.kind),
      name: String(row.name),
      path: row.path === null ? null : String(row.path),
    }));
  }

  queryGraph(centerId: string, depth: number, maxNodes: number): GraphResult {
    const safeDepth = Math.max(1, Math.min(5, Math.trunc(depth)));
    const safeMaxNodes = Math.max(20, Math.min(600, Math.trunc(maxNodes)));
    const distances = new Map<string, number>([[centerId, 0]]);
    const edgeRows = new Map<string, RawEdge>();
    let frontier = [centerId];
    let truncated = false;

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
