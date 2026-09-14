# UE ITPS

UE ITPS 是一组面向 Unreal Engine 工程的确定性、只读检查工具。它从明确选择的 `.uproject`、构建规则和 C++ 源文件中提取 JSON 事实，不启动 Editor、不编译工程，也不修改项目内容。

## 当前组成

- `sourcetools/`：根目录保留 16 个静态检查 CLI，负责工程、Engine、Module、Target、Plugin 和 C++ 源文件分析；`lyra/` 集中存放 Lyra 专用证据工具。
- `schemas/`：核心 CLI 的 JSON Schema，采用 Draft 2020-12。
- `edittools/`：16 个 Editor/离线检查 CLI；连接 Editor 的命令只读取已连接节点的现场状态。
- `information_pool/`：把工程、模块、Target、源码和 Include 关系写入 SQLite 文件图谱。
- `show/`：本地打开并浏览文件图谱的 React 页面。
- `mcp_connection_pool/`：被动选择宿主已提供的 UE 5.8 只读 MCP 连接，不负责启动或重连外部进程。

`ExternalProjects/` 和 `LyraStarterGame/` 是检查对象或参考工程，不属于工具运行时实现。仓库内的 `parsers/tree-sitter-ue-cpp` 是独立子模块。

源码语法统一由 Tree-sitter 前端处理：C++/UE 宏通过 `tree-sitter-ue-cpp` 和 `cpp_frontend.py` 生成结构化事实，C# 通过 `tree-sitter-c-sharp` 和 `syntax_tree.py` 生成结构化事实。下游工具只负责名称解析和 UE 领域语义，不再用正则或字符串切割恢复 C++/C# 语法；INI、对象路径等独立数据格式仍由各自解析器处理。

Lyra 全量 Tree-sitter 回归基线覆盖项目与插件 `Source` 目录内 707 个 `.h/.cpp` 文件，要求原始 AST 无语法恢复，校验 Slate 参数声明与自动化测试声明的 UE 专用节点，并固定关键事实计数。另逐一对照原始 AST 的类型、函数定义及调用所属函数，检查每处定义的引用独立性和宏结束行，避免只有计数正确却存在遗漏或覆盖。可运行 `python -m pytest -q tests/test_lyra_tree_sitter_baseline.py --import-mode=importlib` 单独验证。

只使用 SourceTools 检查 Lyra 时，可运行 `python -m unittest tests.test_lyra_sourcetools_regressions -q`，覆盖宏文本、构造初始化列表、接收者及限定名导航。2026-09-10 全量复查覆盖 383 组显式文件、707 个文件、3,395 处函数定义和 96 个原生 GameplayTag 定义；复用每组 SourceTools 上下文，遍历类型与函数的全部公开选择名，4,672 份公开结果通过 Schema、函数选择和引用位置一致性检查。证据不足或条件声明冲突的调用继续保留 `unknown`。

函数外部符号按源码位置排序（包括同一行）；调用模板实参中 AST 标记为类型的项保留为完整类型表达式，数字和表达式实参不作为类型输出。结果仍是语法候选，不执行模板语义绑定。

## 安装

需要 Python 3.10 或更高版本：

```bash
python -m pip install -r requirements.txt
```

安装和运行必须使用同一个 Python 环境。本地 UE C++ 语法包当前为 `0.1.1`；前端会检查所需 AST 节点，遇到旧版不兼容语法包时返回明确错误，避免静默漏掉 UE 宏参数或声明。更新子模块后，在实际运行环境中执行 `python -m pip install --force-reinstall ./parsers/tree-sitter-ue-cpp`。

开发和测试还需要：

```bash
python -m pip install -r requirements-dev.txt
```

## 快速开始

先查看当前工具清单：

```bash
python sourcetools/ue_list_tools.py
```

查找工程后，必须从结果中明确选择一个 `.uproject`：

