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
单个 Build.cs 声明修改了哪些 ModuleRules 设置并引用了什么？Target.cs 中有哪些静态规则操作、条件和未求值表达式？
单个模块的 StartupModule、ShutdownModule、委托注册/注销和实际绑定回调是什么？
```

当前交付包括十一个只读 CLI、共享服务层、统一结果信封、严格输入校验、中英文 CLI 帮助、UTF-8 输出、仓库级 Codex Skill 和 45 项契约测试。这些结果可以成为后续 Code Graph 和 Authority Context 的底层证据，但不会自动生成 Feature Graph、判断功能权威、修改 UE 项目、执行 UBT 规则或证明运行行为。

## 2. 设计原则

### 单一工程问题对应一个工具

Codex 不应为了回答“引擎版本是什么”而扫描所有 Module 和 Engine Plugin。CLI 按独立工程问题拆分；只有用户明确要求全部类别时，Codex 才依次调用相关聚焦工具，并保留每个结果的独立 Schema 与解释边界。

### 确定性优先

JSON 解析、注册表查询、路径定位、目录分类和受限源码结构分析由程序完成。LLM 负责选择工具、解释结果和提出下一步，不替代可确定的文件系统或源码判断。文件内容哈希只由基线指纹和运行证据工具生成，不进入十一个聚焦检查结果。

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

十一个聚焦检查工具只读项目、Engine、源码和注册表，并向标准输出写 JSON。证据生成工具是单独的有写入能力工具。

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
| `ue_read_plugin_descriptor.py` | 读取并校验单个 Plugin 描述符事实及 Module Build.cs | `.uplugin` | `ue-itps.plugin-descriptor.v2` |
| `ue_inspect_module_rules.py` | 提取单个 Build.cs 声明的设置变更和引用关系 | Build.cs | `ue-itps.module-rule-relations.v1` |
| `ue_inspect_target_rules.py` | 提取单个 Target.cs 声明的设置变更和引用关系 | Target.cs | `ue-itps.target-rule-relations.v1` |
| `ue_inspect_module_entry.py` | 提取单个模块的回调绑定和生命周期状态变化 | Build.cs | `ue-itps.module-entry-state.v12` |

CLI 只处理参数、调用服务、序列化结果和退出码，不应包含新的 UE 领域判断。十一个入口的正常扫描输出统一为 `schema_version → 模块事实 → validation → limits`；`validation` 使用 `ok | warning | error`，`limits` 以 `responsibility` 和 `boundaries` 明示职责边界。`--help`、参数说明、输出契约和退出码均为中英文双语，stdout/stderr 固定使用 UTF-8。

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
| `plugin_descriptor.py` | 读取单个 `.uplugin` 的基础字段、Module 声明、直接 Plugin 依赖和未建模字段清单；校验 UE 5.6.1 类型/枚举并递归对账 Build.cs |
| `source_parser.py` | C#/C++ 轻量词法、括号配对、类/方法、顶层自由函数、条件、操作、位置和未求值表达式事实 |
| `rule_source.py` | 将 Build.cs 内部语法事实投影为相关性，并为 Target.cs 保留独立源码契约 |
| `module_entry.py` | 提取回调绑定与解绑配对，并压缩非回调生命周期状态和可观察默认覆盖 |

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
→ ue_read_plugin_descriptor.py 读取字段、Module 与直接依赖声明，并递归对账 Build.cs
→ 显式选择描述符结果中的一个已解析 Build.cs
→ 按问题调用 ue_inspect_module_rules.py 或 ue_inspect_module_entry.py
```

前一层只提供下一层所需的确定性导航事实。后续结果不得嵌回 `.uproject` 或 Plugin 定位结果，也不得因为已经定位一个直接依赖声明而自动遍历它的描述符。

### 4.5 规则源码静态解析

Build.cs 和 Target.cs 复用 `source_parser.py` 的轻量词法、括号、类、方法、条件和操作模型，但公开不同职责的 Schema。

Build.cs 从 `ModuleRules` 构造函数出发，只跟踪可达的同文件辅助方法，并将内部语法事实投影为：

