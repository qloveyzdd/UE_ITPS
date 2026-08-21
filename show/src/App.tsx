import cytoscape, { type Core, type ElementDefinition, type StylesheetStyle } from "cytoscape";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  GraphDatabase,
  type GraphEdge,
  type GraphNode,
  type GraphResult,
  type GraphSummary,
  type SearchResult,
} from "./graph-db";
import { filterGraphByKinds } from "./graph-visibility";

type Selection = { type: "node" | "edge"; id: string } | null;

const NODE_LABELS: Record<string, string> = {
  project_file: "项目文件",
  plugin_file: "插件文件",
  target_file: "Target 文件",
  module_rules_file: "模块规则",
  source_file: "C++ 源文件",
  external_file: "Engine/外部文件",
  external_module: "外部模块",
  external_plugin: "外部插件",
  unresolved_include: "未解析 Include",
};

const EDGE_LABELS: Record<string, string> = {
  DECLARES_TARGET: "声明 Target",
  DECLARES_MODULE: "声明模块",
  ENABLES_PLUGIN: "启用插件",
  DISABLES_PLUGIN: "禁用插件",
  REFERENCES_MODULE: "引用模块",
  DEPENDS_ON_MODULE: "依赖模块",
  DEPENDS_ON_PLUGIN: "依赖插件",
  CONTAINS_FILE: "包含源码",
  MODULE_ENTRY: "模块入口",
  INCLUDES: "Include",
};

function labelForNode(kind: string): string {
  return NODE_LABELS[kind] ?? kind;
}

function labelForEdge(kind: string): string {
  return EDGE_LABELS[kind] ?? kind;
}

function NodeDetails({ node, graph, onCenter }: { node: GraphNode; graph: GraphResult; onCenter: () => void }) {
  const nodeNames = new Map(graph.nodes.map((item) => [item.id, item.name]));
  const relations = graph.edges.filter((edge) => edge.source === node.id || edge.target === node.id);
  return (
    <div className="detail-content">
      <div className="detail-type"><i className={`kind-dot kind-${node.kind}`} />{labelForNode(node.kind)}</div>
      <h2>{node.name}</h2>
      {node.path && <code className="file-path">{node.path}</code>}
      <button type="button" className="secondary-button" onClick={onCenter}>以此为中心</button>
      {relations.length > 0 && (
        <section>
          <h3>直接关系</h3>
          <ul className="relation-list">
            {relations.map((edge) => {
              const outgoing = edge.source === node.id;
              return (
                <li key={edge.id}>
                  <span>{labelForEdge(edge.kind)}</span>
                  <strong>{outgoing ? "→" : "←"} {nodeNames.get(outgoing ? edge.target : edge.source)}</strong>
                </li>
              );
            })}
          </ul>
        </section>
      )}
      {Object.keys(node.properties).length > 0 && (
        <section>
          <h3>属性</h3>
          <dl className="property-list">
            {Object.entries(node.properties).map(([key, value]) => (
              <div key={key}><dt>{key}</dt><dd>{value === null ? "—" : typeof value === "string" ? value : JSON.stringify(value)}</dd></div>
            ))}
          </dl>
        </section>
      )}
    </div>
  );
}

