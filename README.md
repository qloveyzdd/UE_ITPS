<!-- generated-by: gsd-doc-writer -->
# UE ITPS

UE ITPS 是一组面向用户与 AI Agent 的确定性、只读 Unreal Engine 项目检查器：15 个聚焦 CLI 分别读取一个明确输入，并输出适合程序消费的 JSON 事实、验证问题和能力边界。

## 当前范围

项目按导航深度分为三个范围；这里的 v1/v2/v3 表示能力层级，不等同于每个工具各自的 `schema_version`。

- **v1 — 项目级发现与对账**：发现 `.uproject`，读取项目描述符，解析实际 Engine，定位项目 Module、Target、直接 Plugin 引用，并分类项目根目录。
- **v2 — Plugin、构建规则与模块入口下钻**：读取一个 `.uplugin`，检查一个 `Build.cs` 的静态规则关系、索引一个 `Target.cs` 的类与成员，并检查一个模块入口的注册、回调清理和生命周期状态。
- **v3 — 单个源码文件下钻**：从一个显式选择的 `.cpp/.cc` 列出 include、类型和指定函数引用，或从一个显式选择的 `.cs` 返回指定名称的全部成员函数及外部类型与方法引用。

这些工具不会生成项目级“总报告”。每个结果保留独立的 Schema、验证结果和责任边界，调用方应沿证据路径逐步选择下一个输入。

维护扫描器实现时，请参阅[扫描器核心程序设计](docs/PROGRAM-DESIGN.md)。

## 环境与安装

- Python `>= 3.10`
- 15 个核心 CLI 仅使用 Python 标准库，无需安装第三方包
- 解析 Engine 安装时需要可访问的 Unreal Engine 目录；无法从 `EngineAssociation` 唯一解析时可显式传入 `--engine-root`

```bash
git clone https://github.com/qloveyzdd/UE_ITPS.git
cd UE_ITPS
python --version
```

## 快速开始

1. 从一个搜索根目录发现 `.uproject`：

   ```bash
   python tools/ue_find_projects.py --search-root D:/Projects
   ```

2. 若结果中只有一个候选，将其作为后续工具的显式输入：

   ```bash
   python tools/ue_read_project_descriptor.py --project D:/Projects/MyGame/MyGame.uproject
   ```

3. 按需要继续检查，而不是一次运行所有工具：

   ```bash
   python tools/ue_inspect_modules.py --project D:/Projects/MyGame/MyGame.uproject
   python tools/ue_resolve_plugins.py --project D:/Projects/MyGame/MyGame.uproject --operation scan --platform Win64 --target-type Editor
   ```

所有 CLI 都提供中英双语帮助：

```bash
python tools/ue_inspect_module_entry.py --help
```

## 15 个聚焦 CLI