- `declared_mutations`：已知 ModuleRules 设置上的赋值或集合变更，以及 `literal | symbol | expression` 操作数；
- `unclassified_mutations`：形状像设置变更、但未被当前规则目录确认的候选；
- `unresolved_effect_calls`：可能间接改变规则、但无法安全推断效果的外部或继承方法调用；
- `applicability.kind` 的 `direct | conditional` 生效方式；条件对象内部包含外层到内层的扁平 `control_path`、`related_symbols`，记录本文件源码行证据。

空 `AddRange` 不产生引用，因此从相关性结果中省略；`Add` 与 `AddRange` 统一为 `add`，赋值、删除和更新同样使用语言无关的语义操作。复杂表达式整体保留，不递归输出 AST，也不把其中出现的部分字面量转写为最终设置值。Build.cs 不返回完整条件表达式：`#if/for/foreach/while/if/switch/catch` 等生效约束按源码嵌套顺序压平到 `applicability.control_path`，独立嵌套允许重复，`else if` 归一化为单层分支；相关符号只作为 `applicability.related_symbols`，不区分输入和常量。Target.cs 使用相同的 mutation 分类，但将 `if`、预处理、循环、`switch/case`、`catch when` 和表达式级局部控制统一输出为外层到内层的 `applicability.controls`，每项按适用情况携带 `kind`、源码 `expression` 和 `branch`，不再公开 `conditions`、`control_path` 或重复的 `related_symbols`；每项通过 `source.method` 和 `source.line` 定位证据，并过滤已识别的局部变量、类字段及其集合变更。直接或同文件可证明的 Target 类标记为 `inheritance.kind: confirmed`；跨文件派生包装类仅在文件名和 `TargetInfo` 构造函数共同匹配时作为局部候选输出，标记为 `unresolved` 并产生 warning，不展开或推断基类效果。控制表达式中的显式赋值、更新和调用也进入相关性分析；当前 `if/while/switch` 不控制自身条件的首次求值，短路与三元分支使用表达式级控制，`for` 迭代器和 `catch when` 保留各自局部控制。两种结果都不会执行构造函数、调用环境 API 或根据 Target Profile 选择分支。

可达辅助方法中的变更只保留该操作自身的局部控制路径；调用点控制当前不会传播并合并到被调方法内的变更。

### 4.6 模块入口边界

`ue_inspect_module_entry.py` 以所选 Build.cs 的父目录作为模块源码边界，解析模块类、顶层自由函数和三种 `IMPLEMENT_*_MODULE`。调用关系只从 `StartupModule`、`ShutdownModule` 出发，沿同模块辅助函数继续；实际绑定到本模块方法的成员回调会成为额外根，绑定的顶层 `static` 回调则只记录声明。调用点条件和成员回调绑定成立所需条件会继续传播，条件集合使用 AND 分支、多个路径使用 OR 分支。传播范围包括 `if/else`、预处理、`for/foreach/while`、`switch/case/default`、`&&/||/??` 和三元表达式；`do-while` 循环体至少执行一次，其尾部条件保留为控制结构证据但不作为循环体 `when`；switch 分支按词法 case 区间保守归属，不推断 fallthrough。

v12 在 `registration.module_class` 保留注册宏的原始模块类事实；`module.class` 只表示存在本地声明、可继续构建生命周期函数图的模块类。因此 `FDefaultModuleImpl` 可以出现在前者而后者为 `null`。回调声明会剥离 `public:`、`protected:`、`private:` 等访问控制标签，条件文本统一规范逻辑和比较运算符周围的空格。

对尚无可靠状态转换模型、但明确具有状态影响可能性的外部调用，工具只输出 `unresolved_effects`。显式白名单按完整 callee 匹配，当前覆盖 `UGameplayTagsManager::Get().AddTagIniSearchPath`、`PreLoadingScreen->Init` 和 `PreLoadingScreen.Reset`；它不会把其他接收者上的通用 `Init` 或 `Reset` 自动视为状态变化，也不会为白名单调用生成具体状态。

