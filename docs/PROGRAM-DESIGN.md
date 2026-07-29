# UE ITPS 程序设计

本文说明 UE ITPS 当前实现的职责、架构、公开契约、测试策略和扩展规则。公开使用方式以仓库根目录的 `README.md` 为准。

## 1. 设计目标

UE ITPS 解决的是“如何从一个明确的 Unreal Engine 项目或源码入口，获得稳定、可追溯、适合程序消费的静态事实”。

核心原则：

1. **只读**：不修改项目、资产、配置、Engine 或系统注册信息。
2. **明确选择**：每次处理一个明确输入；遇到歧义时报告问题，不猜测目标。
3. **小职责**：每个 CLI 回答一个聚焦问题，不生成隐式全项目总报告。
4. **证据优先**：事实携带路径、行号、描述符指针或来源类型。
5. **保守失败**：无法证明的内容保持 `warning`、`error`、`unresolved` 或边界说明。
6. **独立 Schema**：每个公开 CLI 保持自己的版本和语义，不把后续结果嵌入前一层。
7. **确定性**：文件遍历、候选选择和数组输出使用稳定顺序。

## 2. 系统边界

系统提供静态文件和源码证据，不承担以下权威职责：

| 问题 | UE ITPS 提供 | 最终权威 |
|---|---|---|
| Engine 身份 | 关联值、候选根目录、`Build.version` | 实际构建或启动环境 |
| Module / Target | 描述符、Build.cs、Target.cs、注册宏 | UnrealBuildTool |
| UE 反射 | 类型、Interface 候选、全局变量、自由函数、成员锚点和相邻宏的词法事实 | UnrealHeaderTool |
| include | 拼写、条件、唯一物理候选和 owner | 编译器与 UBT include path |
| Plugin | `.uproject` 直接声明和物理描述符 | 完整 UBT Plugin 选择 |
| 模块生命周期 | 注册、受支持回调、清理和状态投影 | Editor 或程序运行时 |
| 资产和配置 | 当前核心 CLI 不处理 | Editor、Asset Registry、配置合并 |
| 行为正确性 | 静态结构和诊断 | 构建、自动化测试和目标平台运行 |

因此，任何新功能都不得把静态推断包装成编译、UHT、Editor 或运行时结论。

## 3. 公开表面

项目公开 16 个 CLI，分为四个范围：

### 3.1 项目导航

- `ue_find_projects.py`
- `ue_read_project_descriptor.py`
- `ue_resolve_engine.py`
- `ue_inspect_modules.py`
- `ue_inspect_targets.py`
- `ue_list_project_cxx_sources.py`
- `ue_resolve_plugins.py`
- `ue_classify_project_paths.py`

这一层负责发现和定位，只输出后续明确选择所需的证据。

### 3.2 Plugin 与构建规则

- `ue_read_plugin_descriptor.py`
- `ue_inspect_module_rules.py`
- `ue_inspect_target_rules.py`
- `ue_inspect_cs_function.py`

这一层读取一个明确 `.uplugin`、Build.cs、Target.cs 或普通 C# 文件。规则解析器不执行 C#，只投影受支持的声明、控制条件和引用。

### 3.3 模块入口

- `ue_inspect_module_entry.py`

该工具从一个明确 Build.cs 导航到同一 Module 的源码边界，检查注册宏、模块类、受支持回调绑定与清理、保守状态模型、条件覆盖和未解析外部效果。

### 3.4 C++ 源码事实

- `ue_list_cxx_includes.py`
- `ue_list_cxx_types.py`
- `ue_inspect_cxx_function.py`

三个工具共享源码上下文和 `source_unit` 约定，但按需加载各自需要的分析：

- include 工具只提取直接 include、预处理条件和物理来源。
- type 工具按类别输出 Class、Struct、Enum、Interface 候选、Global Variable、Free Function，以及 Class/Struct 的成员锚点和相邻 UE 宏。类型锚点区分声明/定义，并为嵌套 Class/Struct 保留词法 owner。
- function 工具按函数名返回全部定义、声明关系、外部类型和成员调用。

