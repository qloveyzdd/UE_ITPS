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
```

所有 Editor 工具只读取现场状态，不保存、编译或修改资产。扫描结果若包含未保存的脏包，图谱导出默认拒绝；只有显式传入 `--allow-dirty` 才会继续。

`ue_editor_scan_gameplay_messages.py` 会自动查询 Blueprint 中发现的静态 Channel。对于只在 C++ 中出现的消息 Channel，可重复传入 `--tag`，把代码图谱已经识别出的 Tag 一并用于资产引用者查询。

## 消息关系

扫描器输出 Blueprint 中的发布和订阅操作、Channel、PayloadType、MatchType、Pin 类型和值以及直接连接。Channel 分为：

- `static`：未连接且存在明确 Gameplay Tag 默认值。
- `dynamic`：Channel Pin 有输入连接，保留直接连线证据。
- `unresolved`：既没有可解析默认值，也没有可解释的静态 Tag。

图谱导出使用 `PUBLISHES_EVENT`、`SUBSCRIBES_EVENT`、`USES_TYPE`、`REFERENCES` 和 `CONTAINS` 关系。UE 5.8 Python 不暴露 NodeGuid/GraphGuid，因此以项目、资产、Graph 和节点对象路径生成快照内的确定性标识。

## 测试

```powershell
python -m unittest discover -s edittools/tests -t edittools -v
```
