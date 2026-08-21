# UE 文件知识图谱（第一阶段）

本目录只负责把一个明确选择的 Unreal Engine 项目转换成文件级 SQLite 图谱。事实来源为
`sourcetools/` 中现有的确定性项目检查器。

```powershell
python information_pool/build_file_graph.py `
  --project D:/Projects/MyGame/MyGame.uproject `
  --output D:/Graphs/MyGame.sqlite3
```

第一阶段包含 `.uproject`、项目内 `.uplugin`、`Target.cs`、`Build.cs`、C++ 源文件和直接
Include。关系覆盖项目声明、插件启用、Target 模块引用、模块依赖、模块文件归属、模块入口和
Include。无法在项目内唯一定位的模块、插件和 Include 会保留为外部或未解析节点。

SQLite 表为 `metadata`、`nodes`、`edges`、`edge_evidence` 和 `warnings`。图谱是静态证据，
不替代 UBT、UHT、编译器、Editor 或运行时验证。
