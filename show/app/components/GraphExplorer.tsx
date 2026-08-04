"use client";

import cytoscape, { type Core, type ElementDefinition, type LayoutOptions, type Stylesheet } from "cytoscape";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  GraphDatabase,
  type Certainty,
  type DatabaseSummary,
  type GraphEdge,
  type GraphNode,
  type GraphResult,
  type SearchCandidate,
} from "../lib/graph-db";

type Selection = { type: "node" | "edge"; id: string };
type ExplorerMode = "single" | "multi";

const NODE_KIND_LABELS: Record<string, string> = {
  project: "工程",
  plugin: "插件",
  module: "模块",
  source_file: "源文件",
  external_file: "外部文件",
  class: "类",
  struct: "结构体",
  enum: "枚举",
  member_function: "成员函数",
  free_function: "自由函数",
  member_variable: "成员变量",
  global_variable: "全局变量",
  external_symbol: "外部符号",
};

const RELATION_LABELS: Record<string, string> = {
  REFERENCES: "引用",
  CALLS: "调用",
  INHERITS: "继承",
  CONTAINS: "包含",
  DECLARES: "声明",
  DEFINES: "定义",
  USES_TYPE: "使用类型",
  INCLUDES: "包含文件",
  BELONGS_TO: "属于",
  COMPANION: "配套文件",
  BINDS_CALLBACK: "绑定回调",
  TAKES_ADDRESS: "获取地址",
};

const CERTAINTY_LABELS: Record<Certainty, string> = {
  observed: "代码事实",
  resolved: "已解析",
  inferred: "推断",
};

function nodeKindLabel(kind: string): string {
  return NODE_KIND_LABELS[kind] ?? kind;
}

function relationLabel(kind: string): string {
  return RELATION_LABELS[kind] ?? kind;
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function readableDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN");
}

function summaryText(summary: DatabaseSummary): string {
  return `${formatNumber(summary.nodeCount)} 个节点 · ${formatNumber(summary.relationCount)} 条关系`;
}

function graphLayout(nodeCount: number, animate: boolean): LayoutOptions {
  if (nodeCount > 500) {
    return {
      name: "breadthfirst",
      animate,
      fit: true,
      padding: 42,
      directed: false,
      spacingFactor: 1.15,
    };
  }
  return {
    name: "cose",
    animate,
    animationDuration: animate ? 450 : undefined,
    fit: true,
    padding: 42,
    nodeRepulsion: () => 7000,
    idealEdgeLength: () => 92,
    edgeElasticity: () => 100,
    gravity: 0.32,
    numIter: 800,
  };
}

