# UE ITPS 程序设计

本文记录 UE ITPS 当前实现的职责、架构、公开契约、测试策略和扩展规则。面向使用者的命令与示例以仓库根目录的 `README.md` 为准。

## 1. 目标

UE ITPS 解决的问题是：从一个明确选择的 Unreal Engine 项目、描述符、规则文件或 C++ 源码入口出发，获得稳定、可追溯、适合程序消费的静态事实。

核心原则：

1. **只读**：不修改项目、资产、配置、Engine 或注册表。
2. **明确选择**：遇到多个候选时报告歧义，不猜测目标。
3. **小职责**：每个 CLI 回答一个聚焦问题。
4. **证据优先**：事实保留路径、行号、描述符指针或来源类型。
5. **保守失败**：无法证明的内容保持 warning、error、unresolved 或边界说明。
6. **独立版本**：每个 CLI 拥有自己的 `schema_version` 和正式 Schema。
7. **确定性**：遍历、候选选择和输出数组使用稳定顺序。

## 2. 系统边界

UE ITPS 输出的是静态文件和源码证据，不承担 Unreal 权威工具的职责。

| 问题 | UE ITPS 提供 | 最终权威 |
|---|---|---|
| Engine 身份 | 关联值、候选目录、`Build.version` | 实际构建或启动环境 |
| Module / Target | 描述符、Build.cs、Target.cs、注册宏 | UnrealBuildTool |
| UE 反射 | 类型、宏、接口候选和成员锚点 | UnrealHeaderTool |
| include | 拼写、条件、物理候选和 owner | 编译器与 UBT include path |
| Plugin | `.uproject` 直接声明和物理描述符 | 完整 UBT Plugin 选择 |
| Module 生命周期 | 注册、受支持回调、清理和状态投影 | Editor 或程序运行时 |
| 行为正确性 | 静态结构与诊断 | 构建、自动化测试和目标平台运行 |

任何新功能都不得把静态推断包装成编译、UHT、Editor 或运行时结论。

## 3. 架构

系统分为四层。

```text
tools/ue_*.py
    │  参数、帮助、退出码
    ▼
tools/ue_project_tools/
    │  项目、描述符、规则、Module、C++ 领域服务
    ▼
共享解析与输出组件
    │  严格 JSON、UE JSON、Token、源码上下文、Validation
    ▼
schemas/
       正式 JSON Schema 契约
```

### 3.1 CLI 入口层

`tools/ue_*.py` 只负责：

- 定义中英双语参数与帮助。
- 将路径和选择条件传给一个领域服务。
- 把结果序列化到 stdout。
- 按 Validation 或请求失败选择退出码。

入口层不实现领域解析，不组合隐式全项目报告。

### 3.2 领域服务层

`tools/ue_project_tools/` 的主要职责：

| 模块族 | 职责 |
|---|---|
| `discovery.py`、`descriptor.py`、`engine.py` | 项目发现、描述符投影与 Engine 解析 |
| `code_inventory.py`、`project_cxx_sources.py` | Module、Target 与项目 C++ 文件清单 |
| `plugins.py`、`plugin_descriptor.py` | 直接 Plugin 定位与 `.uplugin` 对账 |
| `rule_source.py`、`cs_source.py` | Build.cs、Target.cs 和普通 C# 成员投影 |
| `module_entry*.py` | Module 注册、回调、清理和状态模型 |
| `source_context.py`、`source_includes.py` | C++ 源码单元、include 定位与 owner |
| `source_type_facts.py` | 类型、接口候选、全局变量、自由函数和成员锚点 |
| `source_function_*.py` | 同名函数索引、声明关系与外部引用 |

领域服务只处理当前工具声明的证据边界，不递归扩展新的依赖、include 或调用图。

### 3.3 共享解析层

共享组件提供：

- 严格 JSON 与 Unreal 描述符 JSON 读取。
- 路径规范化和跳过生成目录。
- C# 与 C++ 的词法 Token、声明、控制条件和操作投影。
- 统一 Validation、Limits 和请求失败信封。
- 稳定 JSON 序列化。