它们只读取明确选择的 `.h/.hpp/.cpp/.cc` 以及至多一个自动推导的同名配对文件，不递归读取 include。实现文件会寻找头文件，头文件也会寻找实现文件。

## 4. 实现分层

```text
公开 CLI
  │  参数、错误通道、JSON 输出
  ▼
领域服务
  │  项目、Engine、Plugin、规则、模块入口、源码事实
  ▼
共享解析与投影
  │  JSON、路径、Token、声明、控制流、预处理、证据
  ▼
只读文件系统
```

### 4.1 CLI 适配层

根目录 `tools/ue_*.py` 只负责：

- 声明中英双语参数和帮助。
- 将字符串参数转换为明确路径或选择值。
- 调用一个领域服务。
- 以 UTF-8 输出 JSON。
- 根据验证状态返回退出码。

业务解析不应堆积在 CLI 文件中。

### 4.2 项目与描述符服务

主要模块：

- `common.py`：公共参数解析器、输出封装、严格 JSON、路径规范化和文件遍历。
- `discovery.py`：`.uproject` 发现和最近项目选择。
- `descriptor.py`：项目描述符投影。
- `engine.py`：Engine 根目录与版本解析。
- `code_inventory.py`：Module 和 Target 文件对账。
- `project_cxx_sources.py`：项目与项目 Plugin 的 C++ 文件分组和生成文件过滤。
- `plugins.py`：直接 Plugin 声明定位。
- `structure.py`：项目根路径分类。
- `plugin_descriptor.py`：`.uplugin` 校验和 Module 对账。
- `ue_json.py`：支持注释、尾随逗号及重复字段记录的 Unreal 描述符读取。

通用 JSON 使用严格读取器；只有明确需要 Unreal 描述符兼容性的读取流程使用 `ue_json.py`。

### 4.3 C# 与规则服务

主要模块：

- `source_tokens.py`：C#/C++ 共用词法 Token 和分隔符诊断。
- `source_parser.py`：类、函数、注册宏及规则文件入口解析。
- `source_declarations.py`：类型、成员和文件/命名空间级自由函数声明。
- `source_operations.py`：赋值、调用和表达式操作。
- `source_flow.py`、`source_controls.py`：控制路径和条件元数据。
- `rule_source.py`：ModuleRules 与 TargetRules 公开投影。
- `cs_source.py`：一个明确 C# 成员函数的外部引用投影。

规则解析器只覆盖实现中明确建模的 C# 子集。字符串插值、反射、任意辅助程序集、跨文件继承和运行时条件不会被执行或猜测。

### 4.4 模块生命周期服务

模块入口实现拆分为：

- `module_entry.py`：输入校验、源码加载、模块类选择和最终组装。
- `module_entry_callables.py`：同模块 callable 与有限调用上下文。
- `module_entry_callbacks.py`：回调绑定、句柄、清理和虚函数入口。
- `module_entry_states.py`：状态转换、闭合性、条件覆盖和未解析效果。
- `module_entry_common.py`：共享身份、路径、条件和证据操作。

分析范围是受限的同模块静态关系，不是通用调用图。Lambda、UFunction、跨模块调用、顶层静态回调体和一般虚派发均按公开边界保守处理。

### 4.5 C++ 源码服务

主要模块：

- `source_context.py`：校验源码、发现最近项目、推导头文件、建立根路径和 Module 上下文。
- `source_includes.py`、`source_include_facts.py`：include 提取、定位和公开投影。
- `source_type_facts.py`：类型、Interface 候选、全局变量、自由函数、成员锚点和宏投影。
- `source_function_facts.py`：函数关系、稳定 ID、外部类型和调用投影。
- `source_fact_common.py`、`source_signatures.py`：共享证据、声明和签名规范化。
- `source_preprocessor.py`：预处理分支条件。
- `source_unit.py`：保留兼容导入入口。