| 范围 | CLI | 主要输入 | 能力 | 输出 Schema |
|---|---|---|---|---|
| v1 | `ue_find_projects.py` | `--search-root PATH` | 发现 `.uproject` 候选；遇到多个候选时报告歧义，不擅自选择 | `ue-itps.project-discovery.v1` |
| v1 | `ue_read_project_descriptor.py` | `--project FILE` | 读取一个 `.uproject` 的显式字段、Module 名称、Plugin 声明和未建模字段 | `ue-itps.project-descriptor.v1` |
| v1 | `ue_resolve_engine.py` | `--project FILE`，可选 `--engine-root PATH` | 将 `EngineAssociation` 解析为唯一 Engine，并读取实际 `Build.version` | `ue-itps.engine-resolution.v1` |
| v1 | `ue_inspect_modules.py` | `--project FILE` | 对账项目 Module 声明、`Build.cs` 候选和模块注册入口证据 | `ue-itps.project-modules.v1` |
| v1 | `ue_inspect_targets.py` | `--project FILE` | 发现 `Target.cs` 并分类原生项目证据 | `ue-itps.project-targets.v1` |
| v1 | `ue_resolve_plugins.py` | `--project FILE`，可选 Engine/Profile 参数 | 在一个显式 operation、platform、target-type Profile 下定位 `.uproject` 的直接 Plugin 引用 | `ue-itps.project-plugin-references.v1` |
| v1 | `ue_classify_project_paths.py` | `--project FILE` | 根据项目描述符证据分类项目根目录及其文件系统状态 | `ue-itps.project-paths.v1` |
| v2 | `ue_read_plugin_descriptor.py` | `--plugin FILE` | 读取并校验一个 `.uplugin`，对账其 Module、`Build.cs` 和直接 Plugin 依赖声明 | `ue-itps.plugin-descriptor.v2` |
| v2 | `ue_inspect_module_rules.py` | `--rules FILE` | 提取一个 `Build.cs` 及同文件可达 helper 中的 ModuleRules 设置变更、引用和条件 | `ue-itps.module-rule-relations.v1` |
| v2 | `ue_inspect_target_rules.py` | `--target FILE` | 索引一个 `Target.cs` 中的 TargetRules 类、继承、成员变量和函数 | `ue-itps.target-rule-relations.v1` |
| v2 | `ue_inspect_module_entry.py` | `--rules FILE` | 从 Module 的 `Build.cs` 导航到入口源码，报告注册、回调绑定/清理和紧凑生命周期状态 | `ue-itps.module-entry-state.v12` |
| v3 | `ue_inspect_cs_function.py` | `--source FILE --function NAME` | 返回任意 `.cs` 中该名称的全部类成员函数、外部类型与方法引用 | `ue-itps.cs-function.v1` |
| v3 | `ue_list_cxx_includes.py` | `--source FILE`，可选 `--engine-root PATH` | 列出一个显式 C++ 源码单元的直接 include、条件和唯一文件系统来源 | `ue-itps.cxx-includes.v1` |
| v3 | `ue_list_cxx_types.py` | `--source FILE`，可选 `--engine-root PATH` | 列出 class、struct、enum、继承、成员名称及 UE 类型/成员宏 | `ue-itps.cxx-types.v1` |
| v3 | `ue_inspect_cxx_function.py` | `--source FILE --function NAME`，可选 `--engine-root PATH` | 返回该名称的全部函数定义、声明关系、稳定 `function_id`、外部类型与成员调用 | `ue-itps.cxx-function.v1` |

`ue_resolve_plugins.py` 的 Profile 参数为：

- `--operation`：`scan`、`open_editor`、`build_editor`、`run_game` 或 `cook_package`，默认 `scan`
- `--platform`：默认 `Win64`
- `--target-type`：默认 `Editor`
- `--plugin-name`：按 Plugin Name 筛选，可重复指定；省略时解析全部直接引用

## 显式导航工作流

```text
搜索根目录
└─ ue_find_projects.py
   └─ 唯一 .uproject
      ├─ ue_read_project_descriptor.py
      ├─ ue_resolve_engine.py
      ├─ ue_inspect_modules.py
      │  └─ 选择一个 Build.cs
      │     ├─ ue_inspect_module_rules.py
      │     └─ ue_inspect_module_entry.py
      ├─ ue_inspect_targets.py
      │  └─ 选择一个 Target.cs
      │     └─ ue_inspect_target_rules.py
      │        └─ 从成员事实中选择一个函数名
      │           └─ ue_inspect_cs_function.py
      ├─ ue_resolve_plugins.py
      │  └─ 选择一个已解析的 .uplugin
      │     └─ ue_read_plugin_descriptor.py
      │        └─ 选择该 Plugin 的一个 Build.cs
      │           ├─ ue_inspect_module_rules.py
      │           └─ ue_inspect_module_entry.py
      └─ ue_classify_project_paths.py

显式选择一个 .cpp/.cc
├─ ue_list_cxx_includes.py
└─ ue_list_cxx_types.py
   └─ 从成员事实中选择一个函数名
      └─ ue_inspect_cxx_function.py

显式选择一个 .cs
└─ 按名称选择类成员函数
   └─ ue_inspect_cs_function.py
```

导航规则：

