# UE Editor Tools

`edittools` 是一组面向运行中 Unreal Editor 的确定性、只读工具。它们通过 UE 自带的 Python Remote Execution、Toolset Registry、Gameplay Tags Toolset、Asset Registry 和 Blueprint Tools 获取编辑器事实，不依赖 Lyra 的路径、标签或类型。

## 前置条件

- 当前第一版以 UE 5.8.2 验证。
- 在目标项目中启用 `Python Editor Script Plugin`。
- 在 `项目设置 → 插件 → Python` 中启用 `Enable Remote Execution?`。
- 同一个 Editor 的命令连接会由工具自动串行化。

## 工具

```powershell
python edittools/ue_editor_list_sessions.py --project D:/Game/Game.uproject
python edittools/ue_editor_list_gameplay_tags.py --project D:/Game/Game.uproject --parent-tag Gameplay.Message
python edittools/ue_editor_find_tag_referencers.py --project D:/Game/Game.uproject --tag Gameplay.Message.Example
python edittools/ue_editor_inspect_blueprint.py --project D:/Game/Game.uproject --asset /Game/BP_Example
python edittools/ue_editor_scan_gameplay_messages.py --project D:/Game/Game.uproject --root /Game --tag Gameplay.Message.FromCode
python edittools/ue_editor_export_message_graph.py --input message-scan.json
python edittools/ue_editor_export_asset_graph.py --project D:/Game/Game.uproject --root /Game
python edittools/ue_editor_scan_blueprint_structure.py --project D:/Game/Game.uproject --root /Game
python edittools/ue_editor_scan_data_tables.py --project D:/Game/Game.uproject --root /Game
python edittools/ue_editor_scan_primary_assets.py --project D:/Game/Game.uproject
python edittools/ue_scan_cxx_gameplay_messages.py --project D:/Game/Game.uproject
python edittools/ue_scan_config_graph.py --project D:/Game/Game.uproject
```

所有 Editor 工具只读取现场状态，不保存、编译或修改资产。扫描结果若包含未保存的脏包，图谱导出默认拒绝；只有显式传入 `--allow-dirty` 才会继续。

`ue_editor_scan_gameplay_messages.py` 会自动查询 Blueprint 中发现的静态 Channel。对于只在 C++ 中出现的消息 Channel，可重复传入 `--tag`，把代码图谱已经识别出的 Tag 一并用于资产引用者查询。

## 消息关系

扫描器输出 Blueprint 中的发布和订阅操作、Channel、PayloadType、MatchType、Pin 类型和值以及直接连接。Channel 分为：

- `static`：未连接且存在明确 Gameplay Tag 默认值。
- `dynamic`：Channel Pin 有输入连接，保留直接连线证据。
- `unresolved`：既没有可解析默认值，也没有可解释的静态 Tag。

图谱导出使用 `PUBLISHES_EVENT`、`SUBSCRIBES_EVENT`、`USES_TYPE`、`REFERENCES` 和 `CONTAINS` 关系。UE 5.8 Python 不暴露 NodeGuid/GraphGuid，因此以项目、资产、Graph 和节点对象路径生成快照内的确定性标识。

## 逻辑知识图谱

新增采集器覆盖 Asset Registry 直接依赖、Blueprint 类型结构、DataTable 行、Primary Asset、
项目本地配置和 C++ Gameplay Message。Map 作为普通资产以及配置或 Primary Asset 的目标进入
图谱；工具不会枚举 Map 内的 Actor、Component、Transform、World Partition Actor Descriptor
或 External Actor，这些属于场景组装而非逻辑相关性。

建议把各工具输出保存为独立 JSON，再统一构建：

```powershell
python edittools/ue_build_knowledge_graph.py `
  --input asset-graph.json `
  --input blueprint-structure.json `
  --input data-tables.json `
  --input primary-assets.json `
  --input config-graph.json `
  --input cxx-messages.json `
  --input blueprint-messages.json > knowledge-graph.json

python edittools/ue_validate_knowledge_graph.py --input knowledge-graph.json
python edittools/ue_diff_knowledge_graph.py --current knowledge-graph.json --previous previous-graph.json
```

统一图谱按项目、实体种类和明确路径生成稳定 ID，合并资产、类、Tag、Payload、DataTable Row、
Primary Asset 和配置项，并为每条关系保留源码位置或 Editor 对象路径证据。输入含未保存脏包时，
构建器默认拒绝；只有显式使用 `--allow-dirty` 才会继续。

统一图谱也可以作为现有信息池的附加证据：

```powershell
python information_pool/build_information_pool.py `
  --project D:/Game/Game.uproject `
  --pool data/Game `
  --knowledge-graph knowledge-graph.json
```

信息池会尝试把明确匹配的 C++ 类型和函数归一到现有静态符号，其余逻辑实体作为稳定节点写入
同一个不可变 SQLite 快照。

## 测试

```powershell
python -m unittest discover -s edittools/tests -t edittools -v
```