include、type 和 function 分析按需加载。公共 Schema 独立，内部共享不应导致某个工具无条件执行其他工具的全部分析。

## 5. 导航与选择规则

### 5.1 项目

1. 未知 `.uproject` 时先运行项目发现。
2. 只有一个候选时才能继续。
3. 多个候选属于歧义，工具返回阻断问题。
4. Module、Target、Plugin 和规则文件必须来自用户输入或上一层证据。

### 5.2 Plugin

1. 项目描述符只报告直接声明。
2. Plugin 定位使用明确 Profile：operation、platform、target type。
3. 同名描述符同时存在时保留一个主来源和全部备用来源。
4. `.uplugin` 读取不会递归展开 Plugin 依赖闭包。

### 5.3 C# 函数

函数名是唯一选择器。结果返回所选文件中全部同名类或结构体成员；owner、参数、限定符和签名是输出事实，不是额外选择器。

### 5.4 C++ 源码

1. 输入必须是一个明确 `.h/.hpp/.cpp/.cc`。
2. 最近祖先层级必须只存在一个 `.uproject`。
3. 配对文件按同目录及 `Private <-> Public/Classes` 同名映射双向推导。
4. 零个配对候选保留对应 `source_unit` 字段为 `null`；多个候选返回 `null` 和 warning。
5. 函数工具按名称返回全部同名定义，并生成稳定 `function_id`。

## 6. 公共输出契约

所有正常结果由 `result_document()` 组装，顶层顺序固定：

```text
schema_version
<领域事实>
validation
limits
```

保留字段 `schema_version`、`validation`、`limits` 不允许被领域内容覆盖。

### 6.1 Validation

`validation_result()` 按问题最高严重级别确定状态：

- 包含 `error`：`error`
- 否则包含 `warning`：`warning`
- 无以上问题：`ok`

`problem_count` 必须等于 `problems` 的实际长度。warning 表示扫描完成且问题非阻断，不能在调用侧静默改写成 ok。

### 6.2 Limits

每个结果必须说明：

- `responsibility`：该 Schema 负责回答的问题。
- `boundaries`：该结果不能证明的内容。

边界是公共契约的一部分，不是可省略的说明文字。

### 6.3 退出码与错误通道

| 退出码 | 语义 |
|---:|---|
| `0` | 扫描完成，Validation 为 `ok` 或 `warning` |
| `1` | 扫描完成，Validation 为 `error` |
| `2` | 参数、输入或读取失败 |

所有 CLI 的参数语法、输入与读取失败统一在 stdout 返回 JSON，stderr 保持为空。公共信封顺序为：

```text
schema_version
request
validation
limits
```

`request.status` 固定为 `failed`；`request.kind` 区分 `argument` 与 `input`。公共参数解析器负责把缺少参数、未知参数和非法枚举转换为 `argument-error`；CLI 在完成参数解析后报告的路径、格式或读取问题转换为 `input-error`。聚焦源码 CLI 可以保留更具体的问题码，但必须使用相同信封。

### 6.4 正式 JSON Schema

`schemas/` 使用 JSON Schema Draft 2020-12：

- `common.schema.json` 定义共享 `validation`、`limits`、`request` 和失败文档。
- 每个公开 CLI 拥有一个同名 `.schema.json`，通过 `oneOf` 分别约束领域结果与请求失败结果。
- JSON Schema 的 `$id` 与文件名用于引用和验证，不替代 CLI 输出中的 `schema_version`。
- 核心 CLI 不依赖 Schema 校验库；测试通过 `requirements-dev.txt` 中的 `jsonschema` 验证所有结果。

正式 Schema 当前严格锁定顶层字段、公共信封、主要标量类型和结果类别；复杂领域对象的内部事实仍由版本化实现、针对性断言和后续约束共同维护。

## 7. 路径、证据与确定性

