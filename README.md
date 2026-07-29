# UE ITPS

UE ITPS 是一组面向用户与 AI Agent 的确定性、只读 Unreal Engine 项目检查器。项目提供 16 个聚焦 CLI：每次接收一个明确入口，返回可供程序消费的 JSON 事实、验证问题和能力边界。

这些工具适合回答：

- 工作区中有哪些 `.uproject`。
- 项目声明了哪些 Module、Plugin 和 Target。
- 指定 `.uplugin`、`Build.cs` 或 `Target.cs` 中能直接观察到什么。
- 指定 C++ 源码单元包含哪些 include、类型、成员和同名函数定义。

UE ITPS 不替代 UnrealBuildTool、UnrealHeaderTool、Editor、编译器或运行时验证。

## 环境

- Python 3.10 或更高版本。
- 16 个核心 CLI 只依赖 Python 标准库。
- 运行测试时需要 `requirements-dev.txt` 中的 `jsonschema`。
- 解析已安装 Engine 时，需要能访问 Engine 目录；必要时显式传入 `--engine-root`。

```powershell
git clone https://github.com/qloveyzdd/UE_ITPS.git
cd UE_ITPS
python --version
```

## 快速开始

先查找项目：

```powershell
python tools/ue_find_projects.py --search-root D:/Projects/MyGame
```

当结果只有一个候选时，将该 `.uproject` 作为后续命令的明确输入：

```powershell
python tools/ue_read_project_descriptor.py --project D:/Projects/MyGame/MyGame.uproject
python tools/ue_resolve_engine.py --project D:/Projects/MyGame/MyGame.uproject
python tools/ue_inspect_modules.py --project D:/Projects/MyGame/MyGame.uproject
python tools/ue_inspect_targets.py --project D:/Projects/MyGame/MyGame.uproject
python tools/ue_list_project_cxx_sources.py --project D:/Projects/MyGame/MyGame.uproject
```

检查一个明确选择的 C++ 文件：

```powershell
python tools/ue_list_cxx_types.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp
python tools/ue_inspect_cxx_function.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp --function BeginPlay
```

所有 CLI 都提供中英双语帮助：

```powershell
python tools/ue_inspect_module_entry.py --help
```

## CLI 清单

| 范围 | CLI | 必要入口 | 作用 | Schema |
|---|---|---|---|---|
| 项目 | `ue_find_projects.py` | `--search-root`，默认当前目录 | 查找 `.uproject`；零个或多个候选都如实报错 | `ue-itps.project-discovery.v1` |
| 项目 | `ue_read_project_descriptor.py` | `--project` | 读取 `.uproject` 的显式声明 | `ue-itps.project-descriptor.v1` |
| 项目 | `ue_resolve_engine.py` | `--project` | 解析 Engine 根目录和 `Build.version` | `ue-itps.engine-resolution.v1` |
| 项目 | `ue_inspect_modules.py` | `--project` | 对账 Module、Build.cs 和注册入口 | `ue-itps.project-modules.v1` |
| 项目 | `ue_inspect_targets.py` | `--project` | 定位并分类 Target.cs | `ue-itps.project-targets.v1` |
| 项目 | `ue_list_project_cxx_sources.py` | `--project` | 按 Module、Plugin 和可见性列出项目 C++ 文件 | `ue-itps.project-cxx-sources.v1` |
| 项目 | `ue_resolve_plugins.py` | `--project` | 定位 `.uproject` 的直接 Plugin 引用 | `ue-itps.project-plugin-references.v1` |
| 项目 | `ue_classify_project_paths.py` | `--project` | 分类项目根目录中的约定路径 | `ue-itps.project-paths.v1` |
| 构建 | `ue_read_plugin_descriptor.py` | `--plugin` | 读取一个 `.uplugin` 并对账其 Module | `ue-itps.plugin-descriptor.v2` |
| 构建 | `ue_inspect_module_rules.py` | `--rules` | 投影 ModuleRules 设置变更及适用条件 | `ue-itps.module-rule-relations.v1` |
| 构建 | `ue_inspect_target_rules.py` | `--target` | 索引 TargetRules 类、变量和函数 | `ue-itps.target-rule-relations.v1` |
| 构建 | `ue_inspect_cs_function.py` | `--source --function` | 检查一个 C# 文件中的全部同名成员函数 | `ue-itps.cs-function.v1` |
| Module | `ue_inspect_module_entry.py` | `--rules` | 检查注册、回调清理和生命周期状态 | `ue-itps.module-entry-state.v12` |
| C++ | `ue_list_cxx_includes.py` | `--source` | 列出直接 include、条件和物理来源 | `ue-itps.cxx-includes.v1` |
| C++ | `ue_list_cxx_types.py` | `--source` | 列出类型、接口候选、全局变量、自由函数和成员锚点 | `ue-itps.cxx-types.v1` |
| C++ | `ue_inspect_cxx_function.py` | `--source --function` | 检查全部同名定义及外部类型和方法引用 | `ue-itps.cxx-function.v1` |

`ue_resolve_plugins.py` 支持以下 Profile 参数：

- `--operation`：`scan`、`open_editor`、`build_editor`、`run_game` 或 `cook_package`。
- `--platform`：默认 `Win64`。
- `--target-type`：默认 `Editor`。
- `--plugin-name`：可重复指定，按 Plugin Name 过滤，大小写不敏感。