1. 多个 `.uproject` 是歧义，不应由调用方随意取第一个。
2. Plugin 定位默认使用项目的 `EngineAssociation`；只有调用方已有明确 Engine 根目录时才传 `--engine-root`。
3. Module、Target、Plugin 和函数必须从用户输入或前一步输出的证据中显式选择。
4. 三个 C++ 源码工具只接受 `.cpp/.cc`；它们自动查找同目录或常规 `Private` → `Public`/`Classes` 映射中的同名头文件。零个候选时 `header` 为 `null`，多个候选时同时返回 warning。
5. `ue_inspect_cxx_function.py` 按函数名返回所有同名定义；owner、参数、限定符和 `function_id` 是输出事实，不是输入选择器。
6. `ue_inspect_cs_function.py` 接受任意 `.cs`，按函数名返回全部同名类成员及其外部类型和方法引用；同类调用也会返回，但不会递归展开。

## 输出、验证与退出码契约

正常 JSON 结果保持以下顶层顺序：

```text
schema_version
<该工具的事实字段>
validation
limits
```

- `validation.status` 为 `ok`、`warning` 或 `error`。
- `validation.problem_count` 等于 `validation.problems` 的项目数；每个问题带有严重级别、稳定问题码和相关证据。
- `limits.responsibility` 说明该工具负责回答什么；`limits.boundaries` 说明结果不能证明什么。
- `warning` 表示扫描已完成且问题非阻断，退出码仍为 `0`。不要把它改写成 `ok`。

| 退出码 | 含义 |
|---|---|
| `0` | 扫描完成，未发现阻断问题；结果可能为 `ok` 或 `warning` |
| `1` | 扫描完成，但 `validation.status` 为 `error` |
| `2` | 命令行参数、输入或读取失败 |

语法错误通常由 `argparse` 写入 stderr。三个 C++ 源码 CLI 和通用 C# 函数 CLI 在输入/读取失败时会在 stdout 返回带 Schema 的 JSON 错误文档并退出 `2`。因此自动化调用方应同时检查退出码、stdout JSON 和 stderr。

## 常见用法

### 读取一个 Plugin，再检查其构建规则

```bash
python tools/ue_read_plugin_descriptor.py --plugin D:/Projects/MyGame/Plugins/MyPlugin/MyPlugin.uplugin
python tools/ue_inspect_module_rules.py --rules D:/Projects/MyGame/Plugins/MyPlugin/Source/MyPlugin/MyPlugin.Build.cs
```

第一条命令会给出 Plugin 声明、Module 与 `Build.cs` 候选；第二条只报告所选规则文件中的静态设置变更和条件，不计算 UnrealBuildTool 的最终有效配置。

### 从类型索引导航到指定函数

```bash
python tools/ue_list_cxx_types.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp
python tools/ue_inspect_cxx_function.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp --function BeginPlay
```

第二条命令的结果包含所有 `BeginPlay` 定义；没有匹配定义时返回结构化 `function-not-found` 错误并退出 `1`。

### 从 TargetRules 类索引导航到 C# 函数

```bash
python tools/ue_inspect_target_rules.py --target D:/Projects/MyGame/Source/MyGame.Target.cs
python tools/ue_inspect_cs_function.py --source D:/Projects/MyGame/Source/MyGame.Target.cs --function MyGameTarget
```

第一条命令只索引 TargetRules 类及其成员变量和函数；第二条按名称返回全部匹配成员及其外部类型和方法引用。

## 仓库结构

```text
.
├─ tools/
│  ├─ ue_*.py                  # 15 个稳定 CLI 入口
│  ├─ ue_project_tools/        # 扫描、解析、验证和 JSON 序列化实现
│  └─ *_lyra_*.ps1/.py         # Lyra 基线、运行证据和资产查询辅助工具
├─ tests/
│  ├─ support.py               # 共享 CLI 清单、断言和临时 UE fixture
│  └─ test_*.py                # 44 项单元与 CLI 导航测试
├─ docs/PROGRAM-DESIGN.md       # 扫描器架构、契约、测试与扩展规则
├─ .agents/skills/             # Agent 使用这些 CLI 时的仓库内操作约定
└─ LyraStarterGame/            # 可选的本地外部烟雾测试项目；被 Git 忽略
```

`LyraStarterGame/` 不是仓库分发内容。没有该目录时，15 个核心 CLI 和测试套件仍可使用。

C++ 源码查询内部按上下文、include、类型、函数和共享事实投影拆分；
`source_unit.py` 仅保留兼容导入入口。各 CLI 的公开 Schema 不受该内部结构影响。