function EdgeDetails({ edge, graph }: { edge: GraphEdge; graph: GraphResult }) {
  const names = new Map(graph.nodes.map((node) => [node.id, node.name]));
  return (
    <div className="detail-content">
      <div className="detail-type"><i className="edge-dot" />关系证据</div>
      <h2>{labelForEdge(edge.kind)}</h2>
      <div className="relation-direction"><strong>{names.get(edge.source)}</strong><span>→</span><strong>{names.get(edge.target)}</strong></div>
      <dl className="facts">
        <dt>可信度</dt><dd>{edge.certainty}</dd>
        <dt>解析状态</dt><dd>{edge.resolutionStatus}</dd>
      </dl>
      {Object.keys(edge.properties).length > 0 && (
        <section><h3>关系属性</h3><pre>{JSON.stringify(edge.properties, null, 2)}</pre></section>
      )}
      <section>
        <h3>来源</h3>
        <ul className="evidence-list">
          {edge.evidence.map((item, index) => (
            <li key={`${item.path}:${item.line}:${index}`}>
              <code>{item.path ?? "未知文件"}{item.line ? `:${item.line}` : ""}</code>
              <span>{item.extractor}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export default function App() {
  const databaseRef = useRef<GraphDatabase | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const [summary, setSummary] = useState<GraphSummary | null>(null);
  const [databaseName, setDatabaseName] = useState("");
  const [rootId, setRootId] = useState("");
  const [graph, setGraph] = useState<GraphResult | null>(null);
  const [selection, setSelection] = useState<Selection>(null);
  const [depth, setDepth] = useState(3);
  const [maxNodes, setMaxNodes] = useState(200);
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<SearchResult[]>([]);
  const [hiddenKinds, setHiddenKinds] = useState<Set<string>>(() => new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadGraph = useCallback((centerId: string, nextDepth = depth, nextMax = maxNodes) => {
    const database = databaseRef.current;
    if (!database) return;
    try {
      const result = database.queryGraph(centerId, nextDepth, nextMax);
      setGraph(result);
      const centerKind = result.nodes.find((node) => node.id === centerId)?.kind;
      if (centerKind) {
        setHiddenKinds((current) => {
          if (!current.has(centerKind)) return current;
          const next = new Set(current);
          next.delete(centerKind);
          return next;
        });
      }
      setSelection({ type: "node", id: centerId });
      setCandidates([]);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取图谱失败。");
    }
  }, [depth, maxNodes]);

  const openDatabase = async (file: File) => {
    setBusy(true);
    setError("");
    try {
      const database = await GraphDatabase.open(new Uint8Array(await file.arrayBuffer()));
      databaseRef.current?.close();
      databaseRef.current = database;
      const nextSummary = database.summary();
      const nextRoot = database.rootNodeId();
      setSummary(nextSummary);
      setDatabaseName(file.name);
      setRootId(nextRoot);
      setHiddenKinds(new Set());
      setQuery("");
      setCandidates([]);
      const result = database.queryGraph(nextRoot, depth, maxNodes);
      setGraph(result);
      setSelection({ type: "node", id: nextRoot });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法打开数据库。");
    } finally {
      setBusy(false);
    }
  };

  const search = (event: React.FormEvent) => {
    event.preventDefault();
    const database = databaseRef.current;
    if (!database || !query.trim()) return;
    setCandidates(database.search(query));
  };

  const displayGraph = useMemo(
    () => graph ? filterGraphByKinds(graph, hiddenKinds) : null,
    [graph, hiddenKinds],
  );

  const toggleKind = (kind: string) => {
    const willHide = !hiddenKinds.has(kind);
    const next = new Set(hiddenKinds);
    if (willHide) next.add(kind); else next.delete(kind);
    setHiddenKinds(next);
    if (!willHide || !selection || !graph) return;
    if (selection.type === "node") {
      const node = graph.nodes.find((item) => item.id === selection.id);
      if (node?.kind === kind) setSelection(null);
      return;
    }
    const edge = graph.edges.find((item) => item.id === selection.id);
    if (!edge) return;
    const sourceKind = graph.nodes.find((item) => item.id === edge.source)?.kind;
    const targetKind = graph.nodes.find((item) => item.id === edge.target)?.kind;
    if (sourceKind === kind || targetKind === kind) setSelection(null);
  };

  useEffect(() => {
    if (!canvasRef.current || !displayGraph || displayGraph.nodes.length === 0) return;
    const layoutRoot = displayGraph.nodes.some((node) => node.id === displayGraph.centerId)
      ? displayGraph.centerId
      : displayGraph.nodes[0].id;
    const elements: ElementDefinition[] = [
      ...displayGraph.nodes.map((node) => ({
        data: { id: node.id, label: node.name, kind: node.kind, center: node.id === displayGraph.centerId ? "yes" : "no" },
      })),
      ...displayGraph.edges.map((edge) => ({
        data: { id: edge.id, source: edge.source, target: edge.target, label: labelForEdge(edge.kind), kind: edge.kind, status: edge.resolutionStatus },
      })),
    ];
    const styles: StylesheetStyle[] = [
      { selector: "node", style: { "background-color": "#64748b", label: "data(label)", color: "#dce8f7", "font-family": "Segoe UI, Microsoft YaHei, sans-serif", "font-size": "10px", "text-wrap": "ellipsis", "text-max-width": "130px", "text-valign": "bottom", "text-margin-y": 8, width: 34, height: 34, "border-width": 1, "border-color": "#94a3b8" } },
      { selector: 'node[kind = "project_file"]', style: { "background-color": "#4f7cff", shape: "round-rectangle", width: 54, height: 42 } },
      { selector: 'node[kind = "plugin_file"]', style: { "background-color": "#8b5cf6", shape: "round-rectangle" } },
      { selector: 'node[kind = "target_file"]', style: { "background-color": "#06b6d4", shape: "diamond" } },
      { selector: 'node[kind = "module_rules_file"]', style: { "background-color": "#f59e0b", shape: "round-rectangle", width: 42, height: 34 } },
      { selector: 'node[kind = "source_file"]', style: { "background-color": "#22c55e", shape: "round-tag" } },
      { selector: 'node[kind ^= "external"], node[kind = "unresolved_include"]', style: { "background-color": "#475569", "border-style": "dashed" } },
      { selector: 'node[center = "yes"]', style: { "border-color": "#f8fafc", "border-width": 4 } },
      { selector: "node:selected", style: { "border-color": "#facc15", "border-width": 4 } },
      { selector: "edge", style: { width: 1.3, "line-color": "#526174", "target-arrow-color": "#526174", "target-arrow-shape": "triangle", "curve-style": "bezier" } },
      { selector: 'edge[status != "resolved"]', style: { "line-style": "dashed", opacity: 0.65 } },
      { selector: "edge:selected", style: { width: 3, "line-color": "#facc15", "target-arrow-color": "#facc15", label: "data(label)", color: "#f8fafc", "font-size": "10px", "text-background-color": "#101722", "text-background-opacity": 0.92, "text-background-padding": "4px", "text-rotation": "autorotate" } },
    ];
    const cy = cytoscape({
      container: canvasRef.current,
      elements,
      style: styles,
      minZoom: 0.08,
      maxZoom: 3,
      layout: { name: "breadthfirst", directed: true, roots: [layoutRoot], padding: 54, spacingFactor: 1.12 },
    });
    cy.on("tap", "node", (event) => setSelection({ type: "node", id: event.target.id() }));
    cy.on("tap", "edge", (event) => setSelection({ type: "edge", id: event.target.id() }));
    cy.on("dbltap", "node", (event) => loadGraph(event.target.id()));
    cyRef.current = cy;
    return () => {
      cy.destroy();
      if (cyRef.current === cy) cyRef.current = null;
    };
  }, [displayGraph, loadGraph]);

  useEffect(() => () => databaseRef.current?.close(), []);

  const selectedNode = selection?.type === "node" ? graph?.nodes.find((node) => node.id === selection.id) ?? null : null;
  const selectedEdge = selection?.type === "edge" ? graph?.edges.find((edge) => edge.id === selection.id) ?? null : null;
  const kindCounts = useMemo(() => {
    if (!graph) return [];
    const counts = new Map<string, number>();
    graph.nodes.forEach((node) => counts.set(node.kind, (counts.get(node.kind) ?? 0) + 1));
    return [...counts.entries()].sort((left, right) => left[0].localeCompare(right[0]));
  }, [graph]);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">KG</span><div><strong>UE 文件知识图谱</strong><span>第一阶段 · 静态文件关系</span></div></div>
        <label className="file-button">
          <input type="file" accept=".sqlite3,.sqlite,.db,application/vnd.sqlite3" onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void openDatabase(file);
            event.currentTarget.value = "";
          }} />
          {summary ? "更换图谱" : "打开图谱"}
        </label>
      </header>

      <section className="toolbar">
        <form className="search" onSubmit={search}>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={summary ? "搜索文件、模块或插件…" : "请先打开 SQLite 图谱"} disabled={!summary} />
          <button type="submit" disabled={!summary || !query.trim()}>搜索</button>
          {candidates.length > 0 && (
            <div className="search-results">
              {candidates.map((candidate) => (
                <button type="button" key={candidate.id} onClick={() => loadGraph(candidate.id)}>
                  <i className={`kind-dot kind-${candidate.kind}`} />
                  <span><strong>{candidate.name}</strong><small>{candidate.path ?? labelForNode(candidate.kind)}</small></span>
                </button>
              ))}
            </div>
          )}
        </form>
        <label>展开深度<select value={depth} onChange={(event) => setDepth(Number(event.target.value))} disabled={!summary}>{[1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value} 层</option>)}</select></label>
        <label>节点上限<select value={maxNodes} onChange={(event) => setMaxNodes(Number(event.target.value))} disabled={!summary}>{[100, 200, 400, 600].map((value) => <option value={value} key={value}>{value}</option>)}</select></label>
        <button type="button" disabled={!rootId} onClick={() => loadGraph(rootId)}>返回项目根</button>
        <button type="button" disabled={!graph} onClick={() => graph && loadGraph(graph.centerId)}>应用范围</button>
      </section>

      {error && <div className="error" role="alert">{error}</div>}

      <div className="workspace">
        <aside className="overview">
          {summary ? (
            <>
              <div className="database-name"><span className="status-dot" /><div><strong>{databaseName}</strong><small>{summary.projectPath}</small></div></div>
              <div className="counts"><div><strong>{summary.nodeCount}</strong><span>节点</span></div><div><strong>{summary.edgeCount}</strong><span>关系</span></div><div><strong>{summary.warningCount}</strong><span>警告</span></div></div>
              <section>
                <h3>节点分类显示</h3>
                <ul className="kind-list">
                  {kindCounts.map(([kind, count]) => (
                    <li key={kind} className={hiddenKinds.has(kind) ? "is-hidden" : ""}>
                      <label className="kind-toggle">
                        <input
                          type="checkbox"
                          checked={!hiddenKinds.has(kind)}
                          onChange={() => toggleKind(kind)}
                        />
                        <i className={`kind-dot kind-${kind}`} aria-hidden="true" />
                        <span>{labelForNode(kind)}</span>
                        <strong>{count}</strong>
                      </label>
                    </li>
                  ))}
                </ul>
              </section>
              <p className="hint">双击节点可重新聚焦；虚线表示外部或未完全解析的关系。</p>
            </>
          ) : (
            <div className="empty-overview"><strong>尚未加载图谱</strong><p>选择由第一阶段构建器生成的 SQLite 文件。</p></div>
          )}
        </aside>

        <section className="graph-stage" aria-label="文件知识图谱">
          {busy && <div className="loading">正在读取图谱…</div>}
          {!graph && !busy && <div className="empty-stage"><div className="empty-symbol"><i /><i /><i /><i /></div><h1>从项目文件开始查看</h1><p>图谱将在本地浏览器内存中打开，不会上传或修改。</p></div>}
          {graph && displayGraph && displayGraph.nodes.length === 0 && <div className="empty-stage"><h1>所有节点分类均已隐藏</h1><p>在左侧重新勾选至少一个分类。</p></div>}
          {graph && displayGraph && displayGraph.nodes.length > 0 && <><div ref={canvasRef} className="graph-canvas" /><div className="graph-actions"><button type="button" onClick={() => cyRef.current?.fit(undefined, 48)}>适应画布</button><button type="button" onClick={() => { const layoutRoot = displayGraph.nodes.some((node) => node.id === displayGraph.centerId) ? displayGraph.centerId : displayGraph.nodes[0].id; cyRef.current?.layout({ name: "breadthfirst", directed: true, roots: [layoutRoot], padding: 54 }).run(); }}>重新布局</button></div><div className="graph-status">{displayGraph.nodes.length}/{graph.nodes.length} 个节点 · {displayGraph.edges.length}/{graph.edges.length} 条关系{graph.truncated && <span>已达到节点上限</span>}</div></>}
        </section>

        <aside className="details">
          {selectedNode && graph && <NodeDetails node={selectedNode} graph={graph} onCenter={() => loadGraph(selectedNode.id)} />}
          {selectedEdge && graph && <EdgeDetails edge={selectedEdge} graph={graph} />}
          {!selectedNode && !selectedEdge && <div className="empty-details"><strong>详细信息</strong><p>点击节点或关系查看路径、上下游和证据。</p></div>}
        </aside>
      </div>
    </main>
  );
}
