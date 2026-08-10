# UE ITPS 程序设计

本文描述 UE ITPS 当前实现的职责、公开契约、内部边界、测试策略和扩展规则。面向使用者的命令和示例以仓库根目录的 `README.md` 为准。

## 1. 目标与非目标

UE ITPS 的目标是：从调用方明确选择的 Unreal Engine 项目或源码入口出发，生成稳定、可追溯、适合程序消费的静态事实。

设计原则：

1. **只读**：21 个正式 CLI 不修改项目、Engine、资产、配置或注册表。
2. **明确选择**：多个候选意味着歧义，不能由工具猜测目标。
3. **单一职责**：每个 CLI 只回答一个聚焦问题。
4. **证据优先**：事实尽量携带路径、行号、描述符指针或来源。
5. **保守失败**：不能证明的内容保持 warning、error、unresolved 或边界说明。
6. **稳定工具标识**：每个 CLI 的 `schema_version` 只保存工具名，不携带独立版本号，并拥有同名正式 Schema。
7. **确定性**：目录遍历、候选选择、事实数组和 JSON 序列化保持稳定顺序。

非目标：

- 不执行 Build.cs、Target.cs 或 C++。
- 不替代 UBT、UHT、Editor、编译器或运行时。
- 不构建编译器级符号表、有效 UBT Profile、完整 include 图或跨文件调用图。
- 不从物理文件存在推导构建、运行或删除安全结论。

## 2. 系统组成

仓库当前有三类能力，必须保持边界清晰：

| 类别 | 数量 | 契约 |
|---|---:|---|
| 正式只读 CLI | 21 | 稳定 JSON、统一错误信封、纯工具名 `schema_version`、正式 Schema |
| JSON Schema | 22 | 21 个 CLI Schema，加 1 个公共 Schema |
| Lyra 辅助脚本 | 3 | 本地证据采集流程，不属于正式 CLI 契约，可能写入 `.planning/evidence/` |

`LyraStarterGame/` 和 `ExternalProjects/` 是可选参考输入，不是正式工具运行或自动化测试的依赖。

## 3. 架构

正式工具分为四层：

```text
sourcetools/ue_*.py
    │  参数、双语帮助、退出码
    ▼
sourcetools/ue_project_tools/
    │  项目、描述符、规则、Module、C++ 领域服务
    ▼
共享解析与输出组件
    │  严格 JSON、UE JSON、Token、源码上下文、Validation
    ▼
schemas/
       公共 Schema 与每个 CLI 的正式 Schema
```

### 3.1 CLI 入口层

`sourcetools/ue_*.py` 负责：

- 声明中英双语参数和帮助。
- 接受一个明确入口及少量选择条件。
- 调用一个聚焦的领域服务。
- 将结果稳定序列化到 stdout。
- 根据请求失败或 Validation 选择退出码。

入口层不承担复杂领域解析，也不组合隐式的全项目报告。

### 3.2 领域服务层

`sourcetools/ue_project_tools/` 的模块族：

| 模块族 | 职责 |
|---|---|
| `discovery.py`、`descriptor.py`、`engine.py` | 项目发现、描述符投影、Engine 解析 |
| `code_inventory.py`、`project_cxx_sources.py` | Module、Target 和项目 C++ 源码清单 |
| `plugins.py`、`plugin_descriptor.py` | Plugin 定位、静态依赖图与单个 `.uplugin` 对账 |
| `rule_source.py`、`cs_source.py` | ModuleRules、TargetRules 和 C# 成员投影 |
| `module_entry*.py` | Module 注册、回调、清理和生命周期状态 |
| `source_context.py`、`source_includes.py` | C++ 源码单元和 include 来源 |
| `source_type_facts.py` | 类型、成员、接口候选、全局变量和自由函数 |
| `source_function_*.py` | 函数身份、声明关系和外部符号 |
| `syntax_tree.py` | 基于 Tree-sitter 的 UE C++ / C# 语法前端与宏归一化 |
| `dependency_graph.py`、`project_graph.py` | 类型依赖、循环、继承、反向影响和局部函数流程 |
| `tool_pool.py` | 项目工具池注册表与能力发现 |

领域服务只处理当前工具声明的证据边界，不递归扩展新的依赖、include 或调用关系。

### 3.3 共享解析层

共享组件提供：

- 严格 JSON 和 Unreal 描述符 JSON 读取。
- 路径规范化及生成目录过滤。
- C#、C++ 的 Tree-sitter AST，以及词法 Token、声明、条件和操作投影。
- gdep 思路改写的确定性依赖图、循环检测和反向影响遍历。
- 源码单元伴随文件推导。
- 统一 Validation、Limits 和请求失败信封。
- 稳定 JSON 序列化。

共享语法能力可以复用，但不能让一个 CLI 输出另一个 CLI 才负责解释的领域结论。

### 3.4 Schema 层

`schemas/` 使用 JSON Schema Draft 2020-12：