```bash
python sourcetools/ue_find_projects.py --search-root D:/Projects
```

检查一个明确选择的 C++ 文件或同名 `.cpp`/`.h` 文件对：

```bash
python sourcetools/ue_list_cxx_types.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp D:/Projects/MyGame/Source/MyGame/Public/MyActor.h
python sourcetools/ue_list_cxx_functions.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp D:/Projects/MyGame/Source/MyGame/Public/MyActor.h
python sourcetools/ue_inspect_cxx_type.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp D:/Projects/MyGame/Source/MyGame/Public/MyActor.h --type AMyActor
python sourcetools/ue_inspect_cxx_function.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp D:/Projects/MyGame/Source/MyGame/Public/MyActor.h --function BeginPlay
```

`ue_list_cxx_types.py` 会把 Engine 5.8 的原生 GameplayTag 声明/定义宏投影为 `FNativeGameplayTag` 变量事实；extern 声明不进入最终定义列表，static 定义保留内部 linkage。

`ue_list_cxx_types.py` 和 `ue_inspect_cxx_function.py` 支持试验性的 `--view behavior`（业务）和 `--view structure`（结构），默认 `--view full` 保持原有输出。规则集中在 `ue_cpp_conventions.py`，按已有 AST 类型与方法事实匹配。规则 v3 对已知容器的增删、清空和重置优先展开，即使返回值未被使用；容量预留 `Reserve` 仍折叠。未使用结果的普通容器查询、智能指针取值，以及文本包装和日志统计默认隐藏；返回表达式被条件、赋值、参数、接收者或 return 承接时，容器查询和指针取值优先展开。这里只做局部语法判断，尚不区分临时容器与业务集合的完整数据流。普通业务同名方法、类型不明的调用和全部委托记录保留。函数中的普通类型引用在业务视图折叠、结构视图展开，模板类型表达式完整保留。类型清单保留全部定义，仅通过 `view.sections` 指示各类别的展开优先级；此处不新增继承或跨文件关系推断。

`UE_LOG`、`UE_CLOG` 格式及输出参数中的辅助调用在 `log_groups` 中按日志位置归组折叠；函数层的普通 `symbol_groups` 保留日志外同名调用、已识别的容器状态写入和显式 `focus`。`UE_CLOG` 条件及 Lambda 内部操作不归入外层日志。折叠未知参数调用不表示已证明它没有副作用；完整调用表达式仍可通过 `--include-syntax-flow` 查看。符号总数由普通组计数、日志子组计数及隐藏计数共同组成。Scope 关系项通过 `context` 关联日志位置，保留逐条关系和跨视图证据入口。

优先级函数结果的 `statement_summary` 汇总前端识别的初始化、赋值、更新、条件和返回证据；`--include-syntax-flow` 返回 `statements` 的表达式、目标、值、位置及函数/Lambda 作用域。Scope 函数层提供同一汇总，证据层提供具体表达式与原文。只检查函数执行区域，不把签名默认参数等当作函数体行为；C++ 声明歧义仍需原文核对，不以零调用或零语句计数断言“无信息”。导航提示也支持 `kind: statement`，按完整表达式匹配，生成 `include_syntax_flow: true` 查询，沿用源码指纹、唯一定义和缺证据降级检查。

函数视图以 `symbol_groups` 替代 `external_symbols`：`count` 与 `lines` 保留出现次数和每次行号，文件类别统一存放在匹配项的 `unit`；不同接收者和 Lambda 分开分组。`display` 省略表示展开，`execution_scope` 省略表示外层函数；命中规则保留 `rule`，隐藏原因和数量汇总在 `view_summary.hidden_by_rule`。这些分组只用于展示，不代表等价调用、执行次数或语义关系。`--focus NAME` 可重复指定精确的符号、方法或类型名称，恢复并展开关注项；它只用于业务或结构视图。`--include-syntax-flow` 在这两种视图中额外保留全部调用的表达式、参数与位置，包括隐藏项，便于核对。

