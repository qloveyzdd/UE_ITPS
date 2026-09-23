# 工具清单与输出契约

## 核心静态工具

机器可读清单由 `python sourcetools/ue_list_tools.py` 生成，当前包含 16 个入口。以下 CLI 文件均位于 `sourcetools/`，执行时加 `.py`。具体可选参数以各入口 `--help` 为准。

| 类别 | CLI | 输入与结果 |
|---|---|---|
| 工程 | `ue_find_projects` | `--search-root` → `.uproject` 候选 |
| 工程 | `ue_resolve_engine` | `--project` → Engine 路径、Build.version 与版本 |
| 工程 | `ue_read_project_descriptor` | `--project --engine-build-version` → 模块名、插件启用/禁用、非空 TargetAllowList |
| 构建 | `ue_find_build_descriptor` | `--project` 与 `--modulename` 或 `--pluginname` → 描述文件候选 |
| 构建 | `ue_inspect_targets` | `--project` → Target 类型、直接及可解析继承的模块声明 |
| 构建 | `ue_inspect_module_rules` | `--rules` → public/private/dynamic 直接依赖 |
| 插件 | `ue_read_plugin_descriptor` | `--plugin` → 该插件的 Modules 与 Plugins 声明 |
| 模块 | `ue_inspect_module_entry` | `--rules` → 注册宏、源码位置、可唯一匹配的头文件 |
| 文件 | `ue_list_module_cxx_sources` | `--rules` → 配对文件、独立头文件、独立实现 |
| Include | `ue_list_cxx_includes` | `--source` → 直接引用与物理来源 |
| 类型 | `ue_list_cxx_types` | `--source` → 类型、变量、自由函数和宏定义清单 |
| 类型 | `ue_inspect_cxx_type` | `--source --type` → 基类、直接成员、成员定义与接口候选依据 |
| 函数 | `ue_list_cxx_functions` | `--source` → 每处函数定义、限定名、签名及位置 |
| 函数 | `ue_inspect_cxx_function` | `--source --function` → 符号候选、委托及可选语法详情 |
| 检索 | `ue_inspect_cxx_scope` | `--project --profile` → 系统/类型/函数/证据四级导航 |
| 工具池 | `ue_list_tools` | 无参数 → 入口、输入和能力清单 |

## 工程、构建与文件边界

- `EngineAssociation` 是关联键。实际版本由 `ue_resolve_engine` 读取 Build.version；描述符工具不解析该关联键，必须另传 Engine Build.version 作为文件定位锚点。
- 多候选时由调用方明确选择；用户已经点名的工程或模块可以据此消除歧义。
- Build.cs 只提取 `Add/AddRange` 中的依赖字面量及可静态到达的同文件辅助函数。条件不求值，变量或计算表达式报告警告；空字面数组是有效空列表。
- 模块入口只认与所选模块同名的 `IMPLEMENT_PRIMARY_GAME_MODULE`、`IMPLEMENT_MODULE`；未找到头文件可以正常返回 null。
- 模块文件清单按物理 Build.cs 边界排除嵌套模块与生成物。配对优先同目录及 Public/Classes→Private 镜像，再尝试模块内唯一同主名候选；歧义保留。返回路径相对于项目根目录。
- C++ 事实工具接受一个明确的 `.h/.hpp/.cpp/.cc`，或同主名的一份头文件与一份实现文件；不自行搜索伴随文件，不读取传递头文件。
- Include 唯一定位只证明物理来源，不证明有效编译搜索顺序或依赖声明正确。生成引用单独标识；缺失、歧义及未解析宏放入校验问题。

## 类型与函数结构

类型清单返回 `classes/structs/enums/global_variables/free_functions/macros`，只保留定义，排除前向声明、extern 声明和函数原型。union 归入 structs。局部 `#define` 返回名称、参数及位置，不返回宏体；UE 注解保留在对应定义上。支持的原生 GameplayTag 定义投影为 `FNativeGameplayTag` 变量。

类型详情的 `matches` 包含 `base_types`、`member_anchors`、`member_functions` 与接口候选原因；不展开继承和嵌套类型。类型选择名必须精确匹配。

函数清单保留每处定义，包括所选文件中没有所属类定义的类外实现。用 `qualified_name` 作为选择名；`source_qualified_name` 保留原始写法。限定名精确匹配；简单函数名有意匹配所有同名定义，重载不因名称相同而合并。无定义时清单为空；详情查询无匹配时返回错误。

