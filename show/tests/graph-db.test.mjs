import assert from "node:assert/strict";
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import initSqlJs from "sql.js";
import ts from "typescript";

const require = createRequire(import.meta.url);

async function createGraphDatabase() {
  const root = path.resolve(import.meta.dirname, "..");
  const source = fs.readFileSync(path.join(root, "app", "lib", "graph-db.ts"), "utf8");
  const javascript = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  const moduleShim = { exports: {} };
  new Function("require", "module", "exports", javascript)(require, moduleShim, moduleShim.exports);

  const SQL = await initSqlJs();
  const db = new SQL.Database();
  db.run(`
    CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE snapshot (
      project_key TEXT NOT NULL,
      created_at TEXT NOT NULL,
      node_count INTEGER NOT NULL,
      relation_count INTEGER NOT NULL,
      warning_count INTEGER NOT NULL
    );
    CREATE TABLE nodes (
      node_id TEXT PRIMARY KEY,
      kind TEXT NOT NULL,
      name TEXT NOT NULL,
      qualified_name TEXT,
      namespace TEXT,
      owner TEXT,
      signature TEXT,
      linkage TEXT,
      properties_json TEXT NOT NULL
    );
    CREATE TABLE occurrences (
      node_id TEXT NOT NULL,
      role TEXT NOT NULL,
      root TEXT NOT NULL,
      path TEXT NOT NULL,
      line INTEGER NOT NULL,
      end_line INTEGER,
      probe_schema TEXT NOT NULL
    );
    CREATE TABLE relations (
      relation_id TEXT PRIMARY KEY,
      source_id TEXT NOT NULL,
      target_id TEXT NOT NULL,
      kind TEXT NOT NULL,
      certainty TEXT NOT NULL,
      resolution_status TEXT NOT NULL,
      confidence REAL NOT NULL,
      properties_json TEXT NOT NULL
    );
    CREATE TABLE relation_evidence (
      relation_id TEXT NOT NULL,
      root TEXT,
      path TEXT,
      line INTEGER,
      end_line INTEGER,
      probe_schema TEXT NOT NULL,
      detail_json TEXT NOT NULL
    );
    INSERT INTO metadata VALUES ('schema_version', '1');
    INSERT INTO snapshot VALUES ('SampleGame|SampleGame.uproject', '2026-08-04T00:00:00Z', 358, 357, 0);
    INSERT INTO nodes VALUES
      ('a', 'class', 'A', 'A', NULL, NULL, NULL, NULL, '{}'),
      ('b', 'class', 'B', 'B', NULL, NULL, NULL, NULL, '{}'),
      ('c', 'class', 'C', 'C', NULL, NULL, NULL, NULL, '{}'),
      ('d', 'class', 'D', 'D', NULL, NULL, NULL, NULL, '{}'),
      ('x', 'class', 'X', 'X', NULL, NULL, NULL, NULL, '{}'),
      ('y', 'class', 'Y', 'Y', NULL, NULL, NULL, NULL, '{}'),
      ('z', 'class', 'Z', 'Z', NULL, NULL, NULL, NULL, '{}');
    INSERT INTO relations VALUES
      ('ab', 'a', 'b', 'CALLS', 'observed', 'resolved', 1, '{}'),
      ('bd', 'b', 'd', 'USES_TYPE', 'resolved', 'resolved', 0.9, '{}'),
      ('ac', 'a', 'c', 'CALLS', 'observed', 'resolved', 1, '{}'),
      ('cd', 'c', 'd', 'USES_TYPE', 'resolved', 'resolved', 0.9, '{}'),
      ('bx', 'b', 'x', 'CALLS', 'observed', 'resolved', 1, '{}'),
      ('xy', 'x', 'y', 'CALLS', 'observed', 'resolved', 1, '{}'),
      ('yb', 'y', 'b', 'CALLS', 'observed', 'resolved', 1, '{}');
    INSERT INTO nodes VALUES
      ('e', 'class', 'E', 'E', NULL, NULL, NULL, NULL, '{}'),
      ('f', 'class', 'F', 'F', NULL, NULL, NULL, NULL, '{}'),
      ('em', 'member_function', 'Run', 'E::Run', NULL, 'E', NULL, NULL, '{}'),
      ('fm', 'member_function', 'Handle', 'F::Handle', NULL, 'F', NULL, NULL, '{}');
    INSERT INTO relations VALUES
      ('e-em', 'e', 'em', 'CONTAINS', 'resolved', 'resolved', 1, '{}'),
      ('f-fm', 'f', 'fm', 'CONTAINS', 'resolved', 'resolved', 1, '{}'),
      ('em-fm', 'em', 'fm', 'CALLS', 'inferred', 'resolved', 0.85, '{}'),
      ('em-f', 'em', 'f', 'USES_TYPE', 'resolved', 'resolved', 0.9, '{}');
    INSERT INTO relation_evidence VALUES
      ('em-fm', 'project', 'Source/E.cpp', 42, 42, 'relation-semantics.v1', '{}');
  `);

  const insertNode = db.prepare("INSERT INTO nodes VALUES (?, 'class', ?, ?, NULL, NULL, NULL, NULL, '{}')");
  const insertRelation = db.prepare("INSERT INTO relations VALUES (?, ?, ?, 'CALLS', 'observed', 'resolved', 1, '{}')");
  try {
    for (let index = 0; index <= 350; index += 1) {
      const id = `p${index}`;
      insertNode.run([id, id.toUpperCase(), id.toUpperCase()]);
      if (index > 0) insertRelation.run([`p${index - 1}-p${index}`, `p${index - 1}`, id]);
    }
  } finally {
    insertNode.free();
    insertRelation.free();
  }

  const GraphDatabase = moduleShim.exports.GraphDatabase;
  return new GraphDatabase(db);
}

