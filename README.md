# UE ITPS

UE ITPS 是一组面向用户与 AI Agent 的确定性、只读 Unreal Engine 项目检查器。项目提供 16 个聚焦 CLI：每次接收一个明确输入，返回结构化 JSON 事实、验证问题和能力边界。

它适合回答“项目声明了什么、文件位于哪里、源码中能直接观察到什么”，但不替代 UnrealBuildTool、UnrealHeaderTool、Editor、编译器或运行时验证。

## 环境

- Python 3.10 或更高版本
- 核心 CLI 仅使用 Python 标准库
- 解析已安装 Engine 时，需要能够访问对应 Engine 目录；必要时可显式传入 `--engine-root`

```powershell
git clone https://github.com/qloveyzdd/UE_ITPS.git
cd UE_ITPS
python --version
```

## 快速开始

先发现项目：

```powershell
python tools/ue_find_projects.py --search-root D:/Projects/MyGame
```

只有一个候选时，再将该 `.uproject` 作为后续检查的明确输入：

```powershell
python tools/ue_read_project_descriptor.py --project D:/Projects/MyGame/MyGame.uproject
python tools/ue_resolve_engine.py --project D:/Projects/MyGame/MyGame.uproject
python tools/ue_inspect_modules.py --project D:/Projects/MyGame/MyGame.uproject
python tools/ue_inspect_targets.py --project D:/Projects/MyGame/MyGame.uproject
python tools/ue_list_project_cxx_sources.py --project D:/Projects/MyGame/MyGame.uproject
```

检查一个明确选择的 C++ 源文件：

```powershell
python tools/ue_list_cxx_types.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp
python tools/ue_inspect_cxx_function.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp --function BeginPlay
```

每个 CLI 都提供中英双语帮助：

```powershell
python tools/ue_inspect_module_entry.py --help
```

## 公开 CLI

| 范围 | CLI | 输入 | 作用 | Schema |
|---|---|---|---|---|
| 项目 | `ue_find_projects.py` | `--search-root` | 发现 `.uproject`；多个候选时报告歧义 | `ue-itps.project-discovery.v1` |
| 项目 | `ue_read_project_descriptor.py` | `--project` | 读取项目描述符的显式声明 | `ue-itps.project-descriptor.v1` |
| 项目 | `ue_resolve_engine.py` | `--project`、可选 `--engine-root` | 解析 Engine 根目录和 `Build.version` | `ue-itps.engine-resolution.v1` |
| 项目 | `ue_inspect_modules.py` | `--project` | 对账 Module、Build.cs 和注册入口 | `ue-itps.project-modules.v1` |
| 项目 | `ue_inspect_targets.py` | `--project` | 定位并分类 Target.cs | `ue-itps.project-targets.v1` |
| 项目 | `ue_list_project_cxx_sources.py` | `--project` | 按 Module、Plugin、文件类型和 Public/Private 列出项目 C++ 源码 | `ue-itps.project-cxx-sources.v1` |
| 项目 | `ue_resolve_plugins.py` | `--project`、Profile 参数 | 定位 `.uproject` 的直接 Plugin 引用 | `ue-itps.project-plugin-references.v1` |
| 项目 | `ue_classify_project_paths.py` | `--project` | 分类项目根目录中的约定路径 | `ue-itps.project-paths.v1` |
| 构建 | `ue_read_plugin_descriptor.py` | `--plugin` | 校验一个 `.uplugin` 并对账其 Module | `ue-itps.plugin-descriptor.v2` |
| 构建 | `ue_inspect_module_rules.py` | `--rules` | 提取 ModuleRules 的声明变更和条件 | `ue-itps.module-rule-relations.v1` |
| 构建 | `ue_inspect_target_rules.py` | `--target` | 索引 TargetRules 类、变量和函数 | `ue-itps.target-rule-relations.v1` |
| 构建 | `ue_inspect_cs_function.py` | `--source --function` | 检查一个 C# 文件中的同名成员函数 | `ue-itps.cs-function.v1` |
| 模块 | `ue_inspect_module_entry.py` | `--rules` | 检查模块注册、回调清理和生命周期状态 | `ue-itps.module-entry-state.v12` |
| C++ | `ue_list_cxx_includes.py` | `--source` | 列出直接 include、条件和文件来源 | `ue-itps.cxx-includes.v1` |
| C++ | `ue_list_cxx_types.py` | `--source` | 列出类型、Interface 候选、全局变量、自由函数和成员锚点 | `ue-itps.cxx-types.v1` |
| C++ | `ue_inspect_cxx_function.py` | `--source --function` | 检查全部同名函数定义及外部引用 | `ue-itps.cxx-function.v1` |

`ue_resolve_plugins.py` 的 Profile 参数为：

- `--operation`：`scan`、`open_editor`、`build_editor`、`run_game` 或 `cook_package`
- `--platform`：默认 `Win64`
- `--target-type`：默认 `Editor`
- `--plugin-name`：可重复指定，按 Plugin Name 过滤

## 导航原则

这些工具不会自动展开整个项目。调用方应根据上一层证据明确选择下一步输入：

```text
搜索根目录
└─ 唯一 .uproject
   ├─ 项目描述符 / Engine / Module / Target / Plugin / 路径
   ├─ 明确选择一个 .uplugin
   │  └─ 明确选择一个 Build.cs
   │     ├─ ModuleRules
   │     └─ 模块注册与生命周期
   └─ 明确选择一个 Target.cs 或普通 .cs
      └─ 按函数名检查成员

明确选择一个 .h/.hpp/.cpp/.cc
├─ include
├─ 类型、Interface 候选、全局变量、自由函数和成员锚点
└─ 按函数名检查定义
```