## 测试

运行完整测试套件：

```bash
python -m unittest discover -s tests -v
```

当前套件已从实时 `tests/` 目录验证为 **44 项测试**，覆盖：

| 测试模块 | 关注点 |
|---|---|
| `test_cli_contracts.py` | 双语帮助、公共 JSON 外层、严格 JSON 读取、退出码与输入失败 |
| `test_navigation_flow.py` | 15 个 CLI 形成一条可执行的显式导航链 |
| `test_project_scanners.py` | 项目发现、描述符、Engine、Module、Target、Plugin 与目录分类 |
| `test_plugin_descriptor.py` | `.uplugin` 对账、重复字段和缺失 `Build.cs` |
| `test_rule_scanners.py` | ModuleRules 变更与 TargetRules 类、变量和函数索引 |
| `test_cs_functions.py` | 通用 C# 函数选择、外部类型与方法引用、重载和缺失函数 |
| `test_module_entry.py` | Module 注册、回调绑定/清理、默认模块和损坏分隔符 |
| `test_source_context.py` | 三个 C++ 源码工具共享上下文、自动头文件和项目歧义 |
| `test_source_includes.py` | 直接 include 来源、生成头、缺失引用与预处理条件 |
| `test_source_types.py` | 类型、继承、成员和 UE 反射宏 |
| `test_source_functions.py` | 声明匹配、外部引用、重载稳定性和缺失函数 |

测试使用临时目录构造最小 Unreal 项目、Engine、Plugin、规则文件和 C++ 源码，不依赖本机安装的 Unreal Engine，也不修改真实项目。

## Lyra 5.6.1 烟雾基线

仓库支持把本地 `LyraStarterGame/` 作为大型只读参考项目。当前基线目标为：

- 项目：`LyraStarterGame/LyraStarterGame.uproject`
- Engine：UE `5.6.1`
- Plugin Profile：`scan / Win64 / Editor`
- 基线内容身份：排除 UE/IDE 生成目录后，对参考项目文件生成 SHA-256 清单

最小烟雾检查：

```bash
python tools/ue_find_projects.py --search-root LyraStarterGame
python tools/ue_read_project_descriptor.py --project LyraStarterGame/LyraStarterGame.uproject
python tools/ue_resolve_engine.py --project LyraStarterGame/LyraStarterGame.uproject
python tools/ue_inspect_modules.py --project LyraStarterGame/LyraStarterGame.uproject
python tools/ue_inspect_targets.py --project LyraStarterGame/LyraStarterGame.uproject
python tools/ue_resolve_plugins.py --project LyraStarterGame/LyraStarterGame.uproject --operation scan --platform Win64 --target-type Editor
python tools/ue_classify_project_paths.py --project LyraStarterGame/LyraStarterGame.uproject
```

本地基线复核中，上述 7 个项目级扫描均完成并退出 `0`：发现、描述符、Engine、Module、Target 为 `ok`；Plugin 定位与根目录分类为非阻断 `warning`。烟雾结果用于验证大型真实目录上的静态导航，不替代 44 项自动化测试，也不证明 Lyra 可以编译或运行。

当前 warning 基线分别是：Win64/Editor Profile 下 `D3DExternalGPUStatistics` 与 `EOSReservedHooks` 两个直接 Plugin 引用未定位；项目根目录中的 `.claude` 与 `.codex` 未被目录分类器建模。它们是需要保留的扫描事实，不应在调用侧静默改写为 `ok`。

## 真实项目测试矩阵

除 Lyra 外，后续可靠性与通用性验证使用以下公开 UE C++ 项目。它们是外部测试输入，不属于仓库分发内容；表中的版本来自项目当前默认分支或指定开发分支，正式纳入基线时必须固定提交，并记录内容指纹。

本地检出统一放在 `ExternalProjects/<项目目录>/`，整个 `ExternalProjects/` 由仓库根 `.gitignore` 排除，不进入当前工程提交。