`function_id` 与文件选择、签名和源码位置相关；它不是永久实体 ID。底层证据使用 `unit: cpp/header` 与行号，调用方应保存输入路径对应关系。结束行是包含式行号；类型起始位置可包含附带 UE 宏。

默认函数详情返回按源码位置排序的 `external_symbols`。类型、全局变量、自由函数、宏、成员调用、函数地址、回调目标和 unknown 都是局部候选分类。函数地址需要可见函数声明证据；冲突声明、占位类型和不能确认的间接调用保留 unknown。

分析覆盖函数体、构造初始化列表及函数 try/catch；默认参数等声明区域不计入执行区域。Lambda 和局部类型的成员函数分别保留作用域。源码显示保留字符串、原始字符串、字符常量及注释内容。

## 委托与语法详情

委托采用唯一的 `delegate_contract_revision: 2`：

- `delegate_operations` 区分创建、绑定、添加、解除绑定、移除、清空、执行、广播和查询。
- `subject`、`delegate_type`、`callback`、`binding`、`arguments`、`result`、`resolution`、`execution_scope` 保留操作对象与依据。
- `identified` 要求选中文件中的类型证据与支持的 API 形状；`candidate` 不证明真实委托关系。
- 回调由指定参数位置识别；payload 中的任意地址不自动成为回调。外层函数与 Lambda 操作分开记录。
- 不追踪跨函数绑定、对象存活或回调线程安全。

`--include-syntax-flow` 按所选视图返回语法详情。默认 full 保留原有调用/控制语句契约；优先级视图另保留调用表达式、参数及初始化、赋值、更新、条件、返回等 `statements`。函数的 `statement_summary` 是语法汇总，不是执行次数或完整数据流。

## 优先级视图

`ue_list_cxx_types` 和 `ue_inspect_cxx_function` 默认 `--view full`，可选 `behavior` 或 `structure`；后两者支持重复的 `--focus NAME` 精确关注项。

- 类型清单仍保留全部定义，通过 `view.sections` 表达展示优先级。
- 函数优先级视图使用 `symbol_groups` 替代 `external_symbols`，保留出现次数、每次行号、接收者、命中规则及 Lambda 作用域。
- 已知容器增删/清空/重置优先展开；Reserve 折叠。被条件、赋值、参数、接收者或 return 使用的查询与指针取值优先展开。
- 日志参数辅助调用归入 `log_groups`；日志条件、已知状态写入、Lambda 与显式关注项保留。
- `view_summary.hidden_by_rule` 汇总隐藏原因；折叠不意味着已证明没有副作用。语法详情可恢复被隐藏调用。

优先级视图和 Scope 按逐位置事实计数；旧 full 的外部符号维持同名同一行合并口径。不同视图的条目数、符号组数和 JSON 字节数不能直接当作同一指标。

## 分层导航与地图

```bash
python sourcetools/ue_inspect_cxx_scope.py --project LyraStarterGame/LyraStarterGame.uproject --profile sourcetools/profiles/lyra_equipment.json
```

默认 `--level system --view behavior`。保持相同工程与配置，使用上一层返回的 ID：

- `--level type --select <类型ID>`
- `--level function --select <函数ID>`
- `--level evidence --select <关系ID或函数ID>`

`--limit` 为 1～100，默认 20；按 `page.next_offset` 翻页。`full` 仍然分页。证据层返回完整表达式、参数和源码定位；`summary.facts.call` 仅统计未进入符号清单的补充调用，不能当作总调用数。

配置包含 `version/id/name/description/units`，单元内是显式 `sources`，可附人工 `roles/entry_points/navigation/reviewed_sources`。工具验证定义、路径与重复项，保留未分类类型；关系名称相同不建立跨文件语义绑定。

配置可附 `inventory_rules`（项目内显式 Build.cs 路径数组）。`--include-audit` 才枚举这些模块的文件路径，并返回 `audit.files/coverage/counting`：已解析、带解析诊断、未选择文件，以及逐文件文本指纹。未选择文件不读取源码；没有配置模块时 `inventory_basis=profile_only`、`inventoried=null`，不宣称项目覆盖率。无效或不可读的已选文件仍使扫描失败，不被静默跳过；模块枚举的排除规则和校验保存在 `audit.inventories`。

Scope 和地图的 `provenance` 记录分析修订号、语法包/检索规则版本、工程/配置/源码摘要及 Engine 身份。源码指纹基于去 BOM、统一换行后的 UTF-8 文本；不是原始文件字节哈希。`snapshot` 还包含 Include 定位和扫描问题。源码、配置或相关环境变化后重新取得 ID；这不是构建快照或跨版本实体 ID。

