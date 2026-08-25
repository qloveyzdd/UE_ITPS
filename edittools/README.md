# Editor 与离线检查工具

`edittools/` 提供 16 个 CLI，用于读取已连接 Unreal Editor 的资产与 Blueprint 现场状态，以及处理配置、C++ Gameplay Message 和统一知识图谱。

实时 Editor 命令必须通过 `--node-id` 精确选择节点；工具只读，不保存、编译或修改资产。先列出当前会话：

```bash
python edittools/ue_editor_list_sessions.py
python edittools/ue_editor_list_gameplay_tags.py --node-id <node-id>
python edittools/ue_editor_inspect_blueprint.py --node-id <node-id> --asset /Game/BP_Sample
```

离线命令直接读取明确输入：

```bash
python edittools/ue_scan_config_graph.py --project D:/Projects/MyGame/MyGame.uproject
python edittools/ue_build_knowledge_graph.py --input facts.json > graph.json
python edittools/ue_validate_knowledge_graph.py --input graph.json
```

每个公开 CLI 在 `edittools/schemas/` 有同名 Schema。当前 `ue_scan_cxx_gameplay_messages.py` 依赖已移除的核心解析模块，不能正常导入；这是已登记的产品缺口，不应作为可用命令调用。

测试命令：

```bash
python -m unittest discover -s edittools/tests -t edittools -v
```