规则 v2 的 `count` 和 `source_count` 按内部逐位置事实计数；同一行出现两次相同调用时，可以分别判断是否使用了结果，行号也可能重复。默认 full 视图的 `external_symbols` 继续维持同名同一行合并的旧契约，因此不能直接把两种视图的记录数量作为等价校验。

例如检查 Lyra 的容器查找与指针取值，可在仓库根目录运行：

```bash
python sourcetools/ue_inspect_cxx_function.py --source LyraStarterGame/Plugins/AsyncMixin/Source/Private/AsyncMixin.cpp LyraStarterGame/Plugins/AsyncMixin/Source/Public/AsyncMixin.h --function FAsyncMixin::GetLoadingState --view behavior
```

追加 `--focus TMap --focus Get` 可恢复这些通用操作；切换到 `--view full` 时去掉 `--focus`。

2026-09-11 仅通过 SourceTools 对 Lyra 的 383 组、707 个文件复测：默认输出与修改前一致；业务视图将 20,024 条符号记录整理为 14,719 组（展示条目减少 26.5%），隐藏 2,765 条低优先级记录，546 条委托记录原样保留。106 项测试通过，两种视图的 6,640 份函数结果通过最终 Schema 校验，并与 9 次独立 CLI 调用抽查对照。优先级视图新增接收者与规则信息，全量紧凑 JSON 体积仍增加约 1.5%；此版主要改善阅读密度，不保证整体字节数减少。

`ue_inspect_cxx_scope.py` 试验性地提供系统、类型、函数和证据四级导航。职责目录使用 `version: 1`、`id`、`name`、`description` 和 `units`；每个单元包含唯一 `id`、项目根目录内的一至两个显式 `sources`，以及可选的 `roles`（精确类型名到职责标签数组）、`entry_points`（精确函数限定名数组）。标签属于人工配置；工具验证对应定义存在，拒绝重复文件、越界路径及未知字段，未分类类型仍保留。职责目录不会产生跨文件语义绑定。

Lyra 装备系统试点包含 6 组、12 个文件，可直接运行：

```bash
python sourcetools/ue_inspect_cxx_scope.py --project LyraStarterGame/LyraStarterGame.uproject --profile sourcetools/profiles/lyra_equipment.json
```

默认返回 `--level system --view behavior`。在相同命令后追加 `--level type --select <类型id>` 或 `--level function --select <函数id>` 展开对应项；`--level evidence --select <关系id或函数id>` 返回完整证据，恢复隐藏项。关系项的 `source` 是来源函数标识（Include 使用配置单元标识），不等于已绑定的目标。不同接收者、Lambda、条件定义与文件组分别保留；类外方法按限定所属名导航，不消除条件分支歧义。

`--view structure` 优先展示类型，`--focus NAME` 可重复指定精确关注项。`--limit` 为每页 1 至 100 项，默认 20；使用 `page.next_offset` 继续翻页，`page.total` 是当前层级可返回的总项数。`view: full` 展开当前层级全部符号组，仍然分页；补充调用和函数原文在证据层返回。`summary.facts.call` 专指未进入符号清单的补充调用，其余调用随符号证据返回。标识绑定 `snapshot`，源码或配置改变后需重新获取。单次查询内每组只加载一次，复用 `SourceScope` 对象可复用上下文；独立 CLI 调用会重新加载所选范围。

新入口使用内部逐位置符号事实，保留旧 `external_symbols` 同一行合并的出现位置；旧 CLI 输出维持原契约。2026-09-12 装备试点覆盖 13 个类型、60 处函数定义，旧的 58 份函数查询及类型/函数清单保持一致，772 份分层结果通过 Schema 与证据检查，四级独立 CLI 对照一致。118 项相关测试通过，包含 Lyra AsyncMixin 委托证据补测。默认概览 6,707 字节，对比同范围完整类型清单、函数清单及函数详情的 124,602 字节减少 94.6%；概览→管理类型→EquipItem→AddEntry 调用证据的四次查询共 21,980 字节，减少 82.4%。这是该试点的紧凑 JSON 字节比较，不代表全 Lyra 或执行耗时；已知具体函数时仍可直接使用单函数工具（EquipItem 的旧函数输出 1,607 字节，新函数层含导航信息为 3,327 字节）。

