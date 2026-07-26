<!-- generated-by: gsd-doc-writer -->
# UE-ITPS 扫描器核心程序设计

本文面向维护 `tools/ue_project_tools/` 与 15 个公开扫描 CLI 的开发者。内容以当前实现和 `tests/` 中的自包含夹具为准，描述静态证据扫描器的职责、契约、边界与扩展方式。

## 1. 设计目标与非目标

### 1.1 目标

- 将一个工程问题映射到一个小而明确的只读工具，避免为回答局部问题扫描无关对象。
- 对 `.uproject`、`.uplugin`、Build.cs、Target.cs 和显式选择的 C++ 源码生成可追溯、确定性排序的 JSON 事实。
- 将事实、扫描诊断和解释边界分开：模块事实位于结果主体，问题位于 `validation`，能力边界位于 `limits`。
- 支持从项目入口逐层导航到 Plugin、Module、Target、源码单元和指定函数，同时要求调用方显式选择每一次深入对象。
- 在解析能力之外保守失败：保留原表达式、输出 `unclassified`、`unresolved` 或诊断，不执行源码，也不猜测有效构建或运行结果。
- 让 15 个入口共享 CLI 帮助、UTF-8 输出、结果信封和退出码语义，同时保持各自独立、可版本化的 Schema。

### 1.2 非目标

- 不替代 UnrealBuildTool（UBT）执行 ModuleRules、TargetRules、Plugin 选择或构建图计算。
- 不替代 UnrealHeaderTool（UHT）完成反射语义、生成代码或宏合法性验证。
- 不替代 Editor、Asset Registry、Cook、PIE、独立进程或联网会话提供的运行权威。
- 不生成完整 C++/C# AST、类型系统、继承图、调用图或依赖闭包。
- 不自动遍历所有已定位的 Plugin、Module、include 或被调用函数。
- 不修改 UE 项目、Engine、源码、资产、注册表或配置。
- 不把 `validation: ok` 解释为“可编译”“可启动”“行为正确”或“测试已通过”。

## 2. 分层架构

```text
用户 / 自动化调用方
        |
        v
15 个 tools/ue_*.py CLI
  参数解析、UTF-8、服务调用、JSON、退出码
        |
        v
tools/ue_project_tools/ 领域服务
  项目发现与描述符 | Engine | Module/Target | Plugin | 路径
        |
        +--------------------------+
        |                          |
        v                          v
规则、C# 与模块入口投影        显式 C++ 源码单元投影
Build.cs / Target.cs / .cs    .cpp + 唯一自动配套头文件
规则 / C# function / 生命周期 include / type / function
        |                          |
        +------------+-------------+
                     v
共享确定性基础
严格/UE JSON、路径归一化、文件遍历、词法 Token、
声明、控制结构、预处理、操作、结果信封与诊断
```

架构采用“薄 CLI + 领域服务 + 共享解析基础”的分层方式。CLI 不承载新的 UE 领域判断；服务负责组装某一个 Schema；底层解析器提供可复用的词法和结构事实，但不直接对外形成新的聚合权威。

## 3. 模块与文件职责

### 3.1 项目、描述符与定位服务

