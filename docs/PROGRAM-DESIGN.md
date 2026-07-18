<!-- generated-by: gsd-doc-writer -->
# UE-ITPS 工具程序设计说明

本文描述仓库 `tools/` 当前可验证实现，供代码检查、架构讨论和后续优化使用。项目级 v1 由七个只读检查 CLI 组成；源码规则与模块入口里程碑在不修改这些项目级 Schema 的前提下新增五个聚焦工具。里程碑版本与各工具的独立 Schema 版本分开管理，因此新增工具均从各自的 v1 契约开始。本文描述实际代码，不是最终产品承诺。

## 1. 当前目标与完成状态

项目级 v1 已完成 UE 项目进入系统时的第一层确定性检查：

```text
项目入口在哪里？
`.uproject` 明确声明了什么？
EngineAssociation 对应哪套真实 Engine？
项目 Module、Target 和直接 Plugin 引用能否在磁盘上定位？
项目根目录中的内容属于输入、生成物、缓存还是运行状态？
```

源码规则与模块入口里程碑增加第二层按需深入：

```text
单个 `.uplugin` 明确声明了什么？
该插件的声明 Module 能否定位到 Build.cs 和 IMPLEMENT_*_MODULE 入口？
单个 Build.cs 或 Target.cs 中有哪些静态规则操作、条件和未求值表达式？
单个模块的 StartupModule、ShutdownModule、委托注册/注销和实际绑定回调是什么？
```

当前交付包括十二个只读 CLI、共享服务层、统一结果信封、严格输入校验、中英文 CLI 帮助、UTF-8 输出、仓库级 Codex Skill 和 38 项契约测试。这些结果可以成为后续 Code Graph 和 Authority Context 的底层证据，但不会自动生成 Feature Graph、判断功能权威、修改 UE 项目、执行 UBT 规则或证明运行行为。

## 2. 设计原则

### 单一工程问题对应一个工具

Codex 不应为了回答“引擎版本是什么”而扫描所有 Module 和 Engine Plugin。CLI 按独立工程问题拆分；只有用户明确要求全部类别时，Codex 才依次调用相关聚焦工具，并保留每个结果的独立 Schema 与解释边界。

### 确定性优先

JSON 解析、注册表查询、路径定位、目录分类和受限源码结构分析由程序完成。LLM 负责选择工具、解释结果和提出下一步，不替代可确定的文件系统或源码判断。文件内容哈希只由基线指纹和运行证据工具生成，不进入十二个聚焦检查结果。

### 事实与结论分级

程序区分：

- `.uproject` 的直接声明；
- 文件系统定位结果；
- Profile 下的适用性判断；
- Build.cs、Target.cs 和模块入口中的静态源码操作；
- 尚未实现或无法证明的运行语义。

`validation: ok` 只表示该次静态扫描未发现问题；`warning` 表示发现非阻断问题；两者都不表示项目已经编译、运行或通过测试。

### 逐层显式深入

项目级结果只负责发现和定位，不嵌入后续源码解析结果。调用者先取得 `.uproject` 和直接 Plugin 位置，再显式选择一个 `.uplugin`、一个 Build.cs、一个 Target.cs 或一个模块入口继续查询。每层保留独立 Schema、`validation` 和 `limits`，不创建聚合权威。

### 默认只读

十二个聚焦检查工具只读项目、Engine、源码和注册表，并向标准输出写 JSON。证据生成工具是单独的有写入能力工具。

## 3. 程序结构

```text
Codex / 用户
    │
    ├─ 仓库 Skill: .agents/skills/ue-project-inspector/
    │       负责意图路由与解释边界
    │
    └─ tools/ue_*.py
            负责参数、退出码与 JSON 输出
                │
                ▼
       tools/ue_project_tools/
            ├─ 项目级发现、描述符、Engine、路径和定位服务
            ├─ 单文件 Plugin、规则源码和模块入口服务
            └─ 共享结果信封、受控遍历、UE JSON 与轻量词法层
                │
                └─ 各工具独立 Schema JSON
```

### 3.1 CLI 层

