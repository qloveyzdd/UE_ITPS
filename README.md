# UE-ITPS

面向 Unreal Engine 项目的可验证功能复用、工程知识管理与增量信任编程系统。

工具第一阶段已经完成，并作为 **v1** 发布：仓库提供七个确定性、只读的 UE 项目检查 CLI，以及负责最小工具路由和结果解释的 `ue-project-inspector` Skill。v2 在不修改这些项目级 Schema 的前提下新增五个源码聚焦工具，用于逐层读取单个 `.uplugin`、插件模块导航、单个 Build.cs、单个 Target.cs 和单个模块入口。里程碑版本与各工具独立的 Schema 版本分开管理。

当前仍不开发具体玩法或信任系统。UE 5.6.1 与 Epic 可追溯 Lyra 快照作为 v1 的首个回归对象，用于验证工程组成、项目入口、Engine、Module、Target、直接 Plugin 引用和项目根目录分类。

当前入口：

- [基线与复现状态](.planning/codebase/BASELINE.md)
- [工程栈与依赖全景](.planning/codebase/STACK.md)
- [目录结构与职责边界](.planning/codebase/STRUCTURE.md)
- [Lyra 顶层架构与启动主链](.planning/codebase/ARCHITECTURE.md)
- [启动、Experience 与玩家初始化管线](.planning/codebase/PIPELINES.md)
- [前端、会话与地图旅行管线](.planning/codebase/TRAVEL.md)
- [网络模式、旅行存续与失败边界](.planning/codebase/NETWORK-MODES.md)
- [L0/L1 运行证据捕获规范](.planning/codebase/RUNTIME-EVIDENCE.md)
- [最小运行边界](.planning/codebase/MINIMAL-RUNTIME.md)

当前已完成 UE 5.6.1 本机编译，冻结 9,656 个权威文件的 SHA-256 清单，并归档 Engine/Lyra 来源、Target、Module、Plugin、目录职责、核心 Asset Registry 关系，以及 PIE 启动、Frontend、Session/Travel、四种网络模式、Hard/Seamless 对象存续、失败恢复、Experience、PlayerState、Pawn、ASC、InitState 和输入的静态主链。十一个检查 CLI 的公共契约、严格校验、双语帮助、UTF-8 输出和单元测试已经稳定；原始日志不可覆盖复制与 SHA-256 manifest 工具也已就绪。

当前本地 Lyra 工程壳可追溯到 Epic UnrealEngine 历史提交，但不是 `5.6.1-release` 标签的逐字节副本。L0 曾在本机观察通过，但原始运行日志已被 UE 日志轮转清理，必须重跑并受控留存后才能恢复为可审计权威证据；完整边界见基线文档。当前仍不执行 L1，也不修改或删减 Lyra。

## 仓库结构

```text
UE_ITPS/
├─ tools/                         UE 项目检查、基线指纹与运行证据工具
├─ docs/                          面向维护者的程序说明
├─ .agents/skills/                仓库级 Codex Skill
├─ .planning/codebase/            Lyra 架构研究归档
├─ .planning/evidence/            指纹、Registry 查询与运行证据
└─ LyraStarterGame/               当前 UE 5.6.1 Lyra 基准项目
```

工具的实现边界、数据流、已知缺口和优化建议见 [程序设计说明](docs/PROGRAM-DESIGN.md)。

## 在 Codex 中使用

仓库包含 `ue-project-inspector` Skill。打开本仓库后，可以显式调用：

```text
$ue-project-inspector 找出当前仓库的 .uproject，只读取项目声明。
```

```text
$ue-project-inspector 识别当前 UE 项目的精确引擎版本并给出证据文件。
```

```text
$ue-project-inspector 读取当前 .uproject 的紧凑声明，列出 Plugin 的简单启用、简单禁用和扩展声明。
```

```text
$ue-project-inspector 检查项目 Module 结构，不扫描插件。
```