| 文件 | 职责 |
|---|---|
| `common.py` | 双语 argparse、退出码说明、UTF-8 流配置、严格 JSON、路径归一化、受控文件遍历、`validation` 与统一结果信封。 |
| `discovery.py` | 递归发现 `.uproject`、拒绝多候选擅自选择，并为源码工具寻找最近且唯一的祖先项目。 |
| `descriptor.py` | 投影 `.uproject` 显式字段，分类 Module/Plugin 声明，解析 Additional 目录并保留未建模字段。 |
| `engine.py` | 按显式覆盖、关联路径、Windows 注册表、版本匹配和祖先路径解析 Engine，并读取 `Build.version`。 |
| `code_inventory.py` | 按 basename 发现 Build.cs、对账项目 Module、提取 `IMPLEMENT_*_MODULE` 入口证据、发现 Target.cs。 |
| `plugins.py` | 为 `.uproject` 的直接 Plugin 引用建立描述符索引，计算有限 Profile 适用性并输出完整记录。 |
| `structure.py` | 依据 `.uproject.parent` 和根目录文件系统状态分类项目、构建、IDE、缓存与本地状态路径。 |
| `ue_json.py` | 读取允许注释和尾逗号的 UE 描述符 JSON，记录重复字段；不接受 `NaN` 等非标准常量。 |
| `plugin_descriptor.py` | 校验一个显式 `.uplugin` 的字段、枚举、Module 和直接 Plugin 依赖，并在该 Plugin 的 `Source`/`Platforms` 下对账 Build.cs。 |

### 3.2 规则与模块入口服务

| 文件 | 职责 |
|---|---|
| `rule_source.py` | 将通用解析事实投影为 ModuleRules mutation 关系，或 TargetRules 类、成员变量和函数索引。 |
| `cs_source.py` | 按名称选择任意 `.cs` 中的全部类成员函数，并投影签名、外部类型和方法引用。 |
| `module_entry.py` | 以所选 Build.cs 的父目录为模块边界，编排源码加载、注册类选择、回调与状态投影，输出 module-entry v12。 |
| `module_entry_common.py` | 委托 API 目录、回调/清理身份、条件合并、源码位置和每个 callable 最多 32 个上下文的共享规则。 |
| `module_entry_callables.py` | 建立模块内受限 callable 索引和可达上下文，解析普通同模块调用与受支持回调目标。 |
| `module_entry_callbacks.py` | 识别委托绑定、解绑、handle/object/callback 配对、未配对清理和 virtual target 路径。 |
| `module_entry_states.py` | 从可达操作生成状态事件，压缩非回调状态模型、条件覆盖和保守的外部未解析效果。 |

### 3.3 确定性源码解析与源码单元服务

| 文件 | 职责 |
|---|---|
| `source_tokens.py` | 对受支持的 C#/C++ 子集分词，建立括号配对、原文位置、字面值投影和分隔符诊断。 |
| `source_declarations.py` | 识别类、成员、外部定义、自由函数、局部/字段声明和声明身份。 |
| `source_flow.py` | 识别 `if`、循环、`switch`、`catch` 等控制范围和控制表达式引用。 |
| `source_preprocessor.py` | 跟踪 `#if/#ifdef/#ifndef/#elif/#else/#endif` 分支及可静态判断的活动状态。 |
| `source_controls.py` | 将语句级、表达式级和预处理控制元数据合并到操作上。 |
| `source_operations.py` | 从 Token 和控制范围中提取赋值、集合变更、调用、短路/三元门控等操作。 |
| `source_parser.py` | 保留稳定解析入口，组装任意 C# 文件、规则文件或 C++ 文件的类、函数、操作、注册宏和分隔符问题。 |
| `source_includes.py` | 提取直接 include，建立 Project/Engine Module 物理边界索引并定位唯一文件来源。 |
| `source_unit.py` | 发现源码所属项目和 Engine，自动选择配套头文件，统一三个 C++ 源码 CLI 的上下文，并分别投影 include、type 和指定函数事实。 |

## 4. 15 个公开 CLI 与 Schema 目录

以下 15 个 `tools/ue_*.py` 是扫描器核心的公开命令行入口：