function PropertyList({ properties }: { properties: Record<string, unknown> }) {
  const entries = Object.entries(properties);
  if (entries.length === 0) return null;
  return (
    <section className="detail-section">
      <h3>属性</h3>
      <dl className="property-list">
        {entries.map(([key, value]) => (
          <div key={key}>
            <dt>{key}</dt>
            <dd>{typeof value === "string" ? value : JSON.stringify(value)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function NodeDetail({ node }: { node: GraphNode }) {
  return (
    <div className="detail-content">
      <div className="detail-heading">
        <span className={`kind-mark kind-${node.kind}`} aria-hidden="true" />
        <div>
          <span className="eyebrow">{nodeKindLabel(node.kind)}</span>
          <h2>{node.qualifiedName}</h2>
        </div>
      </div>
      {node.signature && <code className="signature">{node.signature}</code>}
      <dl className="facts">
        {node.owner && <><dt>所有者</dt><dd>{node.owner}</dd></>}
        {node.namespace && <><dt>命名空间</dt><dd>{node.namespace}</dd></>}
        {node.linkage && <><dt>链接属性</dt><dd>{node.linkage}</dd></>}
        <dt>距中心</dt><dd>{node.distance} 层</dd>
      </dl>
      {node.occurrences.length > 0 && (
        <section className="detail-section">
          <h3>源码位置</h3>
          <ul className="evidence-list">
            {node.occurrences.map((occurrence, index) => (
              <li key={`${occurrence.path}:${occurrence.line}:${index}`}>
                <span>{occurrence.role}</span>
                <code>{occurrence.path}:{occurrence.line}</code>
              </li>
            ))}
          </ul>
        </section>
      )}
      <PropertyList properties={node.properties} />
    </div>
  );
}

function EdgeDetail({ edge, nodes }: { edge: GraphEdge; nodes: GraphNode[] }) {
  const names = new Map(nodes.map((node) => [node.id, node.qualifiedName]));
  return (
    <div className="detail-content">
      <div className="detail-heading">
        <span className="edge-mark" aria-hidden="true" />
        <div>
          <span className="eyebrow">关系</span>
          <h2>{relationLabel(edge.kind)}</h2>
        </div>
      </div>
      <div className="relation-pair">
        <strong>{names.get(edge.source) ?? edge.source}</strong>
        <span>→</span>
        <strong>{names.get(edge.target) ?? edge.target}</strong>
      </div>
      <dl className="facts">
        <dt>可信级别</dt><dd>{CERTAINTY_LABELS[edge.certainty]}</dd>
        <dt>解析状态</dt><dd>{edge.resolutionStatus}</dd>
        <dt>置信度</dt><dd>{Math.round(edge.confidence * 100)}%</dd>
      </dl>
      {edge.evidence.length > 0 && (
        <section className="detail-section">
          <h3>关系证据</h3>
          <ul className="evidence-list">
            {edge.evidence.map((item, index) => (
              <li key={`${item.path}:${item.line}:${index}`}>
                <span>{item.probeSchema}</span>
                <code>{item.path ? `${item.path}${item.line ? `:${item.line}` : ""}` : "解析器生成"}</code>
              </li>
            ))}
          </ul>
        </section>
      )}
      <PropertyList properties={edge.properties} />
    </div>
  );
}

export default function GraphExplorer() {
  const databaseRef = useRef<GraphDatabase | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const [databaseName, setDatabaseName] = useState("");
  const [summary, setSummary] = useState<DatabaseSummary | null>(null);
  const [mode, setMode] = useState<ExplorerMode>("single");
  const [query, setQuery] = useState("");
  const [depth, setDepth] = useState(1);
  const [maxNodes, setMaxNodes] = useState(100);
  const [candidates, setCandidates] = useState<SearchCandidate[]>([]);
  const [focusNodes, setFocusNodes] = useState<SearchCandidate[]>([]);
  const [graph, setGraph] = useState<GraphResult | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [relationKinds, setRelationKinds] = useState<Set<string>>(new Set());
  const [certainties, setCertainties] = useState<Set<Certainty>>(
    new Set(["observed", "resolved", "inferred"]),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [renderProgress, setRenderProgress] = useState<{
    loadedNodes: number;
    totalNodes: number;
    loadedEdges: number;
    totalEdges: number;
  } | null>(null);

  const loadGraph = useCallback(async (
    nextFocusNodes: SearchCandidate[],
    selectedId = nextFocusNodes[0]?.id,
    queryMode = mode,
  ) => {
    const database = databaseRef.current;
    if (!database || nextFocusNodes.length === 0) return;
    setBusy(true);
    setError("");
    setCandidates([]);
    await new Promise<void>((resolve) => window.setTimeout(resolve, 0));
    try {
      const result = queryMode === "single"
        ? database.queryGraph(nextFocusNodes[0].id, depth, maxNodes)
        : database.queryRelevantGraph(nextFocusNodes.map((node) => node.id));
      setMode(queryMode);
      setFocusNodes(nextFocusNodes);
      setGraph(result);
      setRelationKinds(new Set(result.edges.map((edge) => edge.kind)));
      setSelection({ type: "node", id: selectedId ?? result.centerId });
      setQuery("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "关系图查询失败。");
    } finally {
      setBusy(false);
    }
  }, [depth, maxNodes, mode]);

  const addFocusNode = useCallback(async (candidate: SearchCandidate) => {
    const alreadySelected = focusNodes.some((node) => node.id === candidate.id);
    const nextFocusNodes = mode === "single"
      ? [candidate]
      : alreadySelected ? focusNodes : [...focusNodes, candidate];
    await loadGraph(nextFocusNodes, candidate.id, mode);
  }, [focusNodes, loadGraph, mode]);

  const graphNodeCandidate = useCallback((node: GraphNode): SearchCandidate => ({
    id: node.id,
    kind: node.kind,
    name: node.name,
    qualifiedName: node.qualifiedName,
    signature: node.signature,
  }), []);

  const openDatabase = async (file: File) => {
    setBusy(true);
    setError("");
    setCandidates([]);
    setFocusNodes([]);
    setGraph(null);
    setSelection(null);
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      const nextDatabase = await GraphDatabase.open(bytes);
      const nextSummary = nextDatabase.summary();
      databaseRef.current?.close();
      databaseRef.current = nextDatabase;
      setDatabaseName(file.name);
      setSummary(nextSummary);
      setMode("single");
      setQuery("");
    } catch (caught) {
      setSummary(null);
      setDatabaseName("");
      setError(caught instanceof Error ? caught.message : "数据库打开失败。");
    } finally {
      setBusy(false);
    }
  };

  const submitSearch = async (event: React.FormEvent) => {
    event.preventDefault();
    const database = databaseRef.current;
    const value = query.trim();
    if (!database || !value) return;
    setBusy(true);
    setError("");
    await new Promise<void>((resolve) => window.setTimeout(resolve, 0));
    try {
      const results = database.search(value);
      if (results.length === 0) {
        setCandidates([]);
        setError(`没有找到“${value}”。`);
        return;
      }
      const normalized = value.toLocaleLowerCase();
      const exact = results.filter(
        (item) => item.name.toLocaleLowerCase() === normalized
          || item.qualifiedName.toLocaleLowerCase() === normalized,
      );
      if (exact.length === 1) {
        await addFocusNode(exact[0]);
      } else {
        setCandidates(exact.length > 1 ? exact : results);
      }
    } finally {
      setBusy(false);
    }
  };

  const filteredEdges = useMemo(() => {
    if (!graph) return [];
    return graph.edges.filter(
      (edge) => relationKinds.has(edge.kind) && certainties.has(edge.certainty),
    );
  }, [graph, relationKinds, certainties]);
  const visibleNodeCount = useMemo(() => {
    if (!graph) return 0;
    const ids = new Set<string>(graph.focusIds);
    for (const edge of filteredEdges) {
      ids.add(edge.source);
      ids.add(edge.target);
    }
    return ids.size;
  }, [filteredEdges, graph]);

  useEffect(() => {
    if (!canvasRef.current || !graph) return;
    cyRef.current?.destroy();
    const visibleNodes = new Set<string>(graph.focusIds);
    const connectedNodeIds = new Set<string>();
    for (const edge of filteredEdges) {
      visibleNodes.add(edge.source);
      visibleNodes.add(edge.target);
      connectedNodeIds.add(edge.source);
      connectedNodeIds.add(edge.target);
    }
    const nodeElements: ElementDefinition[] = graph.nodes
      .filter((node) => visibleNodes.has(node.id))
      .map((node, index) => ({
          data: {
            id: node.id,
            label: node.name,
            kind: node.kind,
            focus: graph.focusIds.includes(node.id) ? "yes" : "no",
            isolatedFocus: graph.focusIds.includes(node.id)
              && !connectedNodeIds.has(node.id)
              ? "yes"
              : "no",
          },
          position: {
            x: (index % 100) * 44,
            y: Math.floor(index / 100) * 44,
          },
        }));
    const edgeElements: ElementDefinition[] = filteredEdges.map((edge) => ({
        data: {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          label: relationLabel(edge.kind),
          kind: edge.kind,
          certainty: edge.certainty,
        },
      }));
    const progressive = nodeElements.length > 1000 || edgeElements.length > 5000;
    const styles: Stylesheet[] = [
      {
        selector: "node",
        style: {
          "background-color": "#314158",
          "border-color": "#6b7c93",
          "border-width": 1,
          color: "#e8eef7",
          label: "data(label)",
          "font-family": "Segoe UI, Microsoft YaHei, sans-serif",
          "font-size": 10,
          "text-wrap": "ellipsis",
          "text-max-width": 120,
          "text-valign": "bottom",
          "text-margin-y": 8,
          width: 30,
          height: 30,
        },
      },
      { selector: 'node[kind = "class"], node[kind = "struct"], node[kind = "enum"]', style: { "background-color": "#7657d6", shape: "round-rectangle", width: 40, height: 30 } },
      { selector: 'node[kind = "member_function"], node[kind = "free_function"]', style: { "background-color": "#148aa0", shape: "ellipse" } },
      { selector: 'node[kind = "member_variable"], node[kind = "global_variable"]', style: { "background-color": "#c4772e", shape: "diamond" } },
      { selector: 'node[kind = "source_file"], node[kind = "external_file"]', style: { "background-color": "#3e8a68", shape: "round-tag" } },
      { selector: 'node[kind = "external_symbol"]', style: { "background-color": "#596273", "border-style": "dashed" } },
      { selector: 'node[focus = "yes"]', style: { "border-color": "#f4d35e", "border-width": 4, width: 54, height: 42, "font-size": 12, "font-weight": 600 } },
      { selector: 'node[isolatedFocus = "yes"]', style: { "border-color": "#ff8278", "border-style": "dashed" } },
      { selector: "node:selected", style: { "border-color": "#ffffff", "border-width": 3 } },
      {
        selector: "edge",
        style: {
          width: 1.5,
          "line-color": "#627087",
          "target-arrow-color": "#627087",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
        },
      },
      { selector: 'edge[certainty = "inferred"]', style: { "line-style": "dashed", opacity: 0.6 } },
      {
        selector: "edge:selected",
        style: {
          width: 3,
          "line-color": "#f4d35e",
          "target-arrow-color": "#f4d35e",
          label: "data(label)",
          color: "#e8eef7",
          "font-family": "Segoe UI, Microsoft YaHei, sans-serif",
          "font-size": 9,
          "text-background-color": "#111821",
          "text-background-opacity": 0.9,
          "text-background-padding": 3,
          "text-rotation": "autorotate",
        },
      },
    ];
    const cy = cytoscape({
      container: canvasRef.current,
      elements: progressive ? [] : [...nodeElements, ...edgeElements],
      style: styles,
      minZoom: 0.08,
      maxZoom: 3,
      layout: progressive ? { name: "preset" } : graphLayout(visibleNodes.size, false),
    });
    cy.on("tap", "node", (event) => setSelection({ type: "node", id: event.target.id() }));
    cy.on("tap", "edge", (event) => setSelection({ type: "edge", id: event.target.id() }));
    cy.on("dbltap", "node", (event) => {
      const id = event.target.id();
      const node = graph.nodes.find((item) => item.id === id);
      if (node) void loadGraph([graphNodeCandidate(node)], id, "single");
    });
    cyRef.current = cy;
    let cancelled = false;
    let animationFrame = 0;
    if (progressive) {
      let nodeIndex = 0;
      let edgeIndex = 0;
      const addNextBatch = () => {
        if (cancelled) return;
        cy.batch(() => {
          if (nodeIndex < nodeElements.length) {
            const nextIndex = Math.min(nodeIndex + 500, nodeElements.length);
            cy.add(nodeElements.slice(nodeIndex, nextIndex));
            nodeIndex = nextIndex;
          } else if (edgeIndex < edgeElements.length) {
            const nextIndex = Math.min(edgeIndex + 1000, edgeElements.length);
            cy.add(edgeElements.slice(edgeIndex, nextIndex));
            edgeIndex = nextIndex;
          }
        });
        setRenderProgress({
          loadedNodes: nodeIndex,
          totalNodes: nodeElements.length,
          loadedEdges: edgeIndex,
          totalEdges: edgeElements.length,
        });
        if (nodeIndex < nodeElements.length || edgeIndex < edgeElements.length) {
          animationFrame = window.requestAnimationFrame(addNextBatch);
          return;
        }
        setRenderProgress(null);
        cy.layout(graphLayout(nodeElements.length, false)).run();
      };
      animationFrame = window.requestAnimationFrame(addNextBatch);
    }
    return () => {
      cancelled = true;
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
      setRenderProgress(null);
      cy.destroy();
      if (cyRef.current === cy) cyRef.current = null;
    };
  }, [filteredEdges, graph, graphNodeCandidate, loadGraph]);

  useEffect(() => () => databaseRef.current?.close(), []);

  const selectedNode = selection?.type === "node"
    ? graph?.nodes.find((node) => node.id === selection.id) ?? null
    : null;
  const selectedEdge = selection?.type === "edge"
    ? graph?.edges.find((edge) => edge.id === selection.id) ?? null
    : null;

  const switchMode = (nextMode: ExplorerMode) => {
    if (nextMode === mode) return;
    const retainedNode = selectedNode
      ? graphNodeCandidate(selectedNode)
      : focusNodes[0] ?? null;
    if (!retainedNode) {
      setMode(nextMode);
      return;
    }
    const nextFocusNodes = [retainedNode];
    void loadGraph(nextFocusNodes, retainedNode.id, nextMode);
  };
  const allRelationKinds = useMemo(
    () => [...new Set(graph?.edges.map((edge) => edge.kind) ?? [])].sort(),
    [graph],
  );

  const toggleRelation = (kind: string) => {
    setRelationKinds((current) => {
      const next = new Set(current);
      if (next.has(kind)) next.delete(kind); else next.add(kind);
      return next;
    });
  };

  const toggleCertainty = (certainty: Certainty) => {
    setCertainties((current) => {
      const next = new Set(current);
      if (next.has(certainty)) next.delete(certainty); else next.add(certainty);
      return next;
    });
  };

  const removeFocusNode = (id: string) => {
    const nextFocusNodes = focusNodes.filter((node) => node.id !== id);
    if (nextFocusNodes.length === 0) {
      setFocusNodes([]);
      setGraph(null);
      setSelection(null);
      setCandidates([]);
      setError("");
      return;
    }
    void loadGraph(nextFocusNodes, undefined, mode);
  };

  const clearFocusNodes = () => {
    setFocusNodes([]);
    setGraph(null);
    setSelection(null);
    setCandidates([]);
    setError("");
    setQuery("");
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-symbol" aria-hidden="true">⌘</span>
          <div><strong>UE ITPS</strong><span>关系浏览器</span></div>
        </div>
        <label className="file-button">
          <input
            type="file"
            accept=".sqlite3,.sqlite,.db,application/vnd.sqlite3"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void openDatabase(file);
              event.currentTarget.value = "";
            }}
          />
          {summary ? "更换数据库" : "打开数据库"}
        </label>
      </header>

      <section className="toolbar" aria-label="图谱查询工具栏">
        <div className="mode-switch" role="group" aria-label="浏览模式">
          <button
            type="button"
            className={mode === "single" ? "active" : ""}
            onClick={() => switchMode("single")}
            disabled={busy}
          >单节点浏览</button>
          <button
            type="button"
            className={mode === "multi" ? "active" : ""}
            onClick={() => switchMode("multi")}
            disabled={busy}
          >多节点关系</button>
        </div>
        <form className="search-form" onSubmit={submitSearch}>
          <div className="search-box">
            <span aria-hidden="true">⌕</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={summary
                ? mode === "multi" && focusNodes.length > 0
                  ? "继续搜索并添加关注节点…"
                  : "搜索类、函数、变量或文件…"
                : "请先打开数据库"}
              disabled={!summary || busy}
              aria-label="符号名称"
            />
            <button type="submit" disabled={!summary || busy || !query.trim()}>查询</button>
          </div>
          {candidates.length > 0 && (
            <div className="candidate-menu" role="listbox" aria-label="搜索候选项">
              {candidates.map((candidate) => (
                <button
                  type="button"
                  key={candidate.id}
                  onClick={() => void addFocusNode(candidate)}
                >
                  <span className={`kind-mark kind-${candidate.kind}`} aria-hidden="true" />
                  <span>
                    <strong>{candidate.qualifiedName}</strong>
                    <small>
                      {mode === "multi" && focusNodes.some((node) => node.id === candidate.id) ? "已选择 · " : ""}
                      {nodeKindLabel(candidate.kind)}{candidate.signature ? ` · ${candidate.signature}` : ""}
                    </small>
                  </span>
                </button>
              ))}
            </div>
          )}
        </form>
        {mode === "single" && (
          <>
            <label>深度
              <select value={depth} onChange={(event) => setDepth(Number(event.target.value))} disabled={!summary || busy}>
                {[1, 2, 3, 4].map((value) => <option key={value} value={value}>{value} 层</option>)}
              </select>
            </label>
            <label>节点上限
              <select value={maxNodes} onChange={(event) => setMaxNodes(Number(event.target.value))} disabled={!summary || busy}>
                {[50, 100, 200, 300].map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
          </>
        )}
      </section>

      {focusNodes.length > 0 && (
        <section className="focus-bar" aria-label="关注节点">
          <strong>关注节点</strong>
          <div className="focus-list">
            {focusNodes.map((node) => (
              <span className="focus-chip" key={node.id} title={node.qualifiedName}>
                <i className={`kind-mark kind-${node.kind}`} aria-hidden="true" />
                <span>{node.qualifiedName}</span>
                <button
                  type="button"
                  onClick={() => removeFocusNode(node.id)}
                  aria-label={`移除 ${node.qualifiedName}`}
                >×</button>
              </span>
            ))}
          </div>
          <button type="button" onClick={() => void loadGraph(focusNodes, undefined, mode)} disabled={busy}>更新关系</button>
          <button type="button" onClick={clearFocusNodes} disabled={busy}>清空</button>
        </section>
      )}

      {error && <div className="error-banner" role="alert">{error}</div>}

      <div className={`workspace${focusNodes.length > 0 ? " with-focus" : ""}`}>
        <aside className="filters" aria-label="图谱筛选">
          {summary ? (
            <div className="database-summary">
              <span className="status-dot" aria-hidden="true" />
              <div><strong>{databaseName}</strong><span>{summary.projectKey}</span></div>
              <p>{summaryText(summary)}</p>
              <small>扫描于 {readableDate(summary.createdAt)}</small>
            </div>
          ) : (
            <div className="database-summary empty"><strong>尚未加载数据库</strong><span>请选择信息池 snapshots 目录中的 SQLite 快照。</span></div>
          )}

          {graph && (
            <>
              <fieldset>
                <legend>可信级别</legend>
                {(Object.keys(CERTAINTY_LABELS) as Certainty[]).map((certainty) => (
                  <label className="check-row" key={certainty}>
                    <input type="checkbox" checked={certainties.has(certainty)} onChange={() => toggleCertainty(certainty)} />
                    <span className={`certainty certainty-${certainty}`} aria-hidden="true" />
                    {CERTAINTY_LABELS[certainty]}
                  </label>
                ))}
              </fieldset>
              <fieldset>
                <legend>关系类型</legend>
                {allRelationKinds.map((kind) => (
                  <label className="check-row" key={kind}>
                    <input type="checkbox" checked={relationKinds.has(kind)} onChange={() => toggleRelation(kind)} />
                    {relationLabel(kind)}
                    <small>{graph.edges.filter((edge) => edge.kind === kind).length}</small>
                  </label>
                ))}
              </fieldset>
            </>
          )}
        </aside>

        <section className="graph-stage" aria-label="知识图谱">
          {busy && <div className="loading"><span />正在读取关系…</div>}
          {!graph && !busy && (
            <div className="empty-stage">
              <div className="empty-graph" aria-hidden="true"><i /><i /><i /><i /></div>
              <h1>{summary ? "搜索并添加关注节点" : "打开知识图谱数据库"}</h1>
              <p>{summary ? "选择一个节点可浏览其局部关系；继续添加节点可查看它们之间的最短联通路径。" : "数据库只会在当前浏览器内存中读取，不会上传或修改。"}</p>
            </div>
          )}
          {graph && (
            <>
              <div ref={canvasRef} className="graph-canvas" />
              <div className="graph-actions">
                <button onClick={() => cyRef.current?.fit(undefined, 42)}>适应画布</button>
                <button onClick={() => cyRef.current?.layout(graphLayout(visibleNodeCount, true)).run()}>重新布局</button>
              </div>
              <div className="graph-status">
                {visibleNodeCount} 个可见节点 · {filteredEdges.length} 条可见关系
                {mode === "multi" && focusNodes.length === 1 && <span>请继续添加关注节点</span>}
                {mode === "multi" && graph.requestedConnectionCount > 0 && (
                  <span>{graph.connectionCount}/{graph.requestedConnectionCount} 对节点已联通</span>
                )}
                {mode === "multi" && graph.requestedConnectionCount > 0 && graph.connectionCount === 0 && (
                  <span>数据库中没有找到联通关系</span>
                )}
                {mode === "single" && graph.truncated && <span>已达到节点上限</span>}
                {renderProgress && (
                  <span>
                    正在绘制 {renderProgress.loadedNodes}/{renderProgress.totalNodes} 个节点 · {renderProgress.loadedEdges}/{renderProgress.totalEdges} 条关系
                  </span>
                )}
              </div>
            </>
          )}
        </section>

        <aside className="details" aria-label="选中项详情">
          {selectedNode && (
            <>
              {mode === "multi" && !focusNodes.some((node) => node.id === selectedNode.id) && (
                <button className="center-button" onClick={() => void addFocusNode(graphNodeCandidate(selectedNode))}>加入关注节点</button>
              )}
              <button className="center-button" onClick={() => void loadGraph([graphNodeCandidate(selectedNode)], selectedNode.id, "single")}>仅查看此节点</button>
              <NodeDetail node={selectedNode} />
            </>
          )}
          {selectedEdge && graph && <EdgeDetail edge={selectedEdge} nodes={graph.nodes} />}
          {!selectedNode && !selectedEdge && <div className="detail-empty"><strong>详细信息</strong><span>点击节点或关系查看代码证据。</span></div>}
        </aside>
      </div>
    </main>
  );
}