首次接入时也可导出可复用的检索地图，后续按地图定位，直接调用旧工具。试验入口位于 `sourcetools/lyra/`，复用 `SourceScope.navigation_map()`；根目录核心 CLI 清单保持 16 项：

```bash
python sourcetools/lyra/export_navigation_map.py --project LyraStarterGame/LyraStarterGame.uproject --profile sourcetools/profiles/lyra_equipment.json --output lyra-equipment-map.json
```

基础地图保存显式文件组、类型名称、配置职责及入口名称；配置导航提示时，还保存所要求的局部证据。将 `units[].sources` 按地图中 `project` 的父目录还原为 `--source`；业务查询使用 `entry_points[].name` 调用 `ue_inspect_cxx_function.py --function`，结构查询使用类/结构体名称调用 `ue_inspect_cxx_type.py --type`。没有配置入口或导航提示时，先用 `ue_list_cxx_functions.py` 获取该文件组的当前名称；枚举仍通过 `ue_list_cxx_types.py` 查看。需要调用实参时使用函数工具的 `--view behavior --include-syntax-flow`，低优先级调用仍在语法详情保留。`definition_count` 提示同名定义的数量，查询时保留全部匹配。定位选择由使用者完成，试验未实现自然语言自动路由或变更监控；`snapshot` 只记录建图来源。普通实现修改由旧工具读取最新事实；文件迁移、入口改名或职责调整后需修订配置并重新导出。

准确性试点配置为 `sourcetools/profiles/lyra_reviewed_navigation.json`，可替换上述导出命令中的 `--profile`。每组可选 `navigation` 保存问题意图、检索目的、精确目标、角色、判断理由及要求核对的调用名或成员名。角色区分 `system_entry`（系统/生命周期入口）、`internal_function`（内部函数）和 `type_structure`（类型结构）；这些是人工阅读证据后的解释，不自动等同于 public 函数或运行时关系。类型提示仅为 class/struct/union 生成旧检查工具的查询。

导出时，`navigation[].definitions` 保存各定义的位置及匹配证据，调用证据包含表达式、参数、列号及 Lambda 作用域；`query` 给出旧工具、选择名和业务/结构视图的精确 `focus`。`reviewed_sources` 必须保存全部所选文件的 SHA-256 文本指纹；指纹与证据来自解析时同一次读取，文本按 UTF-8 解码、去 BOM 并统一换行。`review_status: current` 仅表示指纹一致，不表示已审查该文件的全部职责。只有指纹一致、定义唯一、要求的证据齐全且所选文件没有语法解析告警时，提示才为 `reviewed`；过期、缺证据或同名歧义保留为 `candidate`，找不到可检查目标为 `unresolved` 且不生成查询。重新建图不会自动更新人工复核指纹；旧地图也不会自行监测源码变化。

基准 `tests/fixtures/lyra_retrieval_accuracy.json` 固定 21 个开发问题和 6 个保留问题。开发问题形成带证据的配置；保留问题不进入该配置，用来检查通用过滤、类型成员、委托和 Lambda 证据。可运行 `python -m unittest tests.test_lyra_retrieval_accuracy -v`，通过 SourceTools API 与独立旧 CLI 验证。本阶段优先保证证据准确性，数据库、增删改查及性能优化尚未实施；预选问题的通过数量不代表自然语言检索准确率。

