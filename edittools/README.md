# Editor 与离线检查工具

`edittools/` 提供 18 个 CLI，用于读取已连接 Unreal Editor 的资产、Blueprint 和关卡现场状态，以及处理配置、C++ Gameplay Message 和统一知识图谱。

实时 Editor 命令必须通过 `--node-id` 精确选择节点；工具只读，不保存、编译或修改资产。先列出当前会话：

```bash
python edittools/ue_editor_list_sessions.py
python edittools/ue_editor_list_gameplay_tags.py --node-id <node-id>
python edittools/ue_editor_inspect_blueprint.py --node-id <node-id> --asset /Game/BP_Sample
python edittools/ue_editor_find_blueprint_references.py --node-id <node-id> --target /Script/MyGame.MyCharacter:ApplyDamage
python edittools/ue_editor_scan_level_actors.py --node-id <node-id>
```

离线命令直接读取明确输入：

```bash
python edittools/ue_scan_config_graph.py --project D:/Projects/MyGame/MyGame.uproject
python edittools/ue_scan_cxx_gameplay_messages.py --project D:/Projects/MyGame/MyGame.uproject
python edittools/ue_build_knowledge_graph.py --input facts.json > graph.json
python edittools/ue_validate_knowledge_graph.py --input graph.json
```

每个公开 CLI 在 `edittools/schemas/` 有同名 Schema。

Blueprint 结构扫描会返回稳定的 Blueprint、Graph、Node、Pin、变量和组件标识，包含 Pin 类型、默认值、连线、节点符号和直接引用。`ue_editor_find_blueprint_references.py` 可按符号或对象路径查找蓝图引用，`ue_editor_scan_level_actors.py` 读取当前已加载世界中的 Level Blueprint、Actor 实例、组件层级、Transform、Tags、Data Layers 和常见实例属性。

`ue_build_knowledge_graph.py` 可以同时接收 `ue_editor_scan_blueprint_structure`、资产图谱以及 `ue_list_cxx_types`、`ue_list_cxx_functions`、`ue_inspect_cxx_type`、`ue_inspect_cxx_function` 的结果，生成 `CALLS`、`READS`、`WRITES`、`MAPS_TO`、`REFERENCES_SYMBOL` 和图节点连线关系。

测试命令：

```bash
python -m unittest discover -s edittools/tests -t edittools -v
```

这些测试使用离线输入与模拟数据，不连接真实 Editor；通过不代表 Blueprint 或消息链路运行正确。完整分层见[测试与验证](../docs/TESTING.md)。