底层词法器对 `()[]{}` 执行独立的严格结构校验，区分未闭合左分隔符、意外右分隔符和类型不匹配。`TEXT` 保持为普通宏调用 token，不隐藏真实括号，因而支持字符串化宏参数和相邻字符串拼接。任一结构问题均以 error 进入 `validation.problems` 并使 CLI 返回 1；后续解析仍尽量运行，因此结果可以同时包含已恢复的模块事实和结构错误，不能把这些部分事实视为完整分析。

`callback_bindings` 先按 `AddRaw`、`AddLambda`、`BindUFunction`、`RegisterStartupCallback` 等受支持 API 确认绑定语句，再将目标分类为 `function | lambda | ufunction`；普通取地址不会单独构成绑定。每条记录保留委托源、回调类别与目标，以及绑定/解绑的 API、所在函数、条件和源码行，并用相同委托源及对象、回调或句柄身份匹配 `RemoveAll`、`Unbind`、`RemoveDynamic`、`Remove` 和启动回调注销。公共 `path` 在记录顶层只出现一次，跨文件子项显式覆盖；空 `unbind` 表示该绑定未匹配到解绑。未能与任何绑定配对的可达清理语句进入顶层 `unmatched_cleanups`。`CreateStatic`、`CreateLambda` 等嵌套工厂作为 `bind.factory`，不重复生成绑定。绑定的顶层 `static` 函数回调只记录声明；Lambda 与 UFunction 函数体不跟踪；直接调用的静态辅助函数不受影响。

当绑定或解绑语句位于非 virtual 辅助函数中时，`virtual_targets` 沿同模块普通调用边反向表达其生命周期根；每项的 `line` 是 virtual 函数内部首次调用下一层函数的行，而不是 virtual 函数声明行。不同静态路径分别保留，即使目标名称和行号相同也不去重；跨文件目标覆盖 `path`，无法追溯时返回空数组。语句直接位于 `virtual`、`override` 或 `final` 方法时，`in` 已足够说明位置，因此省略 `virtual_targets`。事件回调的注册关系不是普通函数调用，进入回调体时重新开始追踪，不将注册它的生命周期函数伪装成调用者。

绑定关系不进入 `state_models`；后者仅保留服务和普通注册等非回调状态，并使用精简结构。模型级 `path` 表示全部转换证据位于同一文件；单个证据使用 `line`，同文件多个证据使用 `lines`，跨文件时回退为 `evidence`。转换以 `state` 和 `on` 表达目标状态与触发点；`via` 省略触发函数自身，仅在经过额外辅助函数时出现；默认确认结论省略 `certainty`，推断结论仍显式标记。`when` 始终存在，空数组表示未观察到源码条件，每个字符串是一条 AND 分支，数组中的多条字符串互为 OR。`closure` 只公开 `status` 和 `reason`，不再重复输出可由转换推导的摘要或配对机制。

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
- 单 Plugin 描述符对账中的 Build.cs 缺失、歧义、重复声明或未声明规则为阻断问题。
- 单个 Build.cs/Target.cs 未发现相应 Rules 派生类为阻断问题；Build.cs 的未分类候选和未知副作用调用是正常相关性事实，不自动产生诊断。
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
- 单模块入口工具以所选 Build.cs 的父目录作为唯一源码边界；只返回扫描文件数量，所有证据路径相对该目录。
- 模块入口内部 IR 可以保留调用与赋值细节，但公开 v7 不输出方法、参数、签名、原始操作、RHS 或具体覆盖值。
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

