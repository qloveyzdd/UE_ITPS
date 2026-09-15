# 文件图谱

`information_pool/` 将明确选择的 Unreal 工程转换为本地 SQLite 文件图谱。当前包括工程/插件描述符、Target、Module Build.cs、项目 C++ 文件和直接 Include 关系。

```bash
python information_pool/build_file_graph.py --project D:/Projects/MyGame/MyGame.uproject --output D:/Graphs/MyGame.sqlite3
```

数据库契约为 `ue-itps.file-graph.v1`，保存 `metadata`、`nodes`、`edges`、`edge_evidence`、`warnings`。关系保留来源证据；警告存入独立表，数量记录在元数据。写入使用临时数据库再替换指定输出，不回写被扫描工程。

当前没有 Git 提交绑定、不可变快照库、增量更新或通用查询服务；旧产品设想中的信息池能力不能直接套用。数据库可由 [show/](../show/README.md) 本地打开。该组件不连接 Editor，也不证明资产行为或有效构建依赖。

```bash
python -m unittest discover -s information_pool/tests -v
```

测试用临时工程生成真实 SQLite，检查关系证据与外键。完整测试分层见[测试与验证](../docs/TESTING.md)。
