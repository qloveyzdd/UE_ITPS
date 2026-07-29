# UE ITPS

UE ITPS 是一组确定性、只读的 Unreal Engine 项目检查工具。它从调用方明确选择的 `.uproject`、`.uplugin`、`Build.cs`、`Target.cs` 或 C++ 文件出发，输出适合程序和 AI Agent 消费的 JSON 事实。

当前正式接口包括：

- 16 个聚焦的 Python CLI。
- 16 份 CLI JSON Schema 和 1 份公共 Schema。
- 57 项自动化测试。
- 3 个与 Lyra 本地验证相关的辅助脚本；它们不属于 16 个正式只读 CLI。

UE ITPS 提供静态文件与源码证据，不替代 UnrealBuildTool、UnrealHeaderTool、Editor、编译器或运行时验证。

## 环境要求

- Python 3.10 或更高版本。
- 正式 CLI 只依赖 Python 标准库。
- 运行测试需要 `requirements-dev.txt` 中的 `jsonschema`。
- 只有解析已安装 Engine 或执行 Lyra 辅助流程时，才需要相应 Engine 或项目目录。

安装测试依赖：

```powershell
python -m pip install -r requirements-dev.txt
```

## 快速开始

先发现项目：

```powershell
python tools/ue_find_projects.py --search-root D:/Projects/MyGame
```

只有一个候选时，将返回的 `.uproject` 路径作为后续命令的明确输入：

```powershell
python tools/ue_read_project_descriptor.py --project D:/Projects/MyGame/MyGame.uproject
python tools/ue_resolve_engine.py --project D:/Projects/MyGame/MyGame.uproject
python tools/ue_inspect_modules.py --project D:/Projects/MyGame/MyGame.uproject
python tools/ue_inspect_targets.py --project D:/Projects/MyGame/MyGame.uproject
python tools/ue_list_project_cxx_sources.py --project D:/Projects/MyGame/MyGame.uproject
```

检查一个明确选择的 C++ 源码单元：

```powershell
python tools/ue_list_cxx_includes.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp
python tools/ue_list_cxx_types.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp
python tools/ue_inspect_cxx_function.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp --function BeginPlay
```

每个 CLI 都提供中英双语帮助：

```powershell
python tools/ue_inspect_module_entry.py --help
```

## 正式 CLI

| 范围 | CLI | 明确入口 | Schema 版本 | 职责 |
|---|---|---|---|---|
| 项目 | `ue_find_projects.py` | `--search-root` | `ue-itps.project-discovery.v1` | 查找 `.uproject`，如实报告零个、一个或多个候选 |
| 项目 | `ue_read_project_descriptor.py` | `--project` | `ue-itps.project-descriptor.v1` | 投影 `.uproject` 的显式声明 |
| 项目 | `ue_resolve_engine.py` | `--project` | `ue-itps.engine-resolution.v1` | 定位 Engine 根目录并读取 `Build.version` |
| 项目 | `ue_inspect_modules.py` | `--project` | `ue-itps.project-modules.v1` | 对账 Module 声明、Build.cs 和注册入口 |
| 项目 | `ue_inspect_targets.py` | `--project` | `ue-itps.project-targets.v1` | 发现 Target.cs 并报告原生 Target 证据 |
| 项目 | `ue_list_project_cxx_sources.py` | `--project` | `ue-itps.project-cxx-sources.v1` | 按 Module、Plugin 和可见性列出项目 C++ 源码 |
| 项目 | `ue_resolve_plugins.py` | `--project` | `ue-itps.project-plugin-references.v1` | 在显式 Profile 下定位直接 Plugin 引用 |
| 项目 | `ue_classify_project_paths.py` | `--project` | `ue-itps.project-paths.v1` | 分类项目根路径及文件系统状态 |
| 构建 | `ue_read_plugin_descriptor.py` | `--plugin` | `ue-itps.plugin-descriptor.v2` | 读取一个 `.uplugin` 并对账其 Module |
| 构建 | `ue_inspect_module_rules.py` | `--rules` | `ue-itps.module-rule-relations.v1` | 投影 ModuleRules 设置变更与条件 |
| 构建 | `ue_inspect_target_rules.py` | `--target` | `ue-itps.target-rule-relations.v1` | 索引 TargetRules 类、变量和函数 |
| 构建 | `ue_inspect_cs_function.py` | `--source --function` | `ue-itps.cs-function.v1` | 检查同名 C# 成员及其外部引用 |
| Module | `ue_inspect_module_entry.py` | `--rules` | `ue-itps.module-entry-state.v12` | 检查注册、回调绑定、清理和生命周期状态 |
| C++ | `ue_list_cxx_includes.py` | `--source` | `ue-itps.cxx-includes.v1` | 列出直接 include、条件和物理来源 |
| C++ | `ue_list_cxx_types.py` | `--source` | `ue-itps.cxx-types.v1` | 索引类型、成员、全局变量和自由函数锚点 |
| C++ | `ue_inspect_cxx_function.py` | `--source --function` | `ue-itps.cxx-function.v1` | 检查同名定义及其外部符号 |

`ue_resolve_plugins.py` 还支持：

- `--operation`：`scan`、`open_editor`、`build_editor`、`run_game` 或 `cook_package`。
- `--platform`：默认 `Win64`。
- `--target-type`：默认 `Editor`。
- `--plugin-name`：可重复指定，按名称筛选，大小写不敏感。

## 显式导航