- `common.schema.json` 定义共享 `validation`、`limits`、`request` 和错误文档。
- 21 个 CLI 各有一份同名 Schema。
- 每个 CLI Schema 使用 `oneOf` 区分领域结果和请求失败结果。
- `schema_version` 的值固定为不含版本后缀的工具名，并与 Schema 文件名对应。

## 4. 显式导航模型

项目级工具负责发现和定位，文件级工具负责检查一个明确入口：

```text
search root
└─ .uproject
   ├─ descriptor / engine / modules / targets / paths / C++ inventory
   ├─ direct plugin reference
   │  └─ selected .uplugin
   │     └─ selected Build.cs
   │        ├─ ModuleRules
   │        └─ Module entry
   └─ selected Target.cs or ordinary .cs
      └─ selected function name

selected .h/.hpp/.cpp/.cc
├─ direct includes
├─ type and declaration anchors
└─ selected function name
```

导航规则：

1. 项目发现遇到多个 `.uproject` 时返回歧义错误。
2. `.uproject` Plugin 声明先解析直接描述符，再将可读 `.uplugin` 声明投影为静态传递依赖图。
3. `.uplugin` 提供 Build.cs 候选和一跳依赖图；规则与 C++ 仍由聚焦探针分析。
4. TargetRules 索引先列出函数，再由调用方选择一个函数名。
5. C++ 类型工具先提供成员函数锚点，再由调用方选择函数名。
6. 后续工具结果保持独立，不嵌入前一层 Schema。

## 5. 公共输出契约

### 5.1 文档形状

领域结果：

```text
schema_version
<领域事实>
validation
limits
```

参数、输入或读取失败：

```text
schema_version
request
validation
limits
```

`result_document()` 禁止领域内容覆盖 `schema_version`、`validation` 或 `limits`。

### 5.2 Validation

`validation_result()` 按最高严重级别计算状态：

- 存在 error：`error`
- 否则存在 warning：`warning`
- 没有问题：`ok`

`problem_count` 必须等于 `problems` 的实际长度。warning 表示扫描已经完成，但存在非阻断问题；调用方不能将其静默改写为 ok。

### 5.3 Limits

每个结果必须包含：

- `responsibility`：当前结果负责回答的问题。
- `boundaries`：当前结果不能证明的内容。

边界是公共契约的一部分，不是可以省略的说明文字。

### 5.4 退出码与通道

所有正式 CLI 将 JSON 写入 stdout，并保持 stderr 为空。

| 退出码 | 语义 |
|---:|---|
| `0` | 扫描完成，Validation 为 `ok` 或 `warning` |
| `1` | 扫描完成，Validation 为 `error` |
| `2` | 参数、输入或读取失败 |

参数解析失败使用 `request.kind: argument`。路径、后缀、格式或读取失败使用 `request.kind: input`。已经进入领域扫描后发现阻断问题时保留领域事实并返回退出码 `1`。

### 5.5 JSON 读取

- `.uproject`、`Build.version` 等通用输入使用严格 JSON。
- 严格读取拒绝重复键、`NaN` 等非标准常量和非对象根值。
- `.uplugin` 使用独立 Unreal JSON 读取器，允许注释和尾随逗号。
- `.uplugin` 重复字段保留最后值，同时产生带描述符指针的 Validation 问题。

## 6. 项目与构建事实

### 6.1 项目发现

项目发现返回 `not-found`、`selected` 或 `ambiguous`。生成目录和本地状态目录不参与候选发现。工具只报告候选，不解析项目内容。

### 6.2 描述符和 Engine

项目描述符工具投影已建模字段，并保留未建模顶层字段。Engine 解析将 `EngineAssociation` 视为关联键，通过显式覆盖、祖先 Engine 或平台机制定位根目录，再读取 `Build.version` 作为版本证据。

Engine 定位成功不证明项目能够构建或运行。

### 6.3 Module、Target 和 Plugin

- Module 工具对账 `.uproject` 声明、Build.cs 候选和注册宏。
- Target 工具发现 Target.cs 位置，只报告原生 Target 证据。
- 项目 C++ 清单按物理 Build.cs 祖先、Plugin 和可见性分组。
- Plugin 解析只处理 `.uproject` 的直接声明和显式 Profile。
- `.uplugin` 工具只读取选中的描述符及其 Source/Platforms 下的 Build.cs 候选。

物理位置和命名约定是证据，不是 UBT 有效配置结论。

### 6.4 C# 规则

- ModuleRules 工具投影受支持的设置变更、操作、操作数和控制条件。
- TargetRules 工具只索引类、继承、成员变量和成员函数。
- C# 函数工具按函数名返回全部同名成员，并列出局部可观察的外部类型和方法。

这些结果是词法投影，不执行 C#，不展开被调用函数，也不推断最终 UBT 值。

### 6.5 Module 生命周期

Module 入口工具从 Build.cs 确定 Module 边界，报告：

- 注册宏及 Module 类。
- 受支持的回调绑定。
- 能按委托源和对象、回调或句柄配对的清理。
- 未匹配清理。
- 非回调状态模型。
- 条件覆盖和已知不透明效果。

结果是保守静态模型，不证明加载顺序、线程、回调时机或运行时状态。