- 公共绝对根路径只在对应 `path_roots` 或领域根字段中记录。
- 根目录内证据优先使用规范化相对路径。
- 源码证据记录文件单元和行号。
- 描述符证据使用 JSON Pointer。
- 文件遍历跳过 `.git`、`.idea`、`.vs`、`Binaries`、`DerivedDataCache`、`Intermediate` 和 `Saved`。
- 候选和事实数组在输出前稳定排序。
- 物理文件存在只证明静态候选，不证明 UBT、编译器或运行时实际采用。

## 8. 测试设计

测试使用 Python 标准库 `unittest`。`tests/fixture.py` 在临时目录中建立：

- 最小 `Engine/Build/Build.version`
- Core 与 GameplayTags 的最小 Build.cs 和头文件
- 一个 `.uproject`、项目 Module、Target.cs 和主模块注册
- 一个项目 Plugin、`.uplugin`、Build.cs、回调绑定和清理
- 一组 `Private .cpp -> Public .h` 的 C++ 类型与函数
- 统一 CLI 子进程运行器和输出外层断言

测试不读取 Lyra，不依赖已安装 Unreal Engine，不调用 UBT/UHT/Editor，也不修改真实项目。

当前 45 项测试分布：

| 模块 | 数量 | 目标 |
|---|---:|---|
| `test_contract_surface.py` | 8 | CLI 清单、正式 Schema、帮助、退出码和统一 JSON 错误信封 |
| `test_project_layer.py` | 10 | 项目级发现、导航事实和项目 C++ 源码清单 |
| `test_build_layer.py` | 9 | Plugin、规则、C# 和模块入口 |
| `test_source_layer.py` | 10 | C++ 上下文、include、类型和函数 |
| `test_boundary_cases.py` | 7 | 歧义、损坏输入、保守失败与备用来源 |
| `test_navigation_workflow.py` | 1 | 16 个 CLI 的端到端显式导航 |

执行方式：

```powershell
python -m unittest discover -s tests -v
```

测试目标是锁定公开行为和关键失败边界，不锁定内部模块拆分。内部重构只要 Schema、语义、证据和错误行为不变，就不应要求重写无关测试。

## 9. 扩展规则

新增或修改能力时必须遵循：

1. 新问题优先新增小领域服务和薄 CLI，不扩大现有 CLI 的职责。
2. 新公开结果必须使用 `result_document()`。
3. 改变消费者解释方式时升级该工具自己的 Schema。
4. 不递归展开新的依赖、include 或调用关系，除非新增明确工具与边界。
5. 未知语法或不透明效果输出诊断，不执行源码，也不猜测最终值。
6. 每个事实保留可定位证据；无法定位的结论不能升级为确认事实。
7. 新功能至少增加成功路径、失败路径和 CLI 契约测试。
8. 改变导航入口时同步更新完整导航测试和两份文档。
9. UBT、UHT、Editor、Asset Registry 或运行时证据必须使用独立 Schema 和采集上下文。
10. 核心扫描器继续保持只读；生成、修改和归档能力必须与这 16 个 CLI 分离。

## 10. 已知限制

- 正式 JSON Schema 已覆盖公共信封和稳定领域字段，但复杂嵌套事实尚未全部收紧为封闭类型。
- 未生成 16 个 Schema 的完整 golden 文件，当前测试以 Schema 校验、关键字段和行为断言为主。
- Engine、Plugin 和 Build.cs 树在不同 CLI 进程间会重复扫描。
- 三个 C++ 工具不会跨进程复用上下文或 Token。
- 大型 Engine、Plugin 树或 Module 可能产生明显 I/O 和内存开销。
- 当前没有覆盖率阈值、性能基准或持续集成配置。
- junction、symlink、权限失败、注册表多版本歧义和完整 Plugin Profile 组合尚未形成系统矩阵。

这些限制应在新增功能时显式处理，不能通过扩大静态结论或弱化验证状态来隐藏。