| CLI | 主要输入 | 单一职责 | Schema |
|---|---|---|---|
| `ue_find_projects.py` | `--search-root` | 发现 `.uproject`，对零个、一个或多个候选给出明确状态。 | `ue-itps.project-discovery.v1` |
| `ue_read_project_descriptor.py` | `--project` | 读取一个 `.uproject` 的紧凑显式声明。 | `ue-itps.project-descriptor.v1` |
| `ue_resolve_engine.py` | `--project`，可选 `--engine-root` | 将 `EngineAssociation` 定位到 Engine，并读取真实 `Build.version`。 | `ue-itps.engine-resolution.v1` |
| `ue_inspect_modules.py` | `--project` | 对账项目声明 Module、Build.cs 与入口宏证据。 | `ue-itps.project-modules.v1` |
| `ue_inspect_targets.py` | `--project` | 发现 Target.cs、检查位置并分类原生 Target 证据。 | `ue-itps.project-targets.v1` |
| `ue_resolve_plugins.py` | `--project`，可选 Engine/Profile 参数 | 在一个显式 Profile 下定位 `.uproject` 的直接 Plugin 引用。 | `ue-itps.project-plugin-references.v1` |
| `ue_classify_project_paths.py` | `--project` | 分类项目根路径名称、位置和文件系统状态。 | `ue-itps.project-paths.v1` |
| `ue_read_plugin_descriptor.py` | `--plugin` | 读取一个 `.uplugin`，校验字段并对账其 Module Build.cs。 | `ue-itps.plugin-descriptor.v2` |
| `ue_inspect_module_rules.py` | `--rules` | 投影一个 Build.cs 的 ModuleRules mutation 与引用。 | `ue-itps.module-rule-relations.v1` |
| `ue_inspect_target_rules.py` | `--target` | 索引一个 Target.cs 的 TargetRules 类、继承、成员变量和函数。 | `ue-itps.target-rule-relations.v1` |
| `ue_inspect_module_entry.py` | `--rules` | 提取一个模块的注册、回调绑定/清理和非回调生命周期状态。 | `ue-itps.module-entry-state.v12` |
| `ue_inspect_cs_function.py` | `--source`、`--function` | 返回任意 `.cs` 中指定名称的全部类成员函数及外部类型与方法引用。 | `ue-itps.cs-function.v1` |
| `ue_list_cxx_includes.py` | `--source`，可选 `--engine-root` | 列出显式 C++ 源码单元的非配套头文件直接 include 与物理来源。 | `ue-itps.cxx-includes.v1` |
| `ue_list_cxx_types.py` | `--source`，可选 `--engine-root` | 索引类型、继承、成员名称和 UE 宏的词法事实。 | `ue-itps.cxx-types.v1` |
| `ue_inspect_cxx_function.py` | `--source`、`--function`，可选 Engine | 返回指定名称的全部定义及各自的外部类型与成员调用。 | `ue-itps.cxx-function.v1` |

`ue_resolve_plugins.py` 的默认 Profile 是 `operation=scan`、`platform=Win64`、`target_type=Editor`。三个 C++ 源码 CLI 不接受手动头文件参数；配套 `.h/.hpp` 必须由同目录同名或 Module `Private` 到 `Public`/`Classes` 的唯一映射自动确定。通用 C# 函数 CLI 只读取显式选择的一个 `.cs`。

## 5. 共享结果契约

所有正常扫描结果由 `common.result_document()` 构造，顶层字段顺序固定为：

```json
{
  "schema_version": "ue-itps.<area>.vN",
  "...模块事实...": {},
  "validation": {
    "status": "ok | warning | error",
    "problem_count": 0,
    "problems": []
  },
  "limits": {
    "responsibility": "该结果负责证明什么",
    "boundaries": ["该结果不能证明什么"]
  }
}
```

关键不变量：

- `schema_version` 必须是第一个字段，`validation` 和 `limits` 必须是最后两个字段。
- 模块内容不能覆盖保留字段 `schema_version`、`validation`、`limits`。
- `validation.status` 由问题严重度计算：存在 `error` 为 `error`；否则存在 `warning` 为 `warning`；否则为 `ok`。
- `problem_count` 始终等于 `problems` 长度。
- `warning` 是完成的非阻断扫描；它与 `ok` 都对应 CLI 退出码 0。
- 每个工具独立维护 Schema。后续层的结果不能嵌入前一层 Schema，也不能被包装成未经定义的“全局事实”。
- JSON 使用 UTF-8 和 `ensure_ascii=False`，路径统一为正斜杠形式；集合输出在实现可控处按规范化路径、名称或源码位置排序。