| CLI | 单一职责 | 主要输入 | Schema |
|---|---|---|---|
| `ue_find_projects.py` | 发现 `.uproject` 并报告歧义 | Search root | `ue-itps.project-discovery.v1` |
| `ue_read_project_descriptor.py` | 读取描述符显式事实 | `.uproject` | `ue-itps.project-descriptor.v1` |
| `ue_resolve_engine.py` | 解析 Engine 与 `Build.version` | `.uproject`、可选 Engine override | `ue-itps.engine-resolution.v1` |
| `ue_inspect_modules.py` | 对账项目 Module 结构 | `.uproject` | `ue-itps.project-modules.v1` |
| `ue_inspect_targets.py` | 发现 Target 与原生 Target 证据 | `.uproject` | `ue-itps.project-targets.v1` |
| `ue_resolve_plugins.py` | 定位直接 Plugin 引用 | `.uproject`、可选 Engine override、Profile | `ue-itps.project-plugin-references.v1` |
| `ue_classify_project_paths.py` | 用显式描述符证据校验并分类项目根路径状态 | `.uproject` | `ue-itps.project-paths.v1` |
| `ue_read_plugin_descriptor.py` | 读取单个 Plugin 描述符事实 | `.uplugin` | `ue-itps.plugin-descriptor.v1` |
| `ue_inspect_plugin_modules.py` | 对账单个 Plugin 的 Module、Build.cs 和入口候选 | `.uplugin` | `ue-itps.plugin-modules.v1` |
| `ue_inspect_module_rules.py` | 读取单个 Build.cs 的静态规则事实 | Build.cs | `ue-itps.module-rules-source.v1` |
| `ue_inspect_target_rules.py` | 读取单个 Target.cs 的静态规则事实 | Target.cs | `ue-itps.target-rules-source.v1` |
| `ue_inspect_module_entry.py` | 读取单个模块的注册、生命周期和委托操作 | Build.cs | `ue-itps.module-entry-source.v1` |

CLI 只处理参数、调用服务、序列化结果和退出码，不应包含新的 UE 领域判断。十二个入口的正常扫描输出统一为 `schema_version → 模块事实 → validation → limits`；`validation` 使用 `ok | warning | error`，`limits` 以 `responsibility` 和 `boundaries` 明示职责边界。`--help`、参数说明、输出契约和退出码均为中英文双语，stdout/stderr 固定使用 UTF-8。

### 3.2 服务层

| 文件 | 当前职责 |
|---|---|
| `common.py` | 统一结果契约、双语 CLI、UTF-8 JSON 序列化、路径规范化和受控遍历 |
| `discovery.py` | `.uproject` 搜索、唯一候选选择和歧义状态 |
| `descriptor.py` | 顶层字段、Plugin 声明三分类、未知字段保留、Additional 目录边界 |
| `engine.py` | GUID/版本关联、Windows 注册表、相对路径、祖先 Engine、`Build.version` |
| `code_inventory.py` | Module Build.cs/入口证据与 Target 文件发现 |
| `plugins.py` | 项目/Engine Plugin 描述符索引、直接引用定位和基础 Profile 过滤 |
| `structure.py` | 以 `.uproject.parent` 为根分类路径，并用 Modules/AdditionalRootDirectories 正向证据诊断缺失的 Source |
| `ue_json.py` | 读取单个 UE JSON，识别注释、尾逗号和重复字段，同时保持原有严格 `.uproject` JSON 读取器不变 |
| `plugin_descriptor.py` | 读取单个 `.uplugin` 的基础字段、Module 声明、直接 Plugin 依赖和未建模字段清单 |
| `plugin_modules.py` | 在单个 Plugin 边界内对账 Module 声明、Build.cs 和 `IMPLEMENT_*_MODULE` 候选 |
| `source_parser.py` | C#/C++ 轻量词法、括号配对、类/方法、条件、操作、位置和未求值表达式事实 |
| `rule_source.py` | 为单个 Build.cs 和 Target.cs 提供独立结果信封与规则类校验 |
| `module_entry.py` | 解析单模块注册宏、生命周期可达辅助方法、委托注册/注销和实际绑定回调 |

Target 位置校验区分四种状态：`Source` 下没有 Target 为错误；只有子目录 Target 为根 Target 缺失警告；根目录与子目录同时存在 Target 为混合位置警告；只有根目录 Target 为正常。子目录 Target 可被 UBT 发现，因此不直接判为非法。

## 4. 主要执行流程

### 4.1 最小路由

```text
用户询问 Engine 版本
→ ue_resolve_engine.py
→ 读取 `.uproject` 的 EngineAssociation
→ 精确注册表映射 / 版本匹配 / 路径 / 祖先 Engine
→ 读取 Engine/Build/Build.version
→ 输出版本、根目录和解析方法
```