源码规则与模块入口验收包括：四个新 CLI 使用相同结果信封但拥有独立 Schema；`.uplugin`、Build.cs、Target.cs 和模块入口结果互不嵌套；Build.cs 只公开设置变更相关性而不复刻代码结构；模块入口只公开状态结论、传播后的条件和证据位置。当前 51 项单元测试覆盖十一个 CLI 的双语帮助、既有项目契约和新增源码边界。

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
5. Build.cs 的复杂操作数保留为 `expression`，Target.cs 的 `partial` 和 `unresolved` 也不能转写成实际规则值；两者都不会执行字符串插值、拼接、环境 API、文件读取或辅助函数。
6. 模块入口状态分类只确认受支持的 Delegate、Register/Unregister、集合和直接数据流；Initialize/Shutdown 配对标记为 inferred，宏封装、模板适配器和复杂别名不会被猜测。
7. 模块入口的调用可达性按本模块方法或顶层函数名匹配，不建立完整的 C++ 重载、namespace、虚派发、别名和跨翻译单元解析；每个函数最多保留 32 条不同条件路径，超限产生 warning。
8. 项目类型只记录根 Target 证据，尚未分析 UBT 临时 Target/hybrid 项目原因。
9. 路径边界依赖规范化结果，尚未针对 Windows junction、symlink 和权限不可访问状态建立完整测试。

### 契约

1. 结果使用裸 `dict`，没有提交独立 JSON Schema、TypedDict 或 dataclass 契约。
2. 参数解析或输入读取失败仍使用 stderr 文本，不产生正常扫描 JSON 契约。

### 性能

1. 每次 Plugin 解析都重新遍历 Engine Plugin 树，没有进程内索引缓存。
2. 单模块入口会在所选 Build.cs 的父目录内重新遍历源码；连续查询同一 Plugin 的多个模块时没有共享源码索引。
3. 轻量源码解析器会读取所选文件或模块边界内的 C#/C++ 文本并在内存中建立 Token 列表；超大模块尚无增量解析或文件级缓存。
4. CLI 逐进程调用无法共享描述符、目录索引和 Token；未来 MCP 常驻进程应提供只读缓存和明确失效键。

### 测试

1. 当前 51 项单元测试覆盖统一结果信封、十一个 CLI 的双语帮助、严格 JSON、描述符压缩、Module 对账、Target 分类、Plugin 定位、路径分类、ModuleRules 相关性投影，以及模块入口的状态压缩、条件传播、自由函数回调、默认覆盖和闭合判断。
2. 尚未完整覆盖 Engine 注册表歧义、Windows junction/symlink、权限不可访问状态、完整 Profile 过滤矩阵和真实 UBT 源码语法变体矩阵。
3. Lyra 回归目前是实际命令 smoke 验证，尚未固化为去除绝对路径后的源码工具 golden fixture。

## 11. 建议优化顺序

### P0：固定正确性和契约

1. 为十一个独立 Schema 添加版本化 JSON Schema，并增加跨版本兼容检查。
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
- 模块入口只允许生命周期辅助方法和实际绑定的成员回调形成受限可达关系；绑定事实以 API 与 `&` 函数引用为证据，顶层 `static` 回调不进入函数体，结果不扩展为通用调用图。
- 每个新结论必须标注来源文件、规则或运行证据。
- 没有对应测试和上下文条件的结果不得晋升为权威。
- 对 Engine、Lyra 源码和资产的修改不属于这些只读检查工具的职责。

## 13. 维护者审查清单

建议重点检查以下决策：

1. 十一个工具边界是否足够小，是否仍有应独立拆出的策略层？
2. Profile 是否应继续由工具接收，还是由更上层 Policy Engine 统一计算？
3. Engine 解析是否应直接复用 UE DesktopPlatform/UBT，而不是维护注册表近似实现？
4. Plugin 闭包应优先做到“描述符闭包”还是“某个 Target/Profile 的有效闭包”？
5. 绝对路径、时间戳和 SHA-256 在跨机器可复现结果中如何分层存储？
6. 是否接受 Python 作为长期核心，还是将扫描核心迁移到更贴近 UBT 的 C#/.NET？
7. MCP 常驻缓存如何失效，如何证明缓存没有污染权威边界？
8. 哪些事实可以仅由静态扫描获得，哪些必须进入 UHT、UBT、Editor 或运行验证？
9. 轻量源码解析器的支持语法边界是否足够明确，哪些情况应升级为诊断而不是 `unresolved`？
10. 下一阶段是否先建设版本化 Schema 与 source golden，再继续扩展 Config、Asset 和 Plugin 闭包？