```text
$ue-project-inspector 依次检查当前项目的描述符、Engine、Module、Target、Plugin 和根目录，并汇总结果。
```

Skill 默认选择能回答问题的最小工具。只有明确要求全部类别时，才依次运行相关聚焦工具；各工具保留独立 Schema、验证结果和解释边界。

## 统一 CLI 输出契约

十一个只读检查 CLI 的正常扫描结果使用同一顶层顺序：

```json
{
  "schema_version": "ue-itps.<module>.vN",
  "...模块确认事实...": "...",
  "validation": {
    "status": "ok | warning | error",
    "problem_count": 0,
    "problems": []
  },
  "limits": {
    "responsibility": "该模块负责什么",
    "boundaries": ["该模块不负责或不能证明什么"]
  }
}
```

每个工具维护独立 Schema；模块入口工具的 v7 是面向状态结论的破坏性契约，其余项目级 Schema 不受影响：

| 工具 | Schema |
|---|---|
| `ue_find_projects.py` | `ue-itps.project-discovery.v1` |
| `ue_read_project_descriptor.py` | `ue-itps.project-descriptor.v1` |
| `ue_resolve_engine.py` | `ue-itps.engine-resolution.v1` |
| `ue_inspect_modules.py` | `ue-itps.project-modules.v1` |
| `ue_inspect_targets.py` | `ue-itps.project-targets.v1` |
| `ue_resolve_plugins.py` | `ue-itps.project-plugin-references.v1` |
| `ue_classify_project_paths.py` | `ue-itps.project-paths.v1` |
| `ue_read_plugin_descriptor.py` | `ue-itps.plugin-descriptor.v2` |
| `ue_inspect_module_rules.py` | `ue-itps.module-rule-relations.v1` |
| `ue_inspect_target_rules.py` | `ue-itps.target-rule-relations.v1` |
| `ue_inspect_module_entry.py` | `ue-itps.module-entry-state.v12` |

`validation` 只放该模块检测到的问题；已确认事实保留在中间的模块字段中。`limits` 固定为最后一个字段，供用户和大语言模型判断职责与解释边界。标准输出和标准错误固定使用 UTF-8。

所有命令的 `--help` 都提供中英文双语说明，例如：

```powershell
python tools\ue_resolve_engine.py --help
```

## 直接运行 UE 项目检查工具

以下命令从仓库根目录执行。项目路径示例：

```powershell
$Project = "E:\UE_ITPS\LyraStarterGame\LyraStarterGame.uproject"
```

### 1. 发现 `.uproject`

```powershell
python tools\ue_find_projects.py --search-root E:\UE_ITPS
```

只定位候选项目；存在多个项目时返回 `ambiguous`，不会自行选择。

### 2. 读取 `.uproject` 显式声明

```powershell
python tools\ue_read_project_descriptor.py --project $Project
```

输出 `FileVersion`、`EngineAssociation`、Module 名称列表、Plugin 简单启用/禁用列表、扩展声明索引和 Additional 目录；不重复完整 `Modules`/`Plugins`，不计算描述符哈希，也不搜索 Engine、Module 文件或插件目录。

### 3. 解析真实 Engine 身份

```powershell
python tools\ue_resolve_engine.py --project $Project
```

将 `EngineAssociation` 解析到 Engine 根目录，并读取 `Engine/Build/Build.version`。当前基线应解析为 UE 5.6.1。

### 4. 检查项目 Module

```powershell
python tools\ue_inspect_modules.py --project $Project
```

对账 `.uproject` Module 与项目 `*.Build.cs`；`reconciled_module_count/items` 仅包含一一匹配成功的 Module，缺失、歧义、未声明或重复声明进入 `validation`，并记录 `IMPLEMENT_*_MODULE` 入口证据。

### 5. 发现项目 Target

```powershell
python tools\ue_inspect_targets.py --project $Project
```

发现 `Source/**/*.Target.cs`，在每个结果上标记是否位于 `Source` 根目录，并据此给出原生项目证据分类。Target 不由 `.uproject` 声明。

