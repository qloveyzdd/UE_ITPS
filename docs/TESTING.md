# 测试与验证

测试按组件独立运行，避免把外部 UE 工程、已启动 Editor 或网络连接作为默认前提。

## 核心静态工具

```bash
python -m unittest discover -s tests -v
```

覆盖 CLI/Schema 一致性、Schema 有效性、全部入口帮助，以及最小 `.uproject` 上的工程导航、Build.cs 和显式 C++ 文件工作流。

## Editor 与离线工具

```bash
python -m unittest discover -s edittools/tests -t edittools -v
```

测试不连接真实 Editor；它验证 CLI/Schema 契约、配置扫描和知识图谱合并。`ue_scan_cxx_gameplay_messages.py` 当前因遗留导入缺失被标记为预期失败，修复产品实现后应移除该标记。

## 文件图谱与连接池

```bash
python -m unittest discover -s information_pool/tests -v
python -m unittest discover -s mcp_connection_pool/tests -t . -v
```

文件图谱测试构建真实临时 SQLite 并检查关系证据和外键；连接池测试覆盖缺失、唯一匹配、版本不兼容和多连接歧义。

## 本地浏览器

```bash
cd show
npm test
```

该命令先执行 TypeScript 检查和生产构建，再使用内存 SQLite 验证摘要、关系查询、证据和搜索。

## 验收标准

- 核心、文件图谱、连接池和页面测试全部通过。
- Editor 测试除已登记的单个预期失败外全部通过。
- 测试不修改仓库内工程或资产。
- 文档中的工具数量、命令和能力边界与代码一致。
