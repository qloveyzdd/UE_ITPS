<!-- generated-by: gsd-doc-writer -->
# UE ITPS

UE ITPS 是面向 Unreal Engine 项目维护者与 AI Agent 的确定性、只读项目检查工具集，可从显式选择的项目、构建规则和 C++ 源文件生成带验证状态与能力边界的 JSON 事实。

仓库提供 21 个 Python CLI，覆盖 `.uproject`、Engine、Module、Target、Plugin、C++ 源码清单、类型关系、依赖关系和局部函数流分析。工具只读取静态证据，不替代 UnrealBuildTool、UnrealHeaderTool、Unreal Editor、编译器或运行时验证。

## 当前状态

- 核心静态工具池已形成 21 个正式 CLI、21 份逐工具 Schema 与 1 份公共 Schema；C++ Source 检索正式以 Clang 编译语义为基座。
- `edittools/` 已提供 16 个只读工具，覆盖 Gameplay Tag、资产依赖、Blueprint 结构、DataTable、按需 DataAsset 属性、Primary Asset、配置、C++/Blueprint Gameplay Message，以及统一逻辑图谱的构建、校验和差异。
- `information_pool/` 已能把静态探针结果构建为绑定 Git 提交的不可变 SQLite 快照；`show/` 可在本地浏览语义关系与最短路径；`mcp_connection_pool/` 负责被动发现并选择 UE 5.8 Editor MCP 连接。
- 当前 Unreal 参考基座为 `LyraStarterGame` + UE 5.8.2。Editor 与多个 PIE Experience 已在本机观察到，但 5.8.2 权威文件指纹、完整 L0/L1 日志以及网络和 Travel 路径仍在重新核验。
- UE 5.6.1 的架构与运行资料只保留为历史对照，不自动视为 UE 5.8.2 的当前事实。长期信任治理系统尚未进入实现阶段，当前重点仍是建立可复现的 Lyra 架构和最小运行边界。

## 安装

需要 Python 3.10 或更高版本。描述符、规则和清单工具不要求安装 Unreal Engine；C++ Source 检索还要求与目标构建 Profile 对应的 `compile_commands.json`。依赖清单自带 libclang 运行时；当编译数据库指定了其他 Clang 资源目录时，应通过 `UE_ITPS_LIBCLANG` 选择匹配版本的动态库。

```bash
git clone https://github.com/qloveyzdd/UE_ITPS.git
cd UE_ITPS
python -m pip install -r requirements.txt
```

如需运行测试，请安装开发依赖：

```bash
python -m pip install -r requirements-dev.txt
```

## 快速开始

1. 查看可用工具及其输入和能力：

   ```bash
   python sourcetools/ue_list_tools.py
   ```

2. 在一个目录下查找 Unreal 项目：

   ```bash
   python sourcetools/ue_find_projects.py --search-root D:/Projects/MyGame
   ```

3. 从返回结果中明确选择一个 `.uproject`，再读取其声明：

   ```bash
   python sourcetools/ue_read_project_descriptor.py --project D:/Projects/MyGame/MyGame.uproject --engine-build-version D:/Epic/UE_5.8/Engine/Build/Build.version
   ```

每个正式 CLI 都将 JSON 写入标准输出，并使用统一的顶层结构：领域事实、`validation` 和 `limits`。当搜索范围内存在多个项目时，发现工具会返回歧义错误和候选列表，不会自行选择。

## 使用示例

### 检查项目结构

```bash
python sourcetools/ue_resolve_engine.py --project D:/Projects/MyGame/MyGame.uproject
python sourcetools/ue_inspect_modules.py --project D:/Projects/MyGame/MyGame.uproject
python sourcetools/ue_inspect_targets.py --project D:/Projects/MyGame/MyGame.uproject
python sourcetools/ue_list_project_cxx_sources.py --project D:/Projects/MyGame/MyGame.uproject
```

结果分别提供 Engine 定位证据、Module 声明与规则对应关系、Target 类型及其直接声明或从项目内基类继承的 `ExtraModuleNames`，以及按 Module 和可见性组织的项目 C++ 源文件清单。

### 检查一个 C++ 源码单元

以下命令从项目根目录自动发现 `compile_commands.json`，也可用 `--compile-database FILE_OR_DIRECTORY` 显式选择。缺少编译数据库或编译命令时会明确失败，不会回退到词法符号猜测。