共享层可以复用语法能力，但不能让多个 CLI 共享未声明的领域结论。

### 3.4 Schema 层

`schemas/` 使用 JSON Schema Draft 2020-12：

- `common.schema.json` 定义共享 `validation`、`limits`、`request` 和失败文档。
- 16 个 CLI 各自拥有一份同名 Schema。
- CLI Schema 使用 `oneOf` 区分领域结果与请求失败结果。
- `schema_version` 仍由 CLI 输出，不由 Schema 文件名替代。

## 4. 显式导航模型

项目级工具负责发现与定位，文件级工具负责检查一个明确入口。

```text
search root
└─ .uproject
   ├─ descriptor / engine / modules / targets / paths / C++ inventory
   ├─ direct plugin reference
   │  └─ .uplugin
   │     └─ Build.cs
   │        ├─ ModuleRules
   │        └─ Module entry
   └─ Target.cs or ordinary .cs
      └─ selected function name

selected .h/.hpp/.cpp/.cc
├─ includes
├─ type and declaration anchors
└─ selected function name
```

规则：

1. 项目发现出现多个 `.uproject` 时停止选择并报告错误。
2. `.uproject` 的 Plugin 声明只负责导航到直接描述符，不展开传递依赖。
3. `.uplugin` 结果可以提供 Build.cs 候选，但不自动检查规则或 C++。
4. TargetRules 索引先列出函数名，再由调用方明确选择一个函数检查。
5. C++ 类型工具先提供成员函数锚点，再由调用方明确选择函数名。
6. 后续工具的结果不嵌入前一层 Schema。

## 5. C++ 源码单元

三个 C++ CLI 共享相同的源码上下文和 `source_unit` 语义。

接受的后缀：

- 源文件：`.cpp`、`.cc`
- 头文件：`.h`、`.hpp`

伴随文件选择顺序：

1. 选中文件所在目录中的同名、相反类型文件。
2. 常规 `Private ↔ Public/Classes` 同名映射。
3. 唯一候选与选中文件组成源码单元。
4. 零个候选时只扫描选中文件。
5. 多个候选时不选择，并返回 warning。

每个 C++ 工具只加载自己需要的分析：

- include 工具解析直接 include 和预处理条件。
- 类型工具解析类型、成员、接口候选、全局变量和自由函数。
- 函数工具只返回选定名称的全部定义和相关外部引用。

不会递归读取被 include 的源码，也不会跟踪被调用函数。

## 6. 公开结果契约

### 6.1 顶层顺序

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

`result_document()` 拒绝领域内容覆盖 `schema_version`、`validation` 或 `limits`。

### 6.2 Validation

`validation_result()` 按最高严重级别计算状态：

- 包含 error：`error`
- 否则包含 warning：`warning`
- 没有 warning 或 error：`ok`

`problem_count` 必须等于 `problems` 的实际长度。warning 表示扫描完成但存在非阻断问题，调用方不得静默改写为 ok。

### 6.3 Limits

每个结果必须包含：

- `responsibility`：该结果负责回答的问题。
- `boundaries`：该结果不能证明的内容。

边界属于公共契约，不是可省略的说明文字。

### 6.4 错误通道与退出码

所有 CLI 将 JSON 写入 stdout，并保持 stderr 为空。

| 退出码 | 语义 |
|---:|---|
| `0` | 扫描完成，Validation 为 `ok` 或 `warning` |
| `1` | 扫描完成，Validation 为 `error` |
| `2` | 参数、输入或读取失败 |

参数解析失败使用 `request.kind: argument`。路径、格式或读取失败使用 `request.kind: input`。已开始扫描后发现领域阻断问题时保留领域事实，并返回退出码 `1`。

### 6.5 JSON 读取策略

- `.uproject`、`Build.version` 等通用输入使用严格 JSON。
- 严格读取拒绝重复键、`NaN` 等非标准常量和非对象顶层值。
- `.uplugin` 使用独立 Unreal JSON 读取器，允许注释和尾随逗号。
- `.uplugin` 重复字段不会静默忽略，而会产生可定位的 Validation 问题。

## 7. 路径、证据与确定性