当搜索根目录存在多个 `.uproject` 时，发现工具会返回歧义错误，不会擅自选择。C++ 工具接受明确选择的 `.h/.hpp/.cpp/.cc`，并按同目录及常规 `Private <-> Public/Classes` 映射双向寻找同名实现文件或头文件；候选唯一时一并扫描，多个候选会返回 warning。

## 输出与退出码

正常 JSON 结果保持以下顶层顺序：

```text
schema_version
<该工具的事实字段>
validation
limits
```

请求在参数解析、输入校验或读取阶段失败时，统一返回：

```text
schema_version
request
validation
limits
```

- `request.status` 固定为 `failed`
- `request.kind` 为 `argument` 或 `input`
- 所有 JSON 都写入 stdout；stderr 保持为空
- `validation.status` 为 `ok`、`warning` 或 `error`
- `validation.problems` 保存稳定问题码、严重级别和证据
- `limits.responsibility` 说明该结果负责回答什么
- `limits.boundaries` 说明该结果不能证明什么

| 退出码 | 含义 |
|---:|---|
| `0` | 扫描完成，未发现阻断问题；结果可能是 `ok` 或 `warning` |
| `1` | 扫描完成，但验证结果为 `error` |
| `2` | 参数、输入或读取失败 |

16 个 CLI 的参数语法、输入和读取失败都使用统一 JSON 错误信封与退出码 `2`。扫描已经开始但发现阻断问题时，仍返回对应领域事实、`validation: error` 和退出码 `1`。

`.uproject`、`Build.version` 等通用 JSON 输入使用严格 JSON；`.uplugin` 读取器单独支持 Unreal 描述符中常见的注释和尾随逗号，同时会把重复字段报告为验证问题。

## JSON Schema

`schemas/` 提供 Draft 2020-12 正式契约：

- `common.schema.json`：共享 `validation`、`limits` 和错误信封定义
- `ue_<name>.schema.json`：16 个 CLI 各自的成功结果与错误结果 Schema

Schema 文件不改变 CLI 输出中的既有 `schema_version`。核心 CLI 仍只依赖 Python 标准库；运行 Schema 校验测试时安装开发依赖：

```powershell
python -m pip install -r requirements-dev.txt
```

## 测试

运行完整测试套件：

```powershell
python -m unittest discover -s tests -v
```

当前共有 52 项测试，全部使用临时目录构造最小 Engine、项目、Plugin、规则文件和 C++ 源码，不依赖本机 Unreal Engine，也不会修改真实项目。

| 测试模块 | 数量 | 关注点 |
|---|---:|---|
| `test_contract_surface.py` | 8 | 16 个 CLI、正式 Schema、双语帮助、统一错误信封和退出码 |
| `test_project_layer.py` | 10 | 项目发现、描述符、Engine、Module、Target、Plugin、C++ 源码、路径 |
| `test_build_layer.py` | 9 | `.uplugin`、ModuleRules、TargetRules、C# 函数、模块入口 |
| `test_source_unit.py` | 8 | C++ 上下文和源码单元配对 |
| `test_source_includes.py` | 3 | include 定位、状态和条件 |
| `test_source_types.py` | 3 | 类型、成员和声明锚点 |
| `test_source_functions.py` | 3 | 函数关系、外部引用和选择 |
| `test_boundary_cases.py` | 7 | 歧义、非法输入、重复定位、损坏语法、保守失败 |
| `test_navigation_workflow.py` | 1 | 16 个 CLI 的完整显式导航流程 |
| **合计** | **52** | 当前公开行为与关键失败边界 |

## 仓库结构

```text
.
├─ tools/
│  ├─ ue_*.py                 # 16 个公开 CLI
│  └─ ue_project_tools/       # 发现、解析、验证与事实投影
├─ tests/
│  ├─ fixture.py              # 共享最小 UE 夹具与 CLI 断言
│  └─ test_*.py               # 52 项自动化测试
├─ schemas/                   # Draft 2020-12 公共结果契约
├─ requirements-dev.txt       # Schema 测试依赖
├─ docs/PROGRAM-DESIGN.md     # 架构、契约和扩展规则
├─ LyraStarterGame/           # 可选本地只读参考项目，Git 忽略
└─ ExternalProjects/          # 可选外部测试项目，Git 忽略
```

`LyraStarterGame/` 和 `ExternalProjects/` 不属于核心工具或自动化测试的运行依赖。

## 能力边界

- 结果是静态源码和文件系统证据，不是有效 UBT/UHT 配置。
- Plugin 解析只覆盖 `.uproject` 的直接引用，不计算完整传递闭包。
- Build.cs 和 Target.cs 只解析受支持的 C# 子集，不执行规则代码。
- include 的唯一物理候选不等于编译器实际选中或依赖声明正确。
- Class、Struct 和 Enum 锚点使用 `role` 区分声明/定义；嵌套 Class/Struct 使用 `owner` 和 `qualified_name` 保留词法层级。
- 声明锚点与函数结果是词法事实；Interface 候选不等于 UHT 已确认接口，也不是完整 C++ 符号表、类型系统或调用图。
- 模块生命周期结果是保守静态投影，不证明实际加载顺序、线程或运行状态。
- 路径分类不读取目录内容，也不提供删除安全性结论。
- 编译、启动、资产、配置合并、网络与平台行为仍需 Unreal 权威工具验证。

维护和扩展规则见 [程序设计文档](docs/PROGRAM-DESIGN.md)。