位置校验规则：`Source` 下没有 Target 为错误；Target 只位于子目录为警告；根目录与子目录同时存在 Target 为另一类警告；Target 只位于 `Source` 根目录为正常。

### 6. 定位直接 Plugin 引用

Plugin 工具会根据 `.uproject` 的 `EngineAssociation` 自动解析 Engine 根目录：

```powershell
python tools\ue_resolve_plugins.py `
  --project $Project `
  --operation scan `
  --platform Win64 `
  --target-type Editor
```

当自动解析存在歧义、注册表不可用或需要指定自定义 Engine 时，可额外传入 `--engine-root <path>` 覆盖自动结果。

Plugin v1 输出在 `path_roots` 中只记录一次项目和 Engine 绝对根路径，逐项 `descriptor` 使用对应根的相对路径。正常项从 `item_defaults` 继承省略的默认状态；未定位、候选冲突或关联诊断的问题项保留全部建模字段。工具只定位 `.uplugin` 路径，不读取或计算 Plugin 描述符哈希。

当前只解析 `.uproject` 的直接 Plugin 引用，不计算 `.uplugin` 传递依赖和默认启用插件闭包。

### 7. 分类项目根目录

```powershell
python tools\ue_classify_project_paths.py --project $Project
```

只根据 `.uproject` 的位置和项目根文件系统状态输出目录事实：

- `project_root`：由所选 `.uproject` 父目录唯一确定的绝对项目根，只记录一次。
- `project_descriptor`：所选 `.uproject` 的项目相对路径与文件系统状态。
- `project_directories`：`Source`、`Config`、`Content`、`Plugins`、`Build`、`Platforms` 的约定角色和实际类型；`actual_type: missing` 表示路径不存在。
- `build_and_ide_paths`：`Binaries`、`Intermediate` 和 `.sln` 的约定位置；该分组不判断来源、必要性、删除安全性或可重建性。
- `cache_and_local_state_paths`：`DerivedDataCache`、`Saved`、`.vs` 和 `.idea`。
- `unclassified_root_directories`：不能安全判断为可删除、必须人工复核的其他项目根目录。

除顶层 `project_root` 外，路径项和诊断只保存 `project_relative_path`，不重复绝对路径。工具读取 `.uproject` 的显式顶层声明，但不读取目录内容、Module/Plugin 文件或资产。当 `Modules` 非空、没有声明 `AdditionalRootDirectories` 且 `Source` 缺失时，`validation` 报告阻断错误；路径项不增加额外的必要性字段。没有 Module 声明不能反向证明 `Source` 不需要。工具也不判断源码权威、自包含、删除安全性或可重建性。

## 逐层读取插件与源码事实

源码工具不会自动附加到 `.uproject` 结果。调用方先用项目级工具定位对象，再显式选择一个文件继续深入。例如检查 `CommonLoadingScreen`：

```powershell
$Plugin = "E:\UE_ITPS\LyraStarterGame\Plugins\CommonLoadingScreen\CommonLoadingScreen.uplugin"

python tools\ue_read_plugin_descriptor.py --plugin $Plugin
```

该命令读取 `.uplugin` 的字段、Module 声明和直接 Plugin 依赖，按 UE 5.6.1 枚举与字段类型进行校验，并在插件 `Source`、`Platforms` 下递归对账 Module 对应的 Build.cs。Build.cs 通过文件名匹配，`Source/<Name>/<Name>.Build.cs` 只标记为传统位置，不是硬性要求；工具不遍历依赖插件。

选择一个 Build.cs 后，分别读取规则和模块入口：

```powershell
$Rules = "E:\UE_ITPS\LyraStarterGame\Plugins\CommonLoadingScreen\Source\CommonLoadingScreen\CommonLoadingScreen.Build.cs"

python tools\ue_inspect_module_rules.py --rules $Rules
python tools\ue_inspect_module_entry.py --rules $Rules
```