### 4.2 全面检查路由

```text
发现唯一 `.uproject`
→ 读取描述符
→ 解析 Engine
→ 分别运行 Module / Target / Plugin / Path 检查
→ 校验每个结果的 validation 与 limits
→ 由调用者汇总，不创建新的聚合 Schema
```

每个工具的原始 JSON 都是独立证据。调用者可以汇总展示，但不得丢失组件 Schema、诊断来源或解释边界，也不得把汇总结果冒充新的扫描事实。

### 4.3 Engine 解析优先级

```text
显式 --engine-root
→ EngineAssociation 中的相对/绝对路径
→ Windows 注册表精确关联
→ 按 Build.version 匹配语义版本关联
→ 向项目父目录查找 Engine
→ unresolved / ambiguous
```

`EngineAssociation` 是原始关联键，实际版本必须来自解析后 Engine 的 `Build.version`。

### 4.4 单 Plugin 逐层深入

```text
ue_read_project_descriptor.py
→ 得到 `.uproject` 的直接 Plugin 声明
→ ue_resolve_plugins.py 定位描述符
→ 显式选择一个 `.uplugin`
→ ue_read_plugin_descriptor.py 读取字段、Module 与直接依赖声明
→ 需要模块路径时调用 ue_inspect_plugin_modules.py
→ 显式选择返回的一个 Build.cs
→ 按问题调用 ue_inspect_module_rules.py 或 ue_inspect_module_entry.py
```

前一层只提供下一层所需的确定性导航事实。后续结果不得嵌回 `.uproject` 或 Plugin 定位结果，也不得因为已经定位一个直接依赖声明而自动遍历它的描述符。

### 4.5 规则源码静态解析

Build.cs 和 Target.cs 复用 `source_parser.py` 的词法、括号、类、方法、条件和操作模型，但由 `rule_source.py` 输出不同 Schema。规则解析记录：

- `ModuleRules`、`TargetRules` 及同文件派生规则类；
- 构造函数、同文件辅助方法和直接调用关系；
- 赋值、方法调用、集合 Add/AddRange/Remove/RemoveAll；
- Public/Private/Dynamic 依赖、Include、Definitions、PCH 和 IWYU 等已知 ModuleRules 操作分类；
- `if/else` 与预处理条件上下文；
- 起止行列、原始表达式，以及 `literal | partial | unresolved` 求值状态。

“求值”只识别确定的字符串字面量和字面量集合，不执行构造函数、不调用环境 API，也不根据 Target Profile 选择分支。即使所有字面量都可提取，结果仍是源码声明，不是最终 UBT 状态。

### 4.6 模块入口边界

`ue_inspect_module_entry.py` 以所选 Build.cs 的父目录作为模块源码边界，解析模块类、继承、声明/定义和三种 `IMPLEMENT_*_MODULE`。调用关系只从 `StartupModule`、`ShutdownModule` 出发，沿同模块方法继续；注册操作中实际绑定到本模块方法的回调会成为额外的 `bound-callback` 根。

委托事实记录委托源、Add/Bind/Remove/Unbind API、回调目标、所属方法、可达根、条件、位置和可能的对应注册/注销位置。该边界能够覆盖 `OnBeginPIE`、`OnEndPIE`、`ModulesChangedCallback` 等实际绑定回调，但不会扩展成通用 C++ 类图或项目级调用图。

## 5. Profile 与“必需”边界

Plugin 扫描上下文包含：

```text
operation: scan | open_editor | build_editor | run_game | cook_package
platform
target_type
```

默认 Profile 为 `scan / Win64 / Editor`。在 `scan` 下，程序只陈述声明、定位和适用性，不把目录或插件直接判定为某个运行场景的最小必需项。

Plugin 工具只接受 `operation / platform / target_type`；`configuration` 不被接受或评估。

完整的必需性计算仍需要执行层面的 TargetRules/Build.cs 结果、`.uplugin` 闭包、Config 合并、资产可达性和实际构建/运行证据。新增源码工具只能提供带条件的静态声明，不能替代 UBT 求值。

## 6. 诊断与退出码

### 聚焦工具