当前公共契约由 Python `dict` 和测试约束，没有独立 JSON Schema、TypedDict 或 dataclass 模型。因此 Schema 版本是运行时契约标识，还不是可由外部验证器直接消费的模式文件。

## 6. 项目到源码的显式导航数据流

```text
搜索根
  -> ue_find_projects
  -> 唯一 .uproject
       -> ue_read_project_descriptor
       -> ue_resolve_engine
       -> ue_inspect_modules
       -> ue_inspect_targets
       -> ue_resolve_plugins
       -> ue_classify_project_paths
              |
              +-> 显式选择一个 .uplugin
              |     -> ue_read_plugin_descriptor
              |          -> 显式选择一个 Build.cs
              |               -> ue_inspect_module_rules
              |               -> ue_inspect_module_entry
              |
              +-> 显式选择一个 Target.cs
              |     -> ue_inspect_target_rules
              |     -> 从成员索引显式选择函数名
              |     -> ue_inspect_cs_function
              |
              +-> 显式选择一个 .cpp/.cc
                    -> 最近唯一祖先 .uproject
                    -> Engine 与 Module 物理来源上下文
                    -> 自动选择零个或一个配套头文件
                    -> ue_list_cxx_includes
                    -> ue_list_cxx_types
                    -> 从类型成员名显式选择函数名
                    -> ue_inspect_cxx_function

显式选择一个 .cs
  -> 显式选择函数名
  -> ue_inspect_cs_function
```

导航证据只帮助调用方选择下一层输入。例如项目 Module 结果可定位 Build.cs，Plugin 描述符结果可定位 Plugin Module 的 Build.cs，类型结果可列出成员函数名。任何一层都不会自动调用下一层，也不会递归读取已定位的依赖源码。

三个 C++ 源码工具共享相同的加载逻辑，但每次调用都会独立重建上下文。它们：

1. 校验显式 `.cpp/.cc`。
2. 从源码目录向上查找最近且唯一的 `.uproject`。
3. 读取项目描述符并解析 Engine。
4. 建立 Project/Engine Module 物理边界记录。
5. 确定源码 owner 和唯一自动配套头文件。
6. 只把所选源码与唯一头文件作为 C++ 解析输入。
7. 将 include、type 或指定函数分别投影到独立 Schema。

## 7. 确定性解析器与证据边界

### 7.1 JSON

- `.uproject` 和 `Build.version` 使用 `common.read_json()`：要求顶层对象、拒绝重复键、拒绝非标准 JSON 常量，接受 UTF-8 BOM。
- `.uplugin` 使用 `ue_json.read_ue_json()`：允许 UE 描述符中实际存在的行/块注释和尾逗号，拒绝非标准常量，并把重复字段作为可定位诊断；重复字段物化时保留最后一次出现的值。
- 未建模字段被保留或列入清单，不因扫描器尚未认识而自动判定非法。

### 7.2 C#、Build.cs 与 Target.cs

C# 扫描器使用自有轻量词法层，不执行 C#：

- ModuleRules 从确认类的构造函数出发，只跟踪静态可达的同文件辅助方法。
- mutation 归一化为 `set/add/remove/increment/decrement` 等语义操作。
- operand 仅分类为 `literal`、`symbol` 或保留原文的 `expression`。
- ModuleRules 用 `applicability.kind` 和压平的 `control_path` 表示直接/条件适用性。
- TargetRules 只索引已确认或文件名启发式识别的规则类、继承、成员变量和全部词法成员函数，不读取函数体语义。
- 通用 C# 函数工具接受任意 `.cs` 和一个显式函数名，返回全部同名类成员；外部类型来自参数、局部变量、被引用成员字段，以及非调用成员访问中的未绑定类型限定符。
- 方法引用保留同类调用并按首次出现顺序去重；已知类型的根接收者替换为类型表达式，其余成员链保持不变。工具不绑定重载，也不递归展开被调用函数。
- 输出顺序是确定性的源码顺序，不代表 C# 运行顺序或最终有效 UBT 结果。