Build.cs 工具以构造函数和可达的同文件辅助方法为内部扫描边界，只公开已声明的 ModuleRules 设置变更、引用对象、生效方式和源码行。明确的字符串或符号进入 `declared_mutations`，未知设置进入 `unclassified_mutations`，无法确认效果的外部或继承方法进入 `unresolved_effect_calls`；空集合操作被忽略，复杂表达式保留原文而不展开为 AST。`operation` 使用 `set/add/remove/increment/decrement` 等语义操作，不暴露 `Add` 与 `AddRange` 的 API 差异。`applicability.kind` 区分 `direct` 与 `conditional`；条件对象内部将 `#if/for/foreach/while/if/switch/catch` 等外层结构按顺序压平为 `control_path`，相关符号进入 `related_symbols`，不区分输入与常量，也不返回或求值完整条件表达式。控制表达式内部的显式赋值、`++/--` 和调用也会被扫描；`if/while/switch` 的条件求值不继承其自身分支，短路或三元分支、`for` 迭代器和 `catch when` 仍按条件执行处理。

模块入口 v12 以 Build.cs 父目录作为单模块边界，从 `StartupModule`、`ShutdownModule` 和实际绑定的同模块函数回调建立受限函数图。`registration.module_class` 始终保留注册宏显式声明的类，包括不需要本地状态分析的 `FDefaultModuleImpl`；`module.class` 仍表示可在所选模块源码内继续分析的本地类。`callback_bindings` 以绑定语句为单位报告委托源、`function | lambda | ufunction` 回调目标、绑定/解绑 API、所在函数、条件和源码行；Lambda 与 UFunction 函数体不跟踪。条件会沿本模块调用链传播，并覆盖 `if/else`、预处理、`for/foreach/while`、`switch/case/default`、`&&/||/??` 和三元表达式；`do-while` 循环体首次必定执行，因此尾部条件不进入循环体的 `when`，`switch` 不推断 case 穿透。无法与任何绑定配对的可达清理语句单独进入顶层 `unmatched_cleanups`。位于非 virtual 辅助函数中的绑定和解绑额外使用 `virtual_targets`，列出普通同模块调用链最终到达的 virtual 函数，以及该 virtual 函数内部发起调用链的源码行；重复路径不去重，无法到达时为空数组，语句直接位于 virtual 函数时省略该字段。非回调变化进入精简的 `state_models`：公共源码文件提升为模型级 `path`，转换只保留 `state`、`on`、始终存在的 `when` 和紧凑行号；`via` 仅在经过额外辅助函数时出现，`certainty` 仅在不是 `confirmed` 时出现。`closure` 只保留状态和原因。可观察覆盖和不透明外部效果分别进入 `conditional_overrides` 与 `unresolved_effects`。源码中不配对、意外或类型不匹配的 `()[]{}` 会产生 error 级 validation problem；词法器保留 `TEXT` 宏的真实括号，因此兼容宏参数字符串化与相邻字符串拼接。工具仍保留可恢复的部分事实，但命令行返回 1。结果是静态源码证据，不代表运行时行为证明。

`unresolved_effects` 对没有可靠状态模型的调用只做保守报告。除通用的明确状态动词模式外，当前显式白名单包含 `UGameplayTagsManager::Get().AddTagIniSearchPath`、`PreLoadingScreen->Init` 和 `PreLoadingScreen.Reset`；白名单命中只表示源码中发生了可能改变状态的外部调用，不推断其具体结果。相同方法名出现在其他接收者上不会因此命中。

Target.cs 同样要求显式选择单个文件：

```powershell
python tools\ue_inspect_target_rules.py `
  --target E:\UE_ITPS\LyraStarterGame\Source\LyraGame.Target.cs