test("数据库摘要读取信息池快照元数据", async () => {
  const graphDb = await createGraphDatabase();
  try {
    assert.deepEqual(graphDb.summary(), {
      schemaVersion: "1",
      projectKey: "SampleGame|SampleGame.uproject",
      createdAt: "2026-08-04T00:00:00Z",
      nodeCount: 358,
      relationCount: 357,
      warningCount: 0,
    });
  } finally {
    graphDb.close();
  }
});

test("多节点查询只保留确定性的最短语义路径", async () => {
  const graphDb = await createGraphDatabase();
  try {
    const connected = graphDb.queryRelevantGraph(["a", "d", "z"]);
    assert.equal(connected.connectionCount, 1);
    assert.equal(connected.requestedConnectionCount, 3);
    assert.deepEqual(connected.nodes.map((node) => node.id).sort(), ["a", "b", "d", "z"]);
    assert.deepEqual(connected.edges.map((edge) => edge.id).sort(), ["ab", "bd"]);
    assert.equal(connected.truncated, false);
  } finally {
    graphDb.close();
  }
});

test("类节点关系聚合成员调用并保留成员明细", async () => {
  const graphDb = await createGraphDatabase();
  try {
    const result = graphDb.queryRelevantGraph(["e", "f"]);
    assert.deepEqual(result.nodes.map((node) => node.id).sort(), ["e", "f"]);
    assert.equal(result.edges.length, 1);
    assert.equal(result.edges[0].kind, "CALLS");
    assert.equal(result.edges[0].memberRelationCount, 1);
    assert.deepEqual(result.edges[0].memberRelations, [{
      relationId: "em-fm",
      sourceId: "em",
      sourceName: "E::Run",
      targetId: "fm",
      targetName: "F::Handle",
    }]);

    const expansion = graphDb.queryMemberRelations(
      result.edges[0].memberRelations.map((relation) => relation.relationId),
    );
    assert.deepEqual(expansion.nodes.map((node) => node.id).sort(), ["em", "fm"]);
    assert.equal(expansion.edges.length, 1);
    assert.equal(expansion.edges[0].id, "em-fm");
    assert.equal(expansion.edges[0].source, "em");
    assert.equal(expansion.edges[0].target, "fm");
    assert.equal(expansion.edges[0].evidence[0].path, "Source/E.cpp");
    assert.equal(expansion.edges[0].evidence[0].line, 42);
  } finally {
    graphDb.close();
  }
});

test("多节点查询没有关注节点、深度或节点数量上限", async () => {
  const graphDb = await createGraphDatabase();
  try {
    const longPath = graphDb.queryRelevantGraph(["p0", "p350"]);
    assert.equal(longPath.connectionCount, 1);
    assert.equal(longPath.nodes.length, 351);
    assert.equal(longPath.edges.length, 350);

    const focusIds = Array.from({ length: 12 }, (_, index) => `p${index}`);
    const manyFocusNodes = graphDb.queryRelevantGraph(focusIds);
    assert.equal(manyFocusNodes.focusIds.length, 12);
    assert.equal(manyFocusNodes.connectionCount, 66);
  } finally {
    graphDb.close();
  }
});