### 7.3 模块入口

模块入口扫描器会读取所选 Build.cs 父目录下的 `.h/.hpp/.cpp/.cc`，寻找模块注册宏、本地模块类、生命周期入口、普通同模块调用和受支持的委托 API。

- `registration` 是注册宏证据；`module.class` 只有在模块源码中能找到唯一可分析的本地类时才非空。
- `callback_bindings` 支持 function、lambda 和 UFunction 目标，但不跟踪 lambda/UFunction 函数体；已绑定的顶层 `static` 回调也只报告声明。
- 解绑按 delegate source 与 object、callback 或 handle 身份配对；`unmatched_cleanups` 是可达清理证据，不是运行错误判定。
- `state_models` 只公开压缩后的非回调状态结论；具体 RHS、变更值和完整调用清单被有意省略。
- `unresolved_effects` 只保守记录无法解释的外部状态调用，不推断其结果。
- callable 上下文每项上限为 32；超过上限产生诊断，防止路径组合无界增长。
- 分隔符不平衡会产生 error，但尽可能保留可恢复的注册等局部事实。

### 7.4 显式 C++ 源码单元

- include 工具读取直接 include，不读取 include 的内容；配套头文件本身在 `source_unit.header` 表示，不重复列入 `includes`。
- `resolved` include 只表示在已知 Module 物理根中得到唯一文件候选，不表示编译器或 UBT 的有效 include 路径。
- type 工具提供词法类型、继承、成员和相邻 UE 宏索引，不执行 UHT，也不形成完整类型语义。
- function 工具按名称返回全部同名定义；owner、参数、限定符和 `function_id` 是输出事实，不是筛选条件。
- 外部类型来自当前源码单元可见声明；外部方法来自函数体成员调用。被调用方法、继承、重载和依赖源码均不继续展开。

## 8. 静态证据与 Unreal 权威边界

| 问题 | 当前扫描器可提供的静态证据 | 最终权威 |
|---|---|---|
| Engine 身份 | `EngineAssociation` 的解析候选与所选 Engine 的 `Build.version` | 实际启动/构建使用的 Engine、Launcher/构建环境 |
| Module/Target 文件 | 描述符声明、Build.cs/Target.cs 文件位置、注册宏 | UBT 规则程序集与实际 Target/Profile 构建结果 |
| Plugin | `.uproject` 直接声明、描述符物理位置、有限平台/Target 过滤 | UBT 的默认、传递依赖、Configuration 和完整 Plugin 选择 |
| UPROPERTY/UFUNCTION 等宏 | 词法相邻关系与源码位置 | UHT 解析、生成代码与反射注册结果 |
| include | 拼写、条件、唯一物理候选与 owner | 编译器 include 搜索、UBT include path 与实际编译 |
| 模块生命周期 | 注册、受支持回调绑定/清理、保守状态投影 | Editor/程序实际加载顺序、线程、对象状态与运行日志 |
| 资产与配置 | 当前 15 个 CLI 不解析资产图或合并后的配置 | Editor、Asset Registry、Config 合并、Cook/Package |
| 行为正确性 | 局部静态结构和诊断 | 构建、自动化测试、PIE、独立进程、网络和目标平台运行 |

维护者不得把右列权威反向伪装成当前静态 Schema 的字段。未来若接入 UBT/UHT/Editor/运行时证据，应使用独立 Schema，携带采集上下文和证据来源，再由上层显式关联。

## 9. 校验与退出码

所有 CLI 的 `--help` 均为中英双语，并声明以下退出码：