```bash
python sourcetools/ue_list_cxx_includes.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp
python sourcetools/ue_list_cxx_types.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp --compile-database D:/Projects/MyGame/compile_commands.json
python sourcetools/ue_inspect_cxx_function.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp --function BeginPlay --compile-database D:/Projects/MyGame/compile_commands.json
```

结果包含 Clang 翻译单元实际观察到的 include、类型、函数、继承和调用目标，并保留 UE 宏与委托的领域投影。工具只输出显式选择的文件和唯一可推导的同名伴随文件中的事实，不递归输出 include 或被调用函数的内容。

### 分析项目内 C++ 关系

```bash
python sourcetools/ue_analyze_cxx_dependencies.py --project D:/Projects/MyGame/MyGame.uproject
python sourcetools/ue_query_cxx_hierarchy.py --project D:/Projects/MyGame/MyGame.uproject --class AMyActor
python sourcetools/ue_analyze_cxx_impact.py --project D:/Projects/MyGame/MyGame.uproject --symbol AMyActor
```

结果可用于检查项目内类依赖与循环、查询继承关系，以及反向追踪某个类型的静态影响范围。这些关系是保守的静态证据，不是完整编译器符号表或运行时调用图。

## 相关组件

- [`information_pool/`](information_pool/)：将确定性探针结果构建为绑定 Git 提交的不可变 SQLite 快照，并提供搜索、层级、影响、调用者、循环、最短路径和差异查询。
- [`edittools/`](edittools/)：连接运行中的 Unreal Editor，读取 Gameplay Tag、资产引用、Blueprint 和 Gameplay Message 事实；其前置条件和命令见 [`edittools/README.md`](edittools/README.md)。
- [`show/`](show/)：在本地浏览工程信息池 SQLite 快照中的语义关系，不上传或修改数据库。
- [`schemas/`](schemas/)：21 个正式 CLI Schema 和 1 个公共 Schema，均采用 JSON Schema Draft 2020-12。
- [`docs/PROGRAM-DESIGN.md`](docs/PROGRAM-DESIGN.md)：公共契约、内部边界、测试策略和扩展规则。

## 文档导航

- [快速入门](docs/GETTING-STARTED.md)：安装依赖并执行第一次只读检查。
- [架构说明](docs/ARCHITECTURE.md)：组件边界、数据流和关键抽象。
- [配置参考](docs/CONFIGURATION.md)：命令行参数、配置文件和默认值。
- [开发指南](docs/DEVELOPMENT.md)：本地环境、开发命令和协作约定。
- [测试指南](docs/TESTING.md)：各子系统测试入口、夹具约定和当前门禁。
- [程序设计](docs/PROGRAM-DESIGN.md)：公共输出契约、解析边界和扩展规则。

## 测试

运行正式 CLI 的完整测试套件：

```bash
python -m unittest discover -s tests -v
```

当前测试套件共 67 项，覆盖 CLI 与 Schema 契约、项目导航、Module 与构建规则、Clang C++ 分析、图关系和端到端只读性。测试使用临时工程夹具，不依赖本地 Unreal Engine、`LyraStarterGame/` 或 `ExternalProjects/`。

Editor 工具拥有独立测试套件：

```bash
python -m unittest discover -s edittools/tests -t edittools -v
```

Editor、按需 DataAsset 属性、配置和 Gameplay Message 事实可先由 `edittools/ue_build_knowledge_graph.py` 合并为统一
逻辑图谱，再通过信息池构建命令的 `--knowledge-graph` 参数写入同一个不可变 SQLite 快照。
正式图谱遵循“项目差异优先”：Map 只作为资产和逻辑配置目标，不采集 World Partition 外部分包中的 Actor 或 Component；
Blueprint 只投影静态可达的语义节点和已实现声明；DataAsset 只持久化相对本类或父类默认对象发生变化的属性。

## 能力边界

- Build.cs、Target.cs 和 C++ 结果是受支持语法范围内的静态投影，不执行源码或推断最终 UBT 配置。
- 唯一物理 include 候选不等于编译器实际选择；Plugin 静态依赖也不等于完整有效的构建 Profile。
- Module 入口工具只定位 `IMPLEMENT_PRIMARY_GAME_MODULE` / `IMPLEMENT_MODULE` 所在 `.cpp` 及唯一同名 `.h`；函数流和依赖图仍是保守模型，不证明运行时行为。
- 编译、启动、资产状态、配置合并、网络行为和目标平台行为仍须使用 Unreal 官方工具验证。

## 许可证

本仓库尚未声明项目级许可证；所采用第三方源码思路及其 Apache License 2.0 许可信息见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) 和 [`LICENSES/`](LICENSES/)。