```

TargetRules 和 ModuleRules 复用底层词法、位置、控制结构和表达式模型，但使用不同的公开 Schema。两者都从构造函数出发，只投影可达同文件辅助方法中的 `declared_mutations`、`unclassified_mutations` 和 `unresolved_effect_calls`；TargetRules 通过外层到内层的 `applicability.controls` 统一保留 `if`、预处理、循环、`switch/case`、`catch when` 和表达式级控制，各项按适用情况携带源码表达式和分支，不再公开 `conditions`、`control_path` 或重复的 `related_symbols`。每项 Target 结果通过 `source.method` 和 `source.line` 定位方法与行。跨文件派生包装 Target 不会展开基类；文件名与 `TargetInfo` 构造函数共同命中的类仍保留本文件 mutation，并以 `inheritance.kind: unresolved` 和 validation warning 明示其继承关系未在本文件得到证明。已声明的局部变量、类字段及其集合变更不作为 Target 设置；调用点条件不会传播到被调辅助方法。所有结果均是静态声明证据，工具不会执行构造函数、求值 Target Profile 或生成实际 UBT 构建结果。

## Lyra 研究证据工具

### 生成基线文件指纹

```powershell
& .\tools\new_lyra_baseline_fingerprint.ps1
```

默认扫描 `LyraStarterGame/`，排除可再生目录，并写入：

- `.planning/evidence/lyra-5.6.1/authoritative-files.sha256`
- `.planning/evidence/lyra-5.6.1/baseline-fingerprint.json`

### 归档一次 UE 运行日志

关闭对应 UE 进程后执行：

```powershell
& .\tools\archive_lyra_run.ps1 `
  -SourceLog E:\UE_ITPS\LyraStarterGame\Saved\Logs\LyraStarterGame.log `
  -RunId l0-editor-pie-001 `
  -Level L0 `
  -RunMode PIE
```

工具验证复制前后哈希，并创建不可覆盖的 Run 目录。捕获状态固定为 `captured_unassessed`，不会自动晋升为已验证证据。

### 查询 Lyra Asset Registry

`tools/query_lyra_asset_registry.py` 依赖 `unreal` Python 模块，必须在 Unreal Editor/Commandlet 的 Python 环境中运行，不能用普通系统 Python 执行。默认输出：

```text
.planning/evidence/lyra-5.6.1/asset-registry-slice.json
```

## 输出与安全边界

- 十一个聚焦检查 CLI 默认只读，并将 JSON 写到标准输出。
- 十一个检查 CLI 不计算或输出文件内容哈希；基线指纹工具保持独立职责。
- `--help`、参数说明、输出契约和退出码采用中英文双语；argparse 参数错误仍写入标准错误。
- 基线指纹、运行日志归档和 Asset Registry 查询属于证据生成工具，会写入 `.planning/evidence/`。
- 项目检查结果只证明静态声明和文件定位，不证明项目已经编译、启动、联网或通过测试。
- 当前工具固定以 UE 5.6.1 Lyra 为首个回归基准，但长期数据模型不应绑定 Lyra 架构。

## 开发验证

从仓库根目录运行全部契约测试：

```powershell
python -m unittest discover -s tests -v
```

单元测试覆盖统一结果信封、双语 CLI、严格 JSON、描述符压缩、Module 对账、Target 分类、Plugin 定位、路径分类、ModuleRules 相关性投影，以及模块入口的状态压缩、条件传播、自由函数回调、默认覆盖和保守闭合判断。静态检查通过不等于 UE 项目已经构建或运行；Lyra 构建与运行证据仍按 `.planning/evidence/` 中的独立流程管理。

## 当前回归基线

```text
Engine: 5.6.1
Project Modules: 2
Target classification: native-project
Direct Plugin References: 81
Declared Enabled / Disabled: 69 / 12
Simple Enabled / Disabled / Extended: 63 / 11 / 7
Resolved Plugin Descriptors: 69
Project / Engine Plugin Descriptors: 15 / 54
Applicable Enabled Resolved: 66 / 68
Validation: warning, warnings: 2
```

两条警告来自当前环境未定位的 Optional 插件 `D3DExternalGPUStatistics` 和 `EOSReservedHooks`。