工具不会自动遍历并解释整个项目。调用方先选择入口，再决定是否进入下一层：

```text
搜索根目录
└─ 唯一 .uproject
   ├─ 描述符 / Engine / Module / Target / 项目路径 / C++ 清单
   ├─ 直接 Plugin 引用
   │  └─ 明确选择一个 .uplugin
   │     └─ 明确选择一个 Build.cs
   │        ├─ ModuleRules
   │        └─ Module 注册与生命周期
   └─ 明确选择一个 Target.cs 或普通 .cs
      └─ 明确选择一个函数名

明确选择一个 .h/.hpp/.cpp/.cc
├─ 直接 include
├─ 类型与声明锚点
└─ 明确选择一个函数名
```

项目发现遇到多个 `.uproject` 时返回歧义错误，不代替调用方选择。文件级工具也采用同一原则：没有伴随文件时只扫描选中文件，多个伴随候选时返回 warning，不猜测目标。

## JSON 输出契约

成功或已经开始领域扫描的结果：

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

公共规则：

- JSON 写入 stdout，stderr 保持为空。
- `request.status` 固定为 `failed`。
- `request.kind` 为 `argument` 或 `input`。
- `validation.status` 为 `ok`、`warning` 或 `error`。
- `validation.problem_count` 必须等于 `problems` 的实际数量。
- `limits.responsibility` 说明当前结果负责回答的问题。
- `limits.boundaries` 说明当前结果不能证明的内容。

| 退出码 | 含义 |
|---:|---|
| `0` | 扫描完成，Validation 为 `ok` 或 `warning` |
| `1` | 扫描完成，但出现领域阻断错误 |
| `2` | 参数、输入或读取失败 |

`.uproject` 和 `Build.version` 使用严格 JSON 读取，拒绝重复键、非标准常量和非对象根值。`.uplugin` 使用独立的 Unreal JSON 读取器，允许注释与尾随逗号，同时将重复字段作为可定位的验证问题报告。

## 测试

运行完整测试：

```powershell
python -m unittest discover -s tests -v
```

当前测试共 57 项：

| 测试模块 | 数量 | 覆盖重点 |
|---|---:|---|
| `test_cli_contracts.py` | 15 | CLI/Schema 清单、双语帮助、错误信封、退出码、严格 JSON 和公共结果契约 |
| `test_project_navigation.py` | 14 | 项目发现、描述符、Engine、Module、Target、Plugin、源码清单和路径 |
| `test_build_and_module.py` | 12 | `.uplugin`、ModuleRules、TargetRules、C# 函数和 Module 生命周期 |
| `test_cxx_analysis.py` | 13 | 源码单元、include、类型、接口候选、函数身份和外部符号 |
| `test_end_to_end_workflow.py` | 3 | 16 个 CLI 的完整导航、只读性和字节级确定性 |
| **合计** | **57** | 当前公共行为、成功与失败边界、Schema、只读性和确定性 |

测试在临时目录中构造最小 Engine、项目、Plugin、规则文件和 C++ 源码：

- 不读取 `LyraStarterGame/` 或 `ExternalProjects/`。
- 不依赖已安装 Unreal Engine。
- 不运行 UBT、UHT 或 Editor。
- 不修改真实项目。
- 每个 CLI 结果都通过对应 JSON Schema 校验。

## Lyra 辅助脚本

以下脚本服务于仓库内的 Lyra 本地证据流程，不属于 16 个正式 CLI，也没有复用正式 CLI 的只读输入/输出契约：

| 脚本 | 用途 |
|---|---|
| `tools/query_lyra_asset_registry.py` | 在 Unreal Python 环境内读取指定 Lyra 资产和直接依赖切片 |
| `tools/new_lyra_baseline_fingerprint.ps1` | 为 Lyra 权威文件生成 SHA-256 基线 |
| `tools/archive_lyra_run.ps1` | 将一次 Lyra 运行日志和上下文归档为不可覆盖的证据目录 |

这些脚本可能写入 `.planning/evidence/`，应与正式只读检查器分开使用和评估。

## 仓库结构

```text
.
├─ tools/
│  ├─ ue_*.py                 # 16 个正式 CLI
│  ├─ ue_project_tools/       # 领域服务、解析器与公共输出组件
│  └─ *lyra*                  # Lyra 本地证据辅助脚本
├─ schemas/                   # 16 个 CLI Schema + 1 个公共 Schema
├─ tests/                     # 57 项临时夹具自动化测试
├─ docs/PROGRAM-DESIGN.md     # 架构、契约和扩展规则
├─ LyraStarterGame/           # 可选本地参考项目
├─ ExternalProjects/          # 可选外部参考项目
└─ requirements-dev.txt       # 测试依赖
```

## 能力边界

- 所有正式 CLI 结论都是静态证据，不是有效 UBT/UHT 配置。
- Plugin 解析只覆盖 `.uproject` 的直接声明，不计算完整传递闭包。
- Build.cs 和 Target.cs 只解析受支持的 C# 子集，不执行规则代码。
- include 的唯一物理候选不等于编译器实际选中。
- 类型、成员与函数结果是词法投影，不是完整 C++ 符号表或调用图。
- Module 生命周期结果是保守静态模型，不证明实际加载顺序、线程或运行状态。
- 路径分类不提供删除安全结论。
- 编译、启动、资产、配置合并、网络和目标平台行为仍需 Unreal 权威工具验证。

维护规则和内部设计见 [程序设计文档](docs/PROGRAM-DESIGN.md)。