2026-09-13 准确性复核覆盖 21 组、42 个文件、61 处类型和 405 处函数定义：21 个导航提示通过当前证据检查，分为 5 个入口、9 个内部函数和 7 个类型结构提示。27 个问题分别通过独立旧 CLI 核对；两种优先级视图保留预期关键证据，所选范围的 375 份默认 full 查询与历史结果逐份一致。126 项相关测试通过，包含同一行混合调用、源码读取期间变化、语法恢复告警、过期配置及同名歧义。产物见 [本轮地图](Saved/SourceTools/lyra-accuracy-20260913/navigation-map.json) 和 [验证汇总](Saved/SourceTools/lyra-accuracy-20260913/verification-summary.json)。本轮没有重新扫描全部 707 个文件，也未把未覆盖的职责自动标为已确认。

同日追加抽样避开上述准确性与装备配置的文件，以固定种子 `2026091302` 选择 8 组随机样本及 4 组针对性样本：覆盖 10 个模块、22 个文件，检查 22 个函数选择名和 8 个类型。30 个样本通过独立旧 CLI 与人工选择的源码证据核对；135 份 full 查询、24 份类型/函数清单与历史结果一致，含诊断对照共 33 次独立 CLI、259 份 Schema 校验。两个 `AddEntry` 重载、Lambda 内成员函数指针调用和候选委托均保留各自边界。

抽样发现三项改进点：决定待激活能力集合的 `AddUnique` 仍按普通容器写入折叠；日志参数中的 `GetName()` 在日志隐藏后仍展开；目录分区把设置变更跟踪器的头源文件拆开，补入一个明确匹配头文件后，`DirtySettings.Add` 才从 unknown 变为已知 TMap 调用。显式 focus 能展开这些写入，但通用优先级与首轮文件配对仍需改进。零普通调用的构造函数也可能包含有效默认值，不能按调用数判为无信息。此轮仅测试和记录，未改工具规则或已有配置；结果与复现输入见 [追加抽样汇总](Saved/SourceTools/lyra-sampling-20260913/summary.json)。

**准确性完善进度（2026-09-14）**

目标是让首次项目规划与后续旧工具查询准确保留业务关系所需的源码证据。Lyra 源码继续仅通过 SourceTools 读取；数据库、增删改查和性能优化后置。已有源码指纹、过期降级、同名定义分离及候选委托机制继续沿用。

| 顺序 | 优先级 | 内容 | 本轮结果 |
|---|---|---|---|
| 1 | P0 | 头源配对后再组织目录 | 保留同目录及 Public/Private 镜像规则，为未配对头文件补充模块内唯一同名候选，新增配对标记 `method: unique-module-basename`；不跨模块，歧义保留。设置注册表与变更跟踪器共补回 2 对。 |
| 2 | P0 | 业务写入优先级 | `AbilitiesToActivate.AddUnique` 与 `DirtySettings.Add` 无需 focus 即展开；采用保守的已知状态写入规则，容量预留仍折叠。 |
| 3 | P1 | 日志上下文降噪 | 能力取消函数两处 `GetName` 分别归入对应日志；显式关注可单独展开。日志条件、已知容器写入、Lambda 作用域及旧委托事实保持。 |
| 4 | P1 | 非调用导航证据 | `FAimAssistFilter` 的 7 项布尔初始化可逐项定位并参与导航复核；赋值、条件、更新和返回也提供语法证据，不解释为已证明的运行时关系。 |
| 5 | P1 | 扩大职责复核 | 新配置覆盖 10 个模块、12 组、23 个文件，30 个问题均可定位：29 个已复核、1 个 `AddEntry` 同名重载候选。额外 4 个保留样本不进入导航配置，检查通用规则。全量职责标注仍未完成。 |
| 贯穿 | P1 | 长期回归 | 固化 30 个抽样问题及 4 个新保留问题，检查状态写入、日志、非调用信息、重载、Lambda、类型成员、Schema 和独立旧 CLI；另按相同旧输入检查 full 与基础清单。 |

