# UE ITPS

UE ITPS 将 Unreal Engine 工程中的源码、构建声明和 Editor 现场信息提取为结构化事实，供命令行、Agent 和本地文件图谱浏览器使用。检查工具不修改被检查工程；导出器只写入明确指定的结果文件。

## 已实现的组成

| 组件 | 当前能力 |
|---|---|
| [SourceTools](docs/TOOLS.md) | 16 个核心 CLI：工程与构建入口、头源配对、Include 来源、类型与函数、委托、检索视图及分层证据导航 |
| [Editor 与离线工具](edittools/README.md) | 16 个 CLI：Editor 资产与 Blueprint 查询、配置和 C++ 消息扫描、知识图谱合并/校验/比较 |
| [文件图谱](information_pool/README.md) | 将工程、模块、Target、文件和直接 Include 关系写入 SQLite |
| [本地浏览器](show/README.md) | 在浏览器内打开文件图谱，搜索、展开关系并查看证据 |
| [MCP 连接池](mcp_connection_pool/README.md) | 根据宿主提供的连接信息，被动选择兼容 UE 5.8 的只读连接 |

C++/UE 宏与 C# 均由 Tree-sitter 前端解析。源码工具只分析明确选择的文件或配置范围；不执行编译、预处理、跨文件语义绑定或运行时验证。职责标签与导航提示来自人工配置。

当前文件数据库尚未实现提交绑定、不可变快照、增量更新或权威审查；完整业务关系图、自然语言自动路由和 Agent 写入编排也未实现。详见[架构与边界](docs/ARCHITECTURE.md)。

## 安装

需要 Python 3.10 或更高版本。首次克隆后先初始化语法子模块，再安装依赖：

```bash
git submodule update --init parsers/tree-sitter-ue-cpp
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

安装与执行使用同一个 Python 环境。更新语法子模块后需重新安装本地语法包；具体步骤见[开发约定](docs/DEVELOPMENT.md)。

## 快速开始

在仓库根目录执行：

```bash
python sourcetools/ue_list_tools.py
python sourcetools/ue_find_projects.py --search-root D:/Projects
```

从结果中明确选择工程，再按问题选择最小工具。检查一对已选定的同名头源文件：

```bash
python sourcetools/ue_list_cxx_functions.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp D:/Projects/MyGame/Source/MyGame/Public/MyActor.h
python sourcetools/ue_inspect_cxx_function.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp D:/Projects/MyGame/Source/MyGame/Public/MyActor.h --function AMyActor::BeginPlay --include-syntax-flow
```

函数选择名应来自函数清单。输出中的 `validation` 是本次扫描校验，`limits` 说明分析边界；`ok` 不代表编译或运行通过。

## 测试

默认运行不依赖真实 UE 工程、Engine 安装或 Editor 的核心测试：

```bash
python -m tests
```

明确运行本地 Lyra 回归：

```bash
python -m tests --suite lyra
```

测试分组、参考工程前提、各组件命令及最近验证结果统一维护在[测试与验证](docs/TESTING.md)。

## 文档与参考资料

- [工具清单与输出契约](docs/TOOLS.md)
- [实现架构与未完成边界](docs/ARCHITECTURE.md)
- [开发约定](docs/DEVELOPMENT.md)
- [测试与验证](docs/TESTING.md)
- [当前项目状态与长期方向](.planning/PROJECT.md)

`LyraStarterGame/` 和 `ExternalProjects/` 是本地参考工程，不属于工具实现，也不随本仓库分发。`.planning/codebase/` 保存旧版 Lyra 调查，历史证据入口见[基线归档](.planning/codebase/BASELINE.md)；它们不代表当前工具能力或当前 Engine 运行结论。`Saved/` 是忽略跟踪的本地产物，历史运行次数和性能数字不作为当前验收结果。

## 许可证

仓库尚未声明项目级许可证。第三方许可信息见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 `LICENSES/`。