单次 Scope 构造复用模块目录发现结果，每个文件组解析一次。独立 CLI/Scope 重新加载范围及目录；没有磁盘解析缓存或跨扫描增量更新。

### 候选声明与未解析原因

- 关系层的 `resolution` 含状态、原因、候选数量和契约数量；进入 evidence 层取得完整 `basis/next_step/candidates/receiver_types/contracts/member`。
- `candidates` 分别保留声明与定义的签名、文件位置和文件组；有函数体的候选提供 `function_id`，可继续进入 function/evidence 层。`receiver_types` 提供已选择接收者类型的 type ID。
- 匹配依据为词法限定名、接收者类型与成员名、显式基类名；支持 `TObjectPtr<T>->` 的类型候选。保留重载及条件定义，不根据实参数量猜测最终重载；过滤其他文件组的静态自由函数、静态变量和匿名命名空间声明。
- `candidate` 表示声明线索、有限 API 角色提示或成员地址语法分类，以 `reason` 区分；契约和地址分类的 `candidates` 为空，不生成可跳转的引擎声明。`ambiguous` 保留多种签名或多个定义；`unresolved` 附检查方向。Include 可见性、参数转换、模板实例化和虚调用派发均未验证。
- 原因包含 `declaration_not_in_scope`、`receiver_type_unresolved`、`ambiguous_candidates`、`unsupported_expression`、`requires_semantics`、`semantic_contract`、`member_address`；非调用未知项暂为 `unclassified_reference`。已识别宏标为 `macro`，有声明线索为 `scope_candidate`。`semantic_contract` 只说明有限的 UE API 角色（复制生命周期、FastArray、AbilitySystem、工厂/类型收窄等），不证明重载、可见性或运行派发；`member_address` 只标记成员地址语法，仍需检查成员声明。原因描述当前索引的证据边界，不是编译错误诊断。
- 契约要求匹配未被选中声明遮蔽的自由函数名，或接收者/基类类型与调用形状；布尔回调检查实际类型签名及别名。普通同名方法、局部遮蔽和无法确定类型的迭代器保持未解析。当前 `analysis_revision=2`，旧快照的选择 ID 需重新获取。
- `summary.unresolved_symbols` 仍为原始 unknown 符号出现次数；`unresolved_by_reason` 的和与其相等。`summary.semantic_contracts` 按唯一调用位置统计有限契约，跨文件找到候选或契约也不改写原始事实。断言、日志、保护函数不新增契约。`call_occurrences` 按调用起止位置去重，包含隐藏调用和 Lambda；`candidate_status` 对这些调用统计解析状态，因此与 unknown 符号数不同。

导航地图导出器位于 `sourcetools/lyra/`，不属于 16 个核心入口：

```bash
python sourcetools/lyra/export_navigation_map.py --project LyraStarterGame/LyraStarterGame.uproject --profile sourcetools/profiles/lyra_equipment.json --output lyra-equipment-map.json
```

地图保留文件组、类型、人工职责和检查查询。导航提示只有源码文本 SHA-256 一致、定义唯一、要求证据齐全且无解析告警时才为 `reviewed`；过期或歧义降为 `candidate`，无可检查目标为 `unresolved`。重建地图不会自动更新人工复核指纹，也不实现持续变更监控。

已有配置：装备导航 `lyra_equipment.json`、装备与技能授予链 `lyra_equipment_chain.json`（5 组/10 文件、4 条证据提示）、21 个问题的 `lyra_reviewed_navigation.json`、30 个抽样问题的 `lyra_sampling_reviewed.json`。保留问题与验证方法见 [TESTING.md](TESTING.md)。

## Editor 与辅助工具

`edittools/` 当前有 16 个 CLI：会话、Gameplay Tag 与引用、资产关系、DataTable/DataAsset/Primary Asset、Blueprint、Gameplay Message、配置及知识图谱处理。实时命令需要明确 `--node-id`，会话发现命令除外；详见 [Editor 工具](../edittools/README.md)。

`sourcetools/lyra/query_lyra_asset_registry.py` 是旧调查使用的 UE Editor Python 查询脚本；`archive_lyra_run.ps1` 与 `new_lyra_baseline_fingerprint.ps1` 用于运行日志归档和文件指纹。它们不是当前源码解析测试入口，使用前查看脚本参数及[历史捕获说明](../.planning/codebase/RUNTIME-EVIDENCE.md)。
