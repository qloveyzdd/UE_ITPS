# UE ITPS

UE ITPS 是一组面向 Unreal Engine 工程的确定性、只读检查工具。它从明确选择的 `.uproject`、构建规则和 C++ 源文件中提取 JSON 事实，不启动 Editor、不编译工程，也不修改项目内容。

## 当前组成

- `sourcetools/`：23 个静态检查 CLI，负责工程、Engine、Module、Target、Plugin、C++ 源文件和局部关系分析。
- `schemas/`：核心 CLI 的 JSON Schema，采用 Draft 2020-12。
- `edittools/`：16 个 Editor/离线检查 CLI；连接 Editor 的命令只读取已连接节点的现场状态。
- `information_pool/`：把工程、模块、Target、源码和 Include 关系写入 SQLite 文件图谱。
- `show/`：本地打开并浏览文件图谱的 React 页面。
- `mcp_connection_pool/`：被动选择宿主已提供的 UE 5.8 只读 MCP 连接，不负责启动或重连外部进程。

`ExternalProjects/` 和 `LyraStarterGame/` 是检查对象或参考工程，不属于工具运行时实现。仓库内的 `parsers/tree-sitter-ue-cpp` 是独立子模块。

## 安装

需要 Python 3.10 或更高版本：

```bash
python -m pip install -r requirements.txt
```

开发和测试还需要：

```bash
python -m pip install -r requirements-dev.txt
```

## 快速开始

先查看当前工具清单：

```bash
python sourcetools/ue_list_tools.py
```

查找工程后，必须从结果中明确选择一个 `.uproject`：

```bash
python sourcetools/ue_find_projects.py --search-root D:/Projects
python sourcetools/ue_inspect_modules.py --project D:/Projects/MyGame/MyGame.uproject
python sourcetools/ue_list_project_cxx_sources.py --project D:/Projects/MyGame/MyGame.uproject
```

检查一个明确选择的 C++ 文件或同名 `.cpp`/`.h` 文件对：

```bash
python sourcetools/ue_list_cxx_types.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp D:/Projects/MyGame/Source/MyGame/Public/MyActor.h
python sourcetools/ue_inspect_cxx_function.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp D:/Projects/MyGame/Source/MyGame/Public/MyActor.h --function BeginPlay
```

所有核心 CLI 都把结果写到标准输出，并包含 `schema_version`、领域事实、`validation` 和 `limits`。静态结果是源码证据，不等同于 UBT、UHT、编译器、Editor 或运行时结论。

## 文档

- [架构](docs/ARCHITECTURE.md)
- [工具清单](docs/TOOLS.md)
- [开发约定](docs/DEVELOPMENT.md)
- [测试与验证](docs/TESTING.md)

各子组件的使用方式见 [Editor 工具](edittools/README.md)、[文件图谱](information_pool/README.md)、[连接池](mcp_connection_pool/README.md) 和 [本地浏览器](show/README.md)。

## 当前已知限制

`edittools/ue_scan_cxx_gameplay_messages.py` 仍依赖已从核心解析器移除的 `source_declarations` 和 `source_operations`，当前不能导入。新测试将它标记为预期失败，其余 Editor CLI 仍执行契约验证。本次仅重建测试和文档，没有改动产品实现。

## 许可证

仓库尚未声明项目级许可证。第三方许可信息见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 `LICENSES/`。
