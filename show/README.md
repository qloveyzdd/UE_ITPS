# 本地文件图谱浏览器

`show/` 是只在本机读取 SQLite 文件图谱的 React 页面。它支持查看摘要、搜索文件、按深度展开上下游关系、查看证据，以及按节点类型隐藏结果。

需要 Node.js 22.13 或更高版本：

```bash
cd show
npm install
npm run dev
```

浏览器只接受 `information_pool/` 生成的 `ue-itps.file-graph.v1` 数据库。文件在浏览器内本地解析，不上传，也不修改数据库或 Unreal 工程。

验证：

```bash
npm test
```