| 退出码 | 含义 | 输出形态 |
|---|---|---|
| `0` | 扫描完成，`validation` 为 `ok` 或 `warning` | stdout JSON |
| `1` | 扫描完成，但 `validation` 为 `error` | stdout JSON，可能包含可恢复的局部事实 |
| `2` | 参数语法、输入或读取失败，扫描未正常开始 | 见下述两类行为 |

退出码 2 的当前行为必须精确区分：

- `ue_list_cxx_includes.py`、`ue_list_cxx_types.py`、`ue_inspect_cxx_function.py`、`ue_inspect_cs_function.py` 捕获输入/读取异常，在 stdout 返回各自 Schema 的结构化错误 JSON：`request.status=failed`、`validation.status=error`，stderr 为空。
- 其余 11 个 CLI 的输入/读取异常调用 `argparse.ArgumentParser.error()`，在 stderr 输出用法和文本错误，不输出正常扫描 JSON。
- 所有 15 个 CLI 的命令行语法错误都由 argparse 处理，使用 stderr 文本并退出 2。

因此，当前实现只保证三个 C++ 源码 CLI 和通用 C# 函数 CLI 的输入/读取失败是结构化结果；不能声称 15 个入口对此完全一致。

## 10. 测试架构与覆盖矩阵

测试使用 Python 标准库 `unittest`。`tests/support.py` 在每个临时目录中创建一个自包含夹具，包括：

- 最小 `Engine/Build/Build.version`、Core/GameplayTags Build.cs 和头文件；
- 一个 `.uproject`、项目 Module Build.cs、Target.cs 和主模块入口；
- 一个项目 Plugin、`.uplugin`、Plugin Build.cs、模块注册、委托绑定和清理；
- 一个 `Private/Feature.cpp` 与通过 `Private -> Public` 规则自动定位的 `Public/Feature.h`；
- CLI 子进程运行器和共享结果信封断言。

该套件不读取 Lyra、不依赖已安装 Unreal Engine、不调用 UBT/UHT/Editor，因而适合快速、可重复地验证扫描器核心契约。

| 测试文件 | 数量 | 当前覆盖 |
|---|---:|---|
| `test_cli_contracts.py` | 5 | 15 CLI 双语帮助、统一信封、严格 JSON、Target 输入失败、4 个源码查询 CLI 的结构化输入失败。 |
| `test_navigation_flow.py` | 1 | 15 个 CLI 组成同一个显式项目到源码导航链，并核对每层路径衔接。 |
| `test_project_scanners.py` | 8 | 项目发现歧义、描述符压缩、Engine/Module/Target 对账、Plugin 名称筛选与显式来源、路径职责边界。 |
| `test_plugin_descriptor.py` | 3 | Plugin Module/依赖、重复字段与缺失 Build.cs、错误后缀。 |
| `test_rule_scanners.py` | 3 | ModuleRules helper/条件、TargetRules 类/变量/函数索引、错误基类时保守失败。 |
| `test_cs_functions.py` | 4 | 普通/Rules C# 函数、外部类型与方法引用、重载和缺失函数。 |
| `test_module_entry.py` | 3 | 注册/绑定/清理、默认模块不虚构状态、分隔符错误保留局部事实。 |
| `test_source_context.py` | 4 | 三个 C++ 源码工具共享上下文、自动头文件、头文件歧义、最近项目歧义。 |
| `test_source_includes.py` | 4 | unit 证据、配套头文件去重、非递归读取、预处理条件。 |
| `test_source_types.py` | 3 | 类型/成员/反射宏、enum/interface 宏归属、参数前置声明排除。 |
| `test_source_functions.py` | 3 | 声明定义关系、外部引用、同名重载稳定 ID、函数不存在的结构化扫描错误。 |
| **合计** | **41** | 当前重建套件全部通过。 |

运行方式：

```powershell
python -m unittest discover -s tests -v
```