- 发现工具通过结果中的 `selected`、`not-found` 或 `ambiguous` 表达候选状态。
- Engine 未解析、Module Build.cs 缺失/歧义、非 Optional 且适用的 Plugin 缺失可以导致非零退出。
- Optional、Disabled 或当前 Profile 不适用的 Plugin 不应升级为构建失败。
- 单 Plugin 模块对账中的 Build.cs 缺失、歧义、重复声明或未声明规则为阻断问题；入口缺失或歧义当前为警告。
- 单个 Build.cs/Target.cs 未发现相应 Rules 派生类为阻断问题；无法静态求值的表达式本身是正常事实，不自动产生诊断。
- 模块入口未找到或找到多个匹配注册宏，以及显式注册类未在模块源码中声明，当前为警告。

### 统一退出码

```text
0 = validation ok 或 warning
1 = 扫描完成但存在阻断诊断
2 = 输入、发现或 JSON 解析失败
```

发现工具的 `not-found` 和 `ambiguous` 属于阻断诊断并返回 1。诊断 `code` 使用稳定英文机器码；argparse 帮助为中英文双语，参数错误仍使用标准 stderr 文本。

## 7. 路径与安全策略

- 多个 `.uproject` 返回歧义，不沿用“取第一个”策略。
- `AdditionalRootDirectories` 和 `AdditionalPluginDirectories` 先规范化路径。
- 指向项目外部的 Additional 目录默认标记为 `skipped_external`，不遍历。
- 聚焦 Plugin 输出保留 `AdditionalPluginDirectories` findings；非法条目为错误，跳过外部目录为警告。
- 项目 Plugin 优先于 Engine Plugin；其他候选保留在 `alternate_descriptors` 中。
- Plugin v1 在 `path_roots` 中集中记录项目与 Engine 绝对根；描述符路径按 `origin` 相对对应根保存。
- 正常 Plugin 项从 `item_defaults` 继承省略状态；未定位、候选冲突或关联诊断的问题项保留全部建模字段。
- Plugin 声明仅含 `Name`/`Enabled` 时压缩到简单启用或禁用列表；出现其他字段时记录为 `extended` 并保留原始 JSON Pointer；重复名称进入阻断诊断。
- `extended` 表示需要回读完整声明，不保证每个额外字段都是启用条件；非法声明进入验证问题。
- `Binaries` 对源码项目通常是生成物，但对纯预编译分发可能是条件输入。
- `Saved/Logs` 可以作为运行证据来源，但不能反向成为源码权威。
- 路径 v1 读取 `.uproject` 顶层显式声明，但不读取目录内容；只在 Modules 非空且没有 AdditionalRootDirectories 时把缺失 Source 诊断为错误。
- 路径项不携带必要性字段；必要目录缺失只进入 `validation`。缺少 Module 声明不反向证明 Source 不需要。
- 路径 v1 只在顶层 `project_root` 记录一次绝对根；所有路径项与诊断使用 `project_relative_path`，便于跨机器比较。
- 路径项只保留稳定 `role`，不嵌入本地化 `reason`；角色说明由调用者的解释或展示层负责。
- 项目根不作为独立调用参数传入；路径服务只从 `.uproject.parent` 唯一推导项目根。
- Additional* 相对路径仍由描述符服务按 UE/UBT 语义解析，不进入路径分类服务。
- 单 Plugin 描述符工具只读取用户或上一步显式选中的 `.uplugin`；其直接 Plugin 依赖只作为声明输出，不继续定位。
- 单 Plugin 模块导航只搜索该描述符目录下的 `Source` 与 `Platforms`，不会回到项目或 Engine 目录做全局模块扫描。
- 单模块入口工具以所选 Build.cs 的父目录作为唯一源码边界；返回的 `source_files` 和调用关系不会越过该目录。
- `.uplugin` 读取器支持 UE 描述符中实际出现的注释和尾逗号，并把重复字段作为警告；现有 `.uproject` 严格 JSON 读取器保持不变。

## 8. 其他证据工具

### `new_lyra_baseline_fingerprint.ps1`

扫描项目权威输入候选，排除 `.vs`、`Binaries`、`Intermediate`、`DerivedDataCache`、`Saved` 等可再生或本地状态，生成逐文件 SHA-256 manifest 和汇总 JSON。

### `archive_lyra_run.ps1`

在 UE 进程关闭后复制原始日志，验证源文件捕获前后未变化、复制哈希一致，并通过 staging 目录原子发布不可覆盖的 Run。输出状态固定为 `captured_unassessed`。

### `query_lyra_asset_registry.py`

在 UE Python 环境中等待 Asset Registry 完成，查询固定 Lyra 资产、默认属性和直接依赖，写出当前研究切片。它是 Lyra 5.6.1 专用研究工具，不是通用项目扫描器。