追加配置为 `sourcetools/profiles/lyra_sampling_reviewed.json`，可使用同一地图导出入口。运行 `python -m unittest tests.test_lyra_retrieval_sampling -v` 验证 30 个抽样与 4 个新增保留问题；原有 21 个导航提示和 6 个保留问题继续由 `tests.test_lyra_retrieval_accuracy` 验证。新样本分别检查设置重建、UI 扩展映射增删、捕获目标格式和相机输出赋值，冻结后未据此调整规则。抽样通过数量不作为自然语言检索准确率。

本轮 145 项相关测试通过，包含 61 个问题的独立旧 CLI 校验（原有 27 个、追加 30 个、新保留 4 个）。在相同旧输入的 33 组、64 个文件上，510 份默认 full 查询与 66 份类型/函数清单逐份一致；兼容检查及地图、模块清单共通过 597 份 Schema 校验。全模块配对清单仍覆盖 19 个模块目录项、707 个文件且无遗漏、无重复，输入组从 383 组变为 381 组；本轮未重跑全部文件的 AST 建图，也未覆盖全部职责。产物见 [当前抽样地图](Saved/SourceTools/lyra-priority-v3-20260914/reviewed-map.json)、[模块输入规划](Saved/SourceTools/lyra-priority-v3-20260914/module-input-plan.json) 与 [验证汇总](Saved/SourceTools/lyra-priority-v3-20260914/verification-summary.json)。历史全量地图仍是原日期快照，需要重建后才会包含新的配对与职责配置。

2026-09-12 装备试点地图为 4,140 字节。装备、卸装、快捷栏切换、装备配置四类预选问题各调用一次旧工具；装备 Actor 生成问题先列函数再检查，共六次独立调用，结果通过 Schema 校验。首次建图实测 19.6 秒，后续每次调用 2.4–2.6 秒，六次合计 14.8 秒；这是本机单轮测量，不含人工选择时间。地图读取一次加六份结果共 27,472 字节。以获取 EquipItem 的 AddEntry 调用实参为例，同一源码快照下，地图加旧查询共 6,992 字节，比此前四级路径的 21,980 字节减少 68.2%；地图已经在上下文中时只新增 2,852 字节。所有字节数按 UTF-8 紧凑 JSON 计算。29 项相关测试通过，覆盖地图复用、源码变更、入口失效、同名歧义及上述真实查询；该结果仅代表装备试点。

2026-09-12 全量导航试验复用现有 SourceTools，覆盖 707 个文件、383 组输入、640 处类型定义和 3,395 处函数定义，文件无遗漏、无重复。按实际 Build.cs 边界及首层源码目录组织为 19 个模块目录项、61 张分区地图；其中 18 个模块目录项有源码，两处同名 `CommonStartupLoadingScreen.Build.cs` 按路径分别保留，并报告警告。项目入口索引为 5,146 字节，最大单张地图为 13,695 字节；全部索引和地图合计 232,991 字节，日常按需读取。3,320 个旧函数查询与历史结果逐份一致，模块清单、地图、类型/函数清单、函数结果及独立 CLI 共 4,200 份结果通过 Schema 校验。

跨全部 18 个有源码的模块选取 21 个问题（14 个函数问题、7 个结构问题），从保存的目录与地图定位，执行 34 次独立旧 CLI 调用，均取得预期类型或函数及其源码证据。单次实测 2.4–3.7 秒，调用合计 85.1 秒；结果共 343,708 字节，加上本批问题实际使用且各读取一次的导航数据，共 438,854 字节。定位仍由使用者选择，不能把这些预选问题当作自动问答准确率。

