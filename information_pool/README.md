# 文件图谱

`information_pool/` 把一个明确选择的 Unreal 工程转换为本地 SQLite 文件图谱。当前范围包括 `.uproject`、`.uplugin`、Target、Module Build.cs、项目 C++ 文件和直接 Include。

```bash
python information_pool/build_file_graph.py --project D:/Projects/MyGame/MyGame.uproject --output D:/Graphs/MyGame.sqlite3
```

数据库保存 `metadata`、`nodes`、`edges` 和 `edge_evidence`。每条关系都必须带来源证据；解析警告写入图谱元数据，但不会被提升为编译或运行结论。

该组件不扫描资产、不连接 Editor、不写回 Unreal 工程。生成的数据库可由 `show/` 本地打开。

```bash
python -m unittest discover -s information_pool/tests -v
```