## 9. 验收与当前回归事实

项目级 v1 的代码级验收包括：七个既有 CLI 和 Schema 保持不变；`validation` 与 `limits` 明确分离事实、诊断和解释边界；输入与项目结构异常按职责失败关闭。

源码规则与模块入口验收包括：五个新 CLI 使用相同结果信封但拥有独立 Schema；`.uplugin` 读取、Plugin 模块导航、Build.cs、Target.cs 和模块入口互不嵌套；项目模块和 Plugin 模块的 Build.cs 使用同一底层规则解析器；条件、位置和未求值表达式按源码事实输出；生命周期只沿辅助方法和实际绑定回调展开。当前 38 项单元测试覆盖十二个 CLI 的双语帮助、既有项目契约和新增源码边界。

Lyra 实际回归已验证：`CommonLoadingScreen.uplugin` 的两个声明模块均定位到唯一 Build.cs 和入口；`LyraGame.Target.cs`、`LyraEditor.Build.cs` 均解析到规则类；`FLyraEditorModule` 的入口结果识别 `OnBeginPIE`、`OnEndPIE`、`ModulesChangedCallback` 及其注册/注销关系。所有这些结果仍是静态证据，不替代 UBT、Editor 或运行验证。

当前本机 Lyra 5.6.1 smoke test：

```text
Engine root: D:/UnrealEngine_5.6
Engine version: 5.6.1
Project Modules: 2
Target classification: native-project
Direct Plugin References: 81
Declared Enabled / Disabled: 69 / 12
Simple Enabled / Disabled / Extended: 63 / 11 / 7
Resolved Plugin Descriptors: 69
Project / Engine Plugin Descriptors: 15 / 54
Applicable Enabled Resolved: 66 / 68
Validation: warning
Warnings: 2 Optional Plugin descriptors not resolved
```

这些数值用于回归，不应成为通用算法中的硬编码。

## 10. 已知问题

### 正确性

1. Plugin 工具只解析 `.uproject` 直接引用，没有计算 Engine 默认插件、项目插件默认值和 `.uplugin` 传递依赖闭包。
2. Plugin Profile 过滤只覆盖基础 Platform/Target 字段；聚焦工具不接受 configuration，TargetConfiguration、Program、GameTarget 和 `HasExplicitPlatforms` 语义不参与适用性判断。
3. Module 定位按 `*.Build.cs` basename 搜索，尚未使用 UBT 规则程序集证明最终选中项。
4. Build.cs/Target.cs 解析器是确定性的轻量语法层，不覆盖完整 C# 语义、跨文件继承、重载解析、局部函数、动态生成规则或反射调用。
5. 字面量提取不会执行字符串插值、拼接、环境 API、文件读取或辅助函数；`partial` 和 `unresolved` 不能转写成实际规则值。
6. 模块入口解析只识别受支持的 Add/Bind/Remove/Unbind API 和显式回调取址表达式；宏封装、模板适配器或间接保存的委托句柄可能只保留为普通调用事实。
7. 模块入口的调用可达性按方法名匹配，不建立完整的 C++ 重载、虚派发、别名和跨翻译单元解析。
8. 项目类型只记录根 Target 证据，尚未分析 UBT 临时 Target/hybrid 项目原因。
9. 路径边界依赖规范化结果，尚未针对 Windows junction、symlink 和权限不可访问状态建立完整测试。

### 契约

1. 结果使用裸 `dict`，没有提交独立 JSON Schema、TypedDict 或 dataclass 契约。
2. 参数解析或输入读取失败仍使用 stderr 文本，不产生正常扫描 JSON 契约。

### 性能

1. 每次 Plugin 解析都重新遍历 Engine Plugin 树，没有进程内索引缓存。
2. 单 Plugin 模块导航和单模块入口会在各自边界内重新遍历目录；连续查询同一 Plugin 的多个模块时没有共享源码索引。
3. 轻量源码解析器会读取所选文件或模块边界内的 C#/C++ 文本并在内存中建立 Token 列表；超大模块尚无增量解析或文件级缓存。
4. CLI 逐进程调用无法共享描述符、目录索引和 Token；未来 MCP 常驻进程应提供只读缓存和明确失效键。

### 测试