本轮也暴露了规模限制：仅沿用装备配置的 12 个类型职责标签和 4 处入口，其余 628 个类型未分类；14 个函数问题只有 1 个直接命中配置入口，另 13 个需要先列函数，最大函数清单达 72,154 字节。4 路并发的建图与全量对照检查共耗时约 41.8 分钟，包含完整上下文解析、地图导出及回归校验，尚未分离纯建图成本。当前全量流程验证了文件与类型导航，完整职责规划、入口选择和首轮性能仍需改进。本机产物保存在 [全量目录](Saved/SourceTools/lyra-full-navigation-20260912/index.json) 与 [验证汇总](Saved/SourceTools/lyra-full-navigation-20260912/summary.json)，`Saved/` 为本地生成数据，不纳入 Git。

`ue_list_cxx_types.py` 只输出所给文件中类、结构体（含 union）、枚举、自由函数、全局变量及 `#define` 宏定义的基础清单。保留名称、限定名、所属作用域、位置、函数签名、变量类型和附带的 UE 宏；不展开继承、成员、枚举项或接口推断。类型的 `evidence.line` 从附带的 `UCLASS`、`USTRUCT`、`UENUM` 或 `UINTERFACE` 宏起始行计算，`end_line` 仍为类型结束行；无附带宏时从类型声明行开始。独立宏仅返回名称、参数及位置，`parameters: null` 表示对象宏，`[]` 表示无参数函数宏，不输出宏体。前向声明、extern 声明和函数原型仍不进入清单。

声明中的每个变量或函数分别分类：保留内联类型后附带的变量、函数指针变量及带初始化的 `extern` 定义；同一条声明混写变量和函数时也分别处理。

局部类型使用包含外层函数名的词法路径导航，例如 `AWorker::Run::Local`；它是工具的选择名，不是可直接用于 C++ 的限定表达式。同名定义仍可返回多个匹配。内联友元函数归入命名空间自由函数；局部类型的成员函数体独立扫描，不计入外层函数或 Lambda 的调用。前端已有的 UE 测试类与 Spec 节点也进入类型清单，测试方法按 `TEST_METHOD` 的名称参数、`Setup`、`TearDown` 输出，保留原宏签名作为源码证据；不展开宏生成的额外成员。位置的结束行均为包含式行号，单行证据可省略 `end_line`。

`ue_inspect_cxx_type.py --type <qualified_name>` 精确选择类或结构体，返回 `matches`，包含继承、直接成员 `member_anchors`、成员函数定义 `member_functions` 和接口候选原因。嵌套类型须单独选择；类外实现只来自显式传入的文件，找不到类型返回退出码 1。成员覆盖类内定义、构造函数、模板和条件编译中的成员；类外静态成员变量定义仍在基础清单保留完整限定名。旧清单的 `member_anchors`、`base_types` 和顶层 `member_functions`、`interface_candidates` 已迁往类型详情，`enumerators` 及空的 `unresolved_declarations` 已移除。

`ue_list_cxx_functions.py` 列出所选文件的全部函数定义，包括所选文件中没有所属类定义的成员实现，保留重载、条件分支、签名、位置及与函数检查共用的 `function_id`。通过清单中的 `qualified_name` 选择函数；`source_qualified_name` 保留源码写法。仅在所选文件有类型和成员声明证据时归一 `C::C::Method`，原写法仍可作为选择名。没有定义时返回空数组和退出码 0。

宏、签名和调用参数的显示文本使用 AST 范围格式化，保留字符串、原始字符串、字符常量及注释内部空白；UE 宏识别使用结构化名称与参数。函数扫描覆盖函数体、构造初始化列表及函数 try/catch，其中的 Lambda 单独标记；默认参数、`noexcept` 和函数声明区域不计入调用。

普通调用、取地址和委托复用本地名称查询。成员归属结合调用点词法绑定、`this`、成员声明和所选文件全局变量，处理命名空间及遮蔽；本地可见类型的构造表达式归入 `type`。冲突声明、`auto` 和 `decltype(auto)` 不作为已解析的所属类型。通过 `.*`、`->*` 发起的成员函数指针调用保留原始表达式，目标无法确定时输出 `unknown`，不生成虚构的具名成员方法。