| # | 项目 | 目标版本/分支 | 主要测试角色 | 获取与许可注意事项 |
|---:|---|---|---|---|
| 1 | [JanSeliv/Bomber](https://github.com/JanSeliv/Bomber) | UE 5.7 / `master` | 现代模块化主案例：GAS、Game Feature、Iris、Mover、MVVM、StateTree、Steam 联机 | 使用递归子模块；仓库含精简地图，完整美术内容另见 Releases；MIT |
| 2 | [tomlooman/ActionRoguelike](https://github.com/tomlooman/ActionRoguelike) | UE 5.6 / `master` | 常规完整游戏主案例：C++/Blueprint、AI、EQS、联机、存档、异步资源加载 | 主分支含实验性功能；仓库未声明独立许可证 |
| 3 | [intrxx/Multiplayer-Shooter](https://github.com/intrxx/Multiplayer-Shooter) | UE 5.2 / `main` | 中型多人射击回归案例：RPC、服务器回溯、客户端预测、会话、HUD/UI | 部分功能仍为 WIP；仓库未声明独立许可证 |
| 4 | [tomlooman/EpicSurvivalGame](https://github.com/tomlooman/EpicSurvivalGame) | UE 5.2 / `master` | 旧代码风格兼容案例：多人、生存玩法、AI、UMG、存档 | 作者明确标记为较旧的编码标准与约定；MIT |
| 5 | [intrxx/Obsidian](https://github.com/intrxx/Obsidian) | UE 5.7 / `main` | 大型 GAS/ARPG 案例：Game Feature、CommonUI、复制背包、装备、程序化物品、存档 | 使用递归子模块；项目仍在持续开发；GPL-3.0 |
| 6 | [vahabahmadvand/ActionRPG_UE5](https://github.com/vahabahmadvand/ActionRPG_UE5) | UE 5.7 / `main` | 资源与 Blueprint 占比较高的混合案例：GAS、Enhanced Input、LoadingScreen 模块 | 官方 ActionRPG 样例的社区升级仓库；未声明独立许可证 |
| 7 | [carla-simulator/carla](https://github.com/carla-simulator/carla) | UE 5.5 / `ue5-dev` | 极端规模与非标准结构压力案例：嵌套 `.uproject`、CMake、Python API、ROS2、第三方库、自定义插件 | 需要额外资产和复杂构建环境；不进入快速回归集；MIT |

建议执行分层为：1–4 组成常规回归集，5–6 组成复杂 Gameplay/资源关系集，7 只用于大型仓库压力测试。仓库链接和版本声明只是候选身份，不能替代本地提交哈希、子模块提交和 SHA-256 基线。

## 只读边界

15 个核心 CLI 只读取并分析现有文件。它们不会：

- 修改 `.uproject`、`.uplugin`、C++、Build.cs、Target.cs、Config、资产或 Engine 文件
- 启动 Unreal Editor、编译项目、Cook、Package 或运行游戏
- 写注册表、安装 Engine、启用 Plugin 或生成项目文件
- 递归跟踪依赖源码、构建完整调用图或推导运行时状态

`--operation` 只是 Plugin 适用性判断的静态上下文，不会执行相应操作。

## 已知限制

- 所有结论都是静态源码或描述符证据，不是编译、UHT、UnrealBuildTool、Editor 或运行时证明。
- Plugin 项目扫描只解析 `.uproject` 的直接引用，不计算完整 Plugin 依赖闭包；单 Plugin 工具也只报告其直接依赖声明。
- ModuleRules 工具是规则相关性投影，TargetRules 工具是类与成员索引；两者都不是 C# AST 或最终有效 UBT 结果。
- 通用 C# 函数工具从局部声明及非调用成员访问中的未绑定类型限定符提取外部类型，并返回包括同类调用在内的方法引用；已知类型的根接收者会替换为类型表达式，其余成员链保持不变。工具不执行或展开被调用函数，也不推断重载绑定。
- Module 入口工具只报告支持的注册、回调和状态模式；无法看到的外部调用保留为未解析影响。
- 源码工具只读取所选 `.cpp/.cc` 及自动确定的唯一同名头文件，不递归读取 include、基类或被调用函数实现。
- include 的文件系统唯一来源不等于有效编译 include 路径，也不能证明 `Build.cs` 依赖声明正确。
- 目录分类只报告角色与当前文件系统状态，不能用于判断删除安全性、自包含性或可重建性。
