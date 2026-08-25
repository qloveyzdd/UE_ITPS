import assert from "node:assert/strict";
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import initSqlJs from "sql.js";
import ts from "typescript";

const require = createRequire(import.meta.url);
const root = path.resolve(import.meta.dirname, "..");

function loadTypeScript(relativePath) {
  const source = fs.readFileSync(path.join(root, relativePath), "utf8");
  const javascript = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const moduleShim = { exports: {} };
  new Function("require", "module", "exports", javascript)(require, moduleShim, moduleShim.exports);
  return moduleShim.exports;
}

async function sampleGraph() {
  const { GraphDatabase } = loadTypeScript("src/graph-db.ts");
  const SQL = await initSqlJs();
  const database = new SQL.Database();
  database.run(`
    CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE nodes (node_id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, path TEXT, properties_json TEXT NOT NULL);
    CREATE TABLE edges (edge_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, target_id TEXT NOT NULL, kind TEXT NOT NULL, certainty TEXT NOT NULL, resolution_status TEXT NOT NULL, properties_json TEXT NOT NULL);
    CREATE TABLE edge_evidence (evidence_id TEXT PRIMARY KEY, edge_id TEXT NOT NULL, path TEXT, line INTEGER, extractor TEXT NOT NULL, detail_json TEXT NOT NULL);
    INSERT INTO metadata VALUES
      ('schema_version', 'ue-itps.file-graph.v1'),
      ('project_path', 'Sample/Sample.uproject'),
      ('node_count', '3'), ('edge_count', '2'), ('warning_count', '0');
    INSERT INTO nodes VALUES
      ('project', 'project_file', 'Sample.uproject', 'Sample.uproject', '{}'),
      ('rules', 'module_rules_file', 'Sample.Build.cs', 'Source/Sample/Sample.Build.cs', '{}'),
      ('source', 'source_file', 'Worker.cpp', 'Source/Sample/Private/Worker.cpp', '{}');
    INSERT INTO edges VALUES
      ('declares', 'project', 'rules', 'DECLARES_MODULE', 'observed', 'resolved', '{}'),
      ('contains', 'rules', 'source', 'CONTAINS_FILE', 'observed', 'resolved', '{}');
    INSERT INTO edge_evidence VALUES
      ('e1', 'declares', 'Sample.uproject', 3, 'project_descriptor', '{}'),
      ('e2', 'contains', 'Source/Sample/Sample.Build.cs', 1, 'project_cxx_sources', '{}');
  `);
  return new GraphDatabase(database);
}

test("读取并校验文件图谱摘要", async () => {
  const graph = await sampleGraph();
  try {
    assert.equal(graph.rootNodeId(), "project");
    assert.deepEqual(graph.summary(), {
      schemaVersion: "ue-itps.file-graph.v1",
      projectPath: "Sample/Sample.uproject",
      nodeCount: 3,
      edgeCount: 2,
      warningCount: 0,
    });
  } finally {
    graph.close();
  }
});

test("按深度查询节点、关系和证据", async () => {
  const graph = await sampleGraph();
  try {
    const result = graph.queryGraph("project", 2, 100);
    assert.deepEqual(result.nodes.map((node) => node.id).sort(), ["project", "rules", "source"]);
    assert.equal(result.edges.find((edge) => edge.id === "declares").evidence[0].path, "Sample.uproject");
  } finally {
    graph.close();
  }
});

test("搜索支持名称和路径片段", async () => {
  const graph = await sampleGraph();
  try {
    assert.equal(graph.search("Worker.cpp")[0].id, "source");
    assert.equal(graph.search("Source/Sample")[0].id, "rules");
    assert.deepEqual(graph.search("   "), []);
  } finally {
    graph.close();
  }
});
