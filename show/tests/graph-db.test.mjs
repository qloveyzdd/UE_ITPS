import assert from "node:assert/strict";
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import initSqlJs from "sql.js";
import ts from "typescript";

const require = createRequire(import.meta.url);

async function database() {
  const root = path.resolve(import.meta.dirname, "..");
  const source = fs.readFileSync(path.join(root, "src", "graph-db.ts"), "utf8");
  const javascript = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const moduleShim = { exports: {} };
  new Function("require", "module", "exports", javascript)(require, moduleShim, moduleShim.exports);
  const SQL = await initSqlJs();
  const db = new SQL.Database();
  db.run(`
    CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE nodes (node_id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, path TEXT, properties_json TEXT NOT NULL);
    CREATE TABLE edges (edge_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, target_id TEXT NOT NULL, kind TEXT NOT NULL, certainty TEXT NOT NULL, resolution_status TEXT NOT NULL, properties_json TEXT NOT NULL);
    CREATE TABLE edge_evidence (evidence_id TEXT PRIMARY KEY, edge_id TEXT NOT NULL, path TEXT, line INTEGER, extractor TEXT NOT NULL, detail_json TEXT NOT NULL);
    INSERT INTO metadata VALUES
      ('schema_version', 'ue-itps.file-graph.v1'),
      ('project_path', 'Sample/Sample.uproject'),
      ('node_count', '4'),
      ('edge_count', '3'),
      ('warning_count', '0');
    INSERT INTO nodes VALUES
      ('p', 'project_file', 'Sample.uproject', 'Sample.uproject', '{}'),
      ('b', 'module_rules_file', 'Sample.Build.cs', 'Source/Sample/Sample.Build.cs', '{}'),
      ('c', 'source_file', 'Sample.cpp', 'Source/Sample/Private/Sample.cpp', '{}'),
      ('h', 'source_file', 'Sample.h', 'Source/Sample/Public/Sample.h', '{}');
    INSERT INTO edges VALUES
      ('pb', 'p', 'b', 'DECLARES_MODULE', 'observed', 'resolved', '{}'),
      ('bc', 'b', 'c', 'CONTAINS_FILE', 'observed', 'resolved', '{}'),
      ('ch', 'c', 'h', 'INCLUDES', 'observed', 'resolved', '{"spelling":"Sample.h"}');
    INSERT INTO edge_evidence VALUES
      ('epb', 'pb', 'Sample.uproject', 4, 'project_descriptor', '{}'),
      ('ebc', 'bc', 'Source/Sample/Sample.Build.cs', 1, 'project_cxx_sources', '{}'),
      ('ech', 'ch', 'Source/Sample/Private/Sample.cpp', 1, 'cxx_includes', '{}');
  `);
  return new moduleShim.exports.GraphDatabase(db);
}

function loadTypeScriptModule(relativePath) {
  const root = path.resolve(import.meta.dirname, "..");
  const source = fs.readFileSync(path.join(root, relativePath), "utf8");
  const javascript = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const moduleShim = { exports: {} };
  new Function("require", "module", "exports", javascript)(require, moduleShim, moduleShim.exports);
  return moduleShim.exports;
}

test("读取摘要和项目根节点", async () => {
  const graph = await database();
  try {
    assert.equal(graph.rootNodeId(), "p");
    assert.deepEqual(graph.summary(), {
      schemaVersion: "ue-itps.file-graph.v1",
      projectPath: "Sample/Sample.uproject",
      nodeCount: 4,
      edgeCount: 3,
      warningCount: 0,
    });
  } finally {
    graph.close();
  }
});

test("按深度读取文件关系并保留证据", async () => {
  const graph = await database();
  try {
    const result = graph.queryGraph("p", 3, 100);
    assert.deepEqual(result.nodes.map((node) => node.id).sort(), ["b", "c", "h", "p"]);
    assert.deepEqual(result.edges.map((edge) => edge.kind).sort(), ["CONTAINS_FILE", "DECLARES_MODULE", "INCLUDES"]);
    const include = result.edges.find((edge) => edge.kind === "INCLUDES");
    assert.equal(include.evidence[0].path, "Source/Sample/Private/Sample.cpp");
    assert.equal(include.evidence[0].line, 1);
  } finally {
    graph.close();
  }
});

test("按文件名和路径搜索", async () => {
  const graph = await database();
  try {
    assert.equal(graph.search("Sample.cpp")[0].id, "c");
    assert.equal(graph.search("Public/Sample.h")[0].id, "h");
  } finally {
    graph.close();
  }
});

test("按节点分类隐藏节点和关联边", () => {
  const { filterGraphByKinds } = loadTypeScriptModule("src/graph-visibility.ts");
  const graph = {
    centerId: "p",
    nodes: [
      { id: "p", kind: "project_file" },
      { id: "b", kind: "module_rules_file" },
      { id: "c", kind: "source_file" },
    ],
    edges: [
      { id: "pb", source: "p", target: "b" },
      { id: "bc", source: "b", target: "c" },
    ],
    truncated: false,
  };
  const filtered = filterGraphByKinds(graph, new Set(["module_rules_file"]));
  assert.deepEqual(filtered.nodes.map((node) => node.id), ["p", "c"]);
  assert.deepEqual(filtered.edges, []);
});