## 7. C++ 源码模型

三个 C++ CLI 接受 `.h`、`.hpp`、`.cpp` 和 `.cc`。

伴随文件选择：

1. 同目录同名、相反类型文件。
2. 常规 `Private ↔ Public/Classes` 同名映射。
3. 唯一候选组成源码单元。
4. 没有候选时只扫描选中文件。
5. 多个候选时不选择，并返回 warning。

职责分离：

- include 工具只报告直接 include、条件和物理来源；伴随头文件 include 由 `source_unit.header` 表示。
- 类型工具报告类、结构体、枚举、接口候选、成员、全局变量和自由函数锚点。
- 函数工具只返回指定名称的全部定义、声明关系和外部符号候选。

任何 C++ 工具都不会递归读取 include，不会跟踪被调用函数，也不会建立项目级符号 ID。

## 8. 测试设计

自动化测试使用 Python `unittest`，Schema 校验使用 `jsonschema`。

`tests/support.py` 为每个测试创建独立临时工作区，其中包含：

- 最小 `Engine/Build/Build.version`。
- Core 和 GameplayTags 的最小 Build.cs 与头文件。
- 一个 `.uproject`、Runtime Module、Game Target 和 Editor Target。
- 一个项目 Plugin、`.uplugin`、Build.cs、注册、回调绑定和清理。
- 一组 `Private .cpp ↔ Public .h` C++ 类型与函数。
- CLI 子进程执行器和 Draft 2020-12 Schema 校验器。

测试子进程设置 `PYTHONUTF8=1`，确保双语帮助和 JSON 在不同 Windows 本地编码下仍以 UTF-8 验证。

当前共 57 项：

| 模块 | 数量 | 目标 |
|---|---:|---|
| `test_cli_contracts.py` | 15 | 公共 CLI、Schema、帮助、错误信封、退出码、严格 JSON |
| `test_project_navigation.py` | 14 | 项目级发现、导航、Engine、Plugin、路径和源码清单 |
| `test_build_and_module.py` | 12 | `.uplugin`、规则、C# 函数和 Module 生命周期 |
| `test_cxx_analysis.py` | 13 | 源码单元、include、类型、接口、函数和符号 |
| `test_end_to_end_workflow.py` | 3 | 全部 CLI 导航、重复扫描确定性和只读性 |

测试原则：

- 每个 CLI 的领域结果和失败结果都通过对应 Schema。
- 成功路径、失败路径和歧义边界分别验证。
- 临时夹具不读取 Lyra 或外部项目。
- 测试不调用 UBT、UHT 或 Editor。
- 测试锁定公共行为，不锁定内部模块拆分。
- 端到端测试对比运行前后文件哈希，验证正式流程保持只读。

执行方式：

```powershell
python -m unittest discover -s tests -v
```

## 9. Lyra 辅助流程边界

三个 Lyra 辅助脚本不属于正式 CLI：

- `query_lyra_asset_registry.py` 依赖 Unreal Python，并读取指定资产及直接依赖。
- `new_lyra_baseline_fingerprint.ps1` 为选定 Lyra 文件生成 SHA-256 清单与摘要。
- `archive_lyra_run.ps1` 将运行日志和上下文归档为不可覆盖的证据目录。

它们可能写入 `.planning/evidence/`，其验证、版本和副作用必须单独管理。不得将它们的运行时或资产结论合并进 21 个静态 CLI 的 Schema。

## 10. 扩展规则

新增或修改正式能力时：

1. 优先新增小型领域服务和薄 CLI，不扩大现有 CLI 的职责。
2. 新结果必须使用公共结果组装器。
3. 消费者解释方式变化时，只更新受影响工具的同名 Schema；工具标识保持不变。
4. 不递归扩展依赖、include 或调用关系，除非新增独立工具和边界。
5. 未知语法或不透明效果输出诊断，不执行源码，也不猜测最终值。
6. 每项事实保留可定位证据；无法定位的结论不能升级为确认事实。
7. 新功能至少具有成功、失败和 Schema 契约测试。
8. 改变导航入口时同步更新端到端测试、README 和本文。
9. UBT、UHT、Editor、Asset Registry 或运行时证据使用独立 Schema 和采集上下文。
10. 生成、修改和归档能力必须与正式只读 CLI 分离。

## 11. 已知限制

- 部分复杂 Schema 允许嵌套事实扩展属性，未锁定所有内部字段。
- 没有为所有成功结果维护完整 golden 文件；测试以 Schema 和关键语义断言为主。
- Engine、Plugin 和 Build.cs 树可能在不同 CLI 进程间重复扫描。
- C++ 工具不跨进程复用源码上下文或 Token。
- 大型 Engine、Plugin 树或 Module 可能产生明显 I/O 与内存开销。
- 当前没有覆盖率阈值、性能基准或持续集成配置。
- junction、symlink、权限失败、注册表多版本歧义和完整 Plugin Profile 组合尚未形成系统矩阵。

这些限制必须通过明确诊断和边界说明处理，不能通过扩大静态结论或弱化 Validation 隐藏。