取地址表达式依据所选文件中的函数、变量和成员声明分类，并考虑参数、局部变量、Lambda 参数及范围循环变量的遮蔽；有函数声明证据才输出 `function_address`，已知数据地址不进入该类别，无法确认的地址保留原表达式并输出 `unknown`。已识别委托操作的指定回调参数继续由委托分析生成 `callback_target`。C++ 的 `const_cast`、`static_cast`、`reinterpret_cast` 和 `dynamic_cast` 不进入调用列表或外部函数候选，但保留目标类型及内部实际调用；基本类型的函数式转换（例如 `int(Value)`）同样不作为调用，内部实际调用仍保留。普通模板调用（例如 UE `Cast<T>`）仍按调用处理；缺少类型证据的 `(UnknownName)(Value)` 无法仅凭语法区分转换与调用，继续保留未知调用候选。

`function_id` 标识所选文件中的一处具体定义，格式在原签名后增加 `|unit:line:column`。条件编译分支、头源文件和同一行上的定义各自保存符号、调用及委托结果；内部函数签名身份仍用于实体描述。它不是跨版本或跨文件选择的稳定实体 ID；文本保真及限定名归一会修正 ID，依赖旧输出的缓存需重新生成，源码位置变化也会改变该标识。

共享前端的离线消息扫描同样按具体函数定义读取引用，保留条件分支中同名函数各自的消息调用。

委托分析使用唯一的 `delegate_contract_revision: 2` 契约：`delegate_operations` 区分创建、绑定、添加、解除绑定、移除、清空、执行、广播和查询；以 `subject` 表达被操作的成员、参数、局部变量或返回值，旧 `event` 字段已移除。`delegate_type` 来自所选文件的声明宏、显式模板或可解析别名；`identified` 表示类型及 API 形状有依据，`candidate` 保留无法确认的调用和原因，不代表真实委托关系。未知类型不会生成虚构的限定成员名。

`callback` 按 API 参数位置识别函数、反射函数名、Lambda 或已有委托值，`callback_target` 从同一分析结果派生。参数之间的注释不占用参数位置。`arguments` 保留对象、payload、执行参数和移除条件，`result` 记录直接承接的委托值或句柄，包括构造初始化列表、局部直接初始化及括号包裹的赋值；多参数初始化不推断承接对象，嵌套创建通过 `source_operation` 关联。`execution_scope` 区分外层函数与 Lambda 函数体。规则基于 UE 5.8；不读取传递头文件，不追踪变量赋值后的绑定流、不证明对象存活或回调线程安全。此次为原位契约替换，没有旧版开关或双写字段。

`ue_inspect_module_rules.py` 只提取可直接读取的模块依赖字面量；`Add(ModuleName)`、`AddRange(ModuleNames)` 等变量或计算表达式保留为未解析证据并报告警告，空字面数组仍可明确解析为空。

所有核心 CLI 都把结果写到标准输出，并包含 `schema_version`、领域事实、`validation` 和 `limits`。静态结果是源码证据，不等同于 UBT、UHT、编译器、Editor 或运行时结论。

## 文档

- [架构](docs/ARCHITECTURE.md)
- [工具清单](docs/TOOLS.md)
- [开发约定](docs/DEVELOPMENT.md)
- [测试与验证](docs/TESTING.md)

各子组件的使用方式见 [Editor 工具](edittools/README.md)、[文件图谱](information_pool/README.md)、[连接池](mcp_connection_pool/README.md) 和 [本地浏览器](show/README.md)。

核心测试可直接从仓库根目录运行：`python -m unittest discover -s tests -v`。其余组件的验证命令见 [测试与验证](docs/TESTING.md)。

## 许可证

仓库尚未声明项目级许可证。第三方许可信息见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 `LICENSES/`。