- 公共绝对根路径只在对应 `path_roots` 或领域根字段中记录。
- 根目录内证据优先使用规范化相对路径。
- C++ 证据保留文件单元和行号。
- 描述符证据使用 JSON Pointer。
- 文件遍历跳过 `.git`、`.idea`、`.vs`、`Binaries`、`DerivedDataCache`、`Intermediate` 和 `Saved`。
- 候选与事实数组在输出前稳定排序。
- 物理文件存在只证明静态候选，不证明 UBT、编译器或运行时实际采用。

## 8. 测试设计

测试使用 Python 标准库 `unittest`，Schema 校验使用开发依赖 `jsonschema`。

`tests/support.py` 在每个测试的临时目录中构造：

- 最小 `Engine/Build/Build.version`。
- Core 与 GameplayTags 的最小 Build.cs 和头文件。
- 一个 `.uproject`、Runtime Module、Game Target 和 Editor Target。
- 一个项目 Plugin、`.uplugin`、Build.cs、注册、回调绑定与清理。
- 一组 `Private .cpp ↔ Public .h` C++ 类型与函数。
- CLI 子进程运行器、公共结果断言和 Schema 校验器。

测试不读取 Lyra 或外部样例项目，不依赖已安装 Unreal Engine，不调用 UBT/UHT/Editor，也不修改真实项目。

当前 64 项测试：

| 模块 | 数量 | 目标 |
|---|---:|---|
| `test_public_contracts.py` | 16 | CLI、Schema、帮助、退出码、错误信封与严格 JSON |
| `test_project_navigation.py` | 14 | 项目级发现、导航事实、Plugin 与 C++ 文件清单 |
| `test_build_analysis.py` | 14 | `.uplugin`、规则、C# 函数和 Module 生命周期 |
| `test_cxx_source_units.py` | 12 | 源码单元、include 和歧义边界 |
| `test_cxx_types.py` | 5 | 类型、接口候选、命名空间和链接属性 |
| `test_cxx_functions.py` | 13 | 函数身份、外部符号分类和失败边界 |
| `test_end_to_end_workflow.py` | 2 | 16 个 CLI 的端到端导航与确定性 |

执行方式：

```powershell
python -m unittest discover -s tests -v
```

测试锁定公开行为、Schema、证据和失败边界，不锁定内部文件拆分。内部重构不应迫使无关公共行为测试重写。

## 9. 扩展规则

新增或修改能力时：

1. 优先新增小型领域服务和薄 CLI，不扩大现有 CLI 的职责。
2. 新公共结果必须使用统一结果组装器。
3. 消费者解释方式变化时，升级该 CLI 自己的 Schema 版本。
4. 不递归扩展依赖、include 或调用关系，除非新增独立工具与边界。
5. 未知语法或不透明效果输出诊断，不执行源码，也不猜测最终值。
6. 每个事实保留可定位证据；无法定位的结论不能升级为确认事实。
7. 新功能至少包含成功路径、失败路径和 CLI Schema 契约测试。
8. 改变导航入口时同步更新端到端测试、README 和本文。
9. UBT、UHT、Editor、Asset Registry 或运行时证据必须使用独立 Schema 和采集上下文。
10. 生成、修改和归档能力必须与这 16 个只读 CLI 分离。

## 10. 已知限制

- 正式 Schema 锁定公共信封和主要领域字段，但部分复杂嵌套事实仍允许扩展属性。
- 当前没有为所有成功结果维护完整 golden 文件，测试以 Schema 和关键语义断言为主。
- Engine、Plugin 和 Build.cs 树可能在不同 CLI 进程间重复扫描。
- C++ 工具不会跨进程复用源码上下文或 Token。
- 大型 Engine、Plugin 树或 Module 可能产生明显 I/O 与内存开销。
- 当前没有覆盖率阈值、性能基准或持续集成配置。
- junction、symlink、权限失败、注册表多版本歧义和完整 Plugin Profile 组合尚未形成系统矩阵。

这些限制必须通过明确诊断和边界说明处理，不能通过扩大静态结论或弱化 Validation 隐藏。