仓库当前没有覆盖率工具、覆盖率阈值或 CI 工作流；41 项通过证明已编码断言成立，不等于完整语法、平台或 Unreal 集成覆盖。

## 11. 性能特征

- 所有扫描同步执行，数据结构保存在单进程内存中；没有后台服务、并行扫描或持久缓存。
- `iter_files()` 使用 `os.walk`，跳过 `.git`、`.idea`、`.vs`、`Binaries`、`DerivedDataCache`、`Intermediate`、`Saved`，调用方随后进行确定性排序。
- 项目发现、Build.cs 对账和 Plugin 描述符索引的主要成本与被遍历目录中的文件数量近似线性相关。
- Plugin 定位会为每次调用重新遍历 Project/Engine Plugin 根；虽然只记录声明名称匹配项，仍需枚举目录树。
- 每个源码 CLI 都会重新扫描 Project/Engine 的 Build.cs 来建立 owner 索引，再解析一个 `.cpp/.cc` 和至多一个配套头文件。连续运行 include/type/function 三个工具不会共享索引或 Token。
- 模块入口工具会读取并分词所选模块边界中的全部 `.h/.hpp/.cpp/.cc`，成本随模块源码总量增长。
- 词法解析器为每个读取文件建立完整 Token 列表，内存使用与文本和 Token 数量近似线性相关。
- 每个 callable 最多保留 32 个上下文，用显式上限约束分支传播的组合增长。
- 15 个独立 CLI 进程之间无法共享 Engine 解析、描述符、Build.cs 索引或 Token。当前也没有基准测试来定义可接受的项目规模和延迟预算。

## 12. 已知边界

### 12.1 正确性边界

1. Plugin 解析仅覆盖 `.uproject` 直接引用；不计算 Engine 默认 Plugin、项目默认值或 `.uplugin` 传递依赖闭包。
2. Plugin 适用性只计算平台与 Target allow/deny；Configuration、Program/GameTarget、`HasExplicitPlatforms` 和更深 UBT policy 不进入有效性结论。
3. Module 和 Plugin Build.cs 通过 basename 与目录证据定位；这不是 UBT 最终选择证明。
4. Target 分类只依据 Target.cs 的发现和位置；“无根 Target”不能证明 Blueprint-only，临时/hybrid Target 原因需要 UBT。
5. Engine 注册表、关联和祖先路径只提供静态定位；不证明版本兼容、工具链完整或项目实际使用它成功构建。
6. Build.cs/Target.cs 解析器只覆盖受支持 C# 子集，不执行字符串插值、任意辅助库、文件/环境访问、反射、跨文件继承或完整重载绑定。
7. 调用点控制不会传播到规则 helper；复杂表达式保留为 `expression`，不能当成最终值。
8. 模块入口不是通用调用图：只跟踪受限同模块调用和受支持绑定；lambda、UFunction、顶层 static 回调体、跨模块调用及一般虚派发不展开。
9. 源码类型和函数投影是词法模型，不是完整 C++ 语义；模板、宏、别名、重载、遮蔽和不完整源码可能产生 `warning`、遗漏或保守结果。
10. include 的唯一物理候选不证明依赖必需、Build.cs 声明正确或编译器实际选中。
11. 路径分类不读取目录内容，不判断源码权威、自包含、可重建性或删除安全性。
12. junction、symlink、权限拒绝、注册表多版本歧义和完整 Profile 组合尚未形成系统测试矩阵。

### 12.2 契约边界

1. 公开 Schema 只有版本字符串和运行时 `dict`，没有独立 JSON Schema 或静态类型定义。
2. 11 个传统 CLI 与 4 个源码查询 CLI 的输入/读取失败输出不同；调用方必须同时处理 stderr 文本和结构化 JSON。
3. Schema 保证字段语义与顺序，但绝对 `path_roots`、注册表候选和文件系统状态依赖机器环境，不能假设跨机器字节完全相同。
4. 测试对关键字段做行为断言，但没有为 15 个 Schema 保存完整、路径归一化后的 golden 输出。
5. 内部存在非公开的辅助投影，例如 `source-functions.v1`；只有本文件目录中列出的 15 个 CLI Schema 属于公开命令行契约。