1. 当前 38 项单元测试覆盖统一结果信封、十二个 CLI 的双语帮助、严格 JSON、描述符压缩、Module 对账、Target 分类、Plugin 定位、路径分类，以及规则条件、未求值表达式、Plugin 模块导航和生命周期回调边界。
2. 尚未完整覆盖 Engine 注册表歧义、Windows junction/symlink、权限不可访问状态、完整 Profile 过滤矩阵和真实 UBT 源码语法变体矩阵。
3. Lyra 回归目前是实际命令 smoke 验证，尚未固化为去除绝对路径后的源码工具 golden fixture。

## 11. 建议优化顺序

### P0：固定正确性和契约

1. 为十二个独立 Schema 添加版本化 JSON Schema，并增加跨版本兼容检查。
2. 建立小型 C#/C++ 语法 fixture 与 Lyra 5.6.1 source golden，归一化绝对路径和位置敏感字段。
3. 补齐字符串插值、复杂泛型、嵌套条件、预处理分支、宏封装委托和同名重载测试。
4. 将事实发现、Profile policy 和诊断定级继续保持分离，避免把静态声明汇总成有效构建结果。
5. 补齐外部路径、junction/symlink 和不可访问状态测试。

### P1：扩大确定性图谱输入

1. 在保持单 Plugin 工具独立的前提下，新增显式请求的 Plugin 描述符闭包工具；不把闭包计算塞回 `.uproject` 或直接引用定位 Schema。
2. 研究 UBT 规则程序集能够提供的确定性结果，并与当前静态声明层建立可追溯、不可混淆的双层证据模型。
3. 建立 Config 合并、AssetManager 和 Primary Asset 入口工具。
4. 为 Engine/Project Plugin、单 Plugin Module 和源码 Token 索引增加以根目录、文件状态为键的只读缓存。
5. 将连续的 Module/Target/Plugin 查询优化为一次索引、多次显式查询。

### P2：Codex 产品接入

1. 将服务函数暴露为本地 STDIO MCP tools。
2. MCP 层保持逐层工具调用：项目发现、单 Plugin、单 Module、单文件事实互不聚合。
3. 保留 Skill 作为任务路由和解释策略，不在 Skill 中复制程序逻辑。
4. 稳定后打包为 Codex Plugin，供团队安装。
5. React/Editor UI 只消费稳定 JSON，不参与扫描和权威判断。

## 12. 扩展规则

- 新的独立工程问题优先新增小服务和小 CLI，不扩大现有 CLI 的语义。
- 共享 helper 不作为 Codex 工具暴露。
- 全面检查由调用者组合独立结果，不新增聚合 Schema 或重新实现领域扫描。
- 上一层只返回下一层的导航事实；不得自动把所有已定位 Plugin、Module 或源码全部展开。
- 项目模块与 Plugin 模块必须复用同一 Build.cs 解析底层，但项目级、Plugin 级和单文件公开结果保持独立。
- 源码解析遇到不能安全计算的表达式时保留原文和条件，不猜测、不执行、不降级为有效值。
- 模块入口只允许生命周期辅助方法和实际绑定回调形成受限可达关系，不扩展为通用调用图。
- 每个新结论必须标注来源文件、规则或运行证据。
- 没有对应测试和上下文条件的结果不得晋升为权威。
- 对 Engine、Lyra 源码和资产的修改不属于这些只读检查工具的职责。

## 13. 维护者审查清单

建议重点检查以下决策：

1. 十二个工具边界是否足够小，是否仍有应独立拆出的策略层？
2. Profile 是否应继续由工具接收，还是由更上层 Policy Engine 统一计算？
3. Engine 解析是否应直接复用 UE DesktopPlatform/UBT，而不是维护注册表近似实现？
4. Plugin 闭包应优先做到“描述符闭包”还是“某个 Target/Profile 的有效闭包”？
5. 绝对路径、时间戳和 SHA-256 在跨机器可复现结果中如何分层存储？
6. 是否接受 Python 作为长期核心，还是将扫描核心迁移到更贴近 UBT 的 C#/.NET？
7. MCP 常驻缓存如何失效，如何证明缓存没有污染权威边界？
8. 哪些事实可以仅由静态扫描获得，哪些必须进入 UHT、UBT、Editor 或运行验证？
9. 轻量源码解析器的支持语法边界是否足够明确，哪些情况应升级为诊断而不是 `unresolved`？
10. 下一阶段是否先建设版本化 Schema 与 source golden，再继续扩展 Config、Asset 和 Plugin 闭包？