## 显式导航

工具不会自动展开整个项目。调用方应从上一层结果中选择下一个明确入口：

```text
搜索根目录
└─ 唯一 .uproject
   ├─ 项目描述符 / Engine / Module / Target / C++ 清单 / 路径
   ├─ 直接 Plugin 引用
   │  └─ 明确选择一个 .uplugin
   │     └─ 明确选择一个 Build.cs
   │        ├─ ModuleRules
   │        └─ Module 注册与生命周期
   └─ 明确选择一个 Target.cs 或普通 .cs
      └─ 按函数名检查成员

明确选择一个 .h/.hpp/.cpp/.cc
├─ 直接 include
├─ 类型与声明锚点
└─ 按函数名检查定义
```

当搜索根目录包含多个 `.uproject` 时，发现工具返回歧义错误，不会代替调用方选择。C++ 工具会在同目录以及常规 `Private ↔ Public/Classes` 映射中寻找同名伴随文件；零个候选时只扫描选中文件，多个候选时返回 warning。

## 输出契约

成功或已开始扫描的结果保持以下顶层顺序：

```text
schema_version
<领域事实>
validation
limits
```

参数、输入或读取失败使用统一信封：

```text
schema_version
request
validation
limits
```

- 所有 JSON 写入 stdout，stderr 保持为空。
- `request.status` 固定为 `failed`。
- `request.kind` 为 `argument` 或 `input`。
- `validation.status` 为 `ok`、`warning` 或 `error`。
- `validation.problem_count` 必须等于 `problems` 的实际数量。
- `limits.responsibility` 说明结果负责回答什么。
- `limits.boundaries` 说明结果不能证明什么。

| 退出码 | 含义 |
|---:|---|
| `0` | 扫描完成，Validation 为 `ok` 或 `warning` |
| `1` | 扫描完成，但 Validation 为 `error` |
| `2` | 参数、输入或读取失败 |

`.uproject` 和 `Build.version` 等通用 JSON 使用严格 JSON。`.uplugin` 读取器单独支持 Unreal 描述符中常见的注释和尾随逗号，并将重复字段报告为验证问题。

## JSON Schema

`schemas/` 包含 JSON Schema Draft 2020-12 契约：

- `common.schema.json` 定义共享 Validation、Limits 和失败信封。
- 每个公开 CLI 都有一份同名 Schema。
- Schema 文件不改变 CLI 输出中既有的 `schema_version`。

安装测试依赖：

```powershell
python -m pip install -r requirements-dev.txt
```

## 测试

运行完整测试：

```powershell
python -m unittest discover -s tests -v
```

当前共 64 项测试，全部在临时目录中构造最小 Engine、项目、Plugin、规则文件和 C++ 源码，不读取仓库内的 Lyra 或外部样例项目，也不会修改真实项目。

| 测试模块 | 数量 | 覆盖重点 |
|---|---:|---|
| `test_public_contracts.py` | 16 | CLI/Schema 清单、双语帮助、退出码、错误信封、公共 JSON 规则 |
| `test_project_navigation.py` | 14 | 项目发现、描述符、Engine、Module、Target、Plugin、源码清单和路径 |
| `test_build_analysis.py` | 14 | `.uplugin`、ModuleRules、TargetRules、C# 函数和 Module 生命周期 |
| `test_cxx_analysis.py` | 18 | 源码单元配对、include、类型、接口候选、函数与失败边界 |
| `test_end_to_end_workflow.py` | 2 | 16 个 CLI 的完整导航和重复扫描确定性 |
| **合计** | **64** | 当前公开行为、关键失败边界与确定性 |

## 仓库结构

```text
.
├─ tools/
│  ├─ ue_*.py                 # 16 个公开 CLI
│  └─ ue_project_tools/       # 领域服务、解析器和公共输出组件
├─ schemas/                   # 16 个 CLI Schema 与 1 个公共 Schema
├─ tests/
│  ├─ support.py              # 临时 UE 工作区与公共断言
│  └─ test_*.py               # 64 项自动化测试
├─ docs/PROGRAM-DESIGN.md     # 架构、契约和扩展规则
└─ requirements-dev.txt       # 测试依赖
```

`LyraStarterGame/` 和 `ExternalProjects/` 仅用于可选的本地只读参考，不属于核心工具或自动化测试的运行依赖。

## 能力边界

- 所有结论都是静态文件与源码证据，不是有效 UBT/UHT 配置。
- Plugin 解析只覆盖 `.uproject` 的直接引用，不计算完整传递闭包。
- Build.cs 和 Target.cs 只解析受支持的 C# 子集，不执行规则代码。
- include 的唯一物理候选不等于编译器实际选中，也不证明依赖声明正确。
- 类型、成员与函数结果是词法投影，不是完整 C++ 符号表、类型系统或调用图。
- Module 生命周期结果是保守静态模型，不证明实际加载顺序、线程或运行状态。
- 路径分类只报告角色与文件系统状态，不提供删除安全结论。
- 编译、启动、资产、配置合并、网络和目标平台行为仍需 Unreal 权威工具验证。

维护与扩展规则见 [程序设计文档](docs/PROGRAM-DESIGN.md)。