### 12.3 性能边界

1. Engine/Project Plugin 树、Build.cs 树和模块源码会在相关调用中重复遍历。
2. 三个 C++ 源码查询会重复建立相同上下文和 Token，连续查询没有进程内复用。
3. 超大 Engine、Plugin 树或单模块可能带来显著 I/O、内存和启动延迟；当前没有规模基准或回归阈值。
4. 现有 CLI 是短生命周期进程，尚无只读常驻索引、缓存失效键或并发访问模型。

## 13. 扩展规则

1. 新工程问题优先增加一个小服务和薄 CLI；不要扩大现有 CLI 的职责或改变已有 Schema 的含义。
2. 每个公开结果必须使用 `result_document()`，保持 `schema_version -> facts -> validation -> limits`。
3. 新字段若改变消费者解释，应升级该工具 Schema；不得借其他工具版本或里程碑名替代 Schema 版本。
4. 上一层只提供下一层所需的导航事实；自动展开 Plugin 闭包、Module 树、include 或调用函数必须是新的显式工具。
5. 文件遍历、候选选择和数组输出必须具有稳定排序；路径必须通过共享规范化函数输出。
6. 解析器遇到未知语法或不透明效果时输出诊断、`unclassified` 或 `unresolved`，不得执行源码或猜测有效值。
7. 静态事实必须带来源路径、行号或描述符指针；不能定位证据的结论不得升级为已确认事实。
8. UBT/UHT/Editor/运行时接入必须使用独立 Schema 和来源上下文，不得覆写静态扫描结果。
9. 新功能至少扩展自包含夹具、直接服务测试和 CLI 契约测试；若改变导航入口，还要更新 15 CLI 流程测试及本目录。
10. 扫描器核心保持只读。任何生成、修改或归档能力必须与 15 个扫描 CLI 分离。

## 14. 优先后续工作

### P0：冻结并统一公共契约

1. 为 15 个公开 Schema 增加版本化 JSON Schema 或等价静态模型，并验证保留字段、必需字段、枚举和向后兼容性。
2. 明确统一输入/读取失败契约：优先让全部 CLI 使用结构化错误 JSON，同时保留 argparse 对纯语法错误的退出码 2 行为。
3. 为自包含夹具增加路径归一化后的完整 golden 输出，防止字段删除、重命名和顺序漂移只靠局部断言漏检。
4. 补齐注册表歧义、junction/symlink、权限失败、Plugin Profile 组合、复杂 C#/C++ 声明和预处理分支测试。

### P1：建立可量化的性能与复用边界

1. 增加小/中/大项目基准，分别记录 Plugin 索引、Build.cs 索引、模块入口和三个 C++ 源码查询的时间与峰值内存。
2. 将 Engine、描述符、Build.cs owner 索引和 Token 缓存抽象为只读会话对象，并以根路径、文件元数据和 Engine 身份定义明确失效键。
3. 让同一进程中的 include/type/function 查询复用同一个源码上下文，同时保持三个公开 Schema 独立。
4. 在性能优化后验证排序、诊断和证据边界不因缓存或并发发生变化。

### P2：扩展权威层而不污染静态层

1. 设计独立的 UBT 规则结果 Schema，将“源码声明”与“给定 Target/Profile 的有效规则”明确关联。
2. 按相同原则设计 UHT、Editor/Asset Registry 和运行时证据适配层，并记录工具版本、Profile、平台和采集时间。
3. 只有在权威分层稳定后，再考虑 Plugin 传递闭包、Config 合并和资产入口等新扫描能力。
4. 若提供常驻 MCP/服务入口，继续暴露同样的小工具边界，不增加隐式全项目聚合扫描。
