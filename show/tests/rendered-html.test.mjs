import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import path from "node:path";

test("生产构建包含关系浏览器页面和本地 SQLite 引擎", () => {
  const root = path.resolve(import.meta.dirname, "..");
  const page = fs.readFileSync(path.join(root, "app", "page.tsx"), "utf8");
  const graphDb = fs.readFileSync(path.join(root, "app", "lib", "graph-db.ts"), "utf8");
  const sqliteEngine = path.join(root, "public", "vendor", "sql-asm.js");
  assert.match(page, /GraphExplorer/);
  assert.match(graphDb, /\/vendor\/sql-asm\.js/);
  const explorer = fs.readFileSync(path.join(root, "app", "components", "GraphExplorer.tsx"), "utf8");
  assert.match(explorer, /在图中展开/);
  assert.match(explorer, /queryMemberRelations/);
  assert.match(explorer, /edge\.source === selectedId/);
  assert.match(explorer, /breadthfirst/);
  assert.ok(fs.statSync(sqliteEngine).size > 1_000_000);
});
