# UE ITPS

UE ITPS 是面向 Unreal Engine 工程的只读分析工具集。它把工程描述符、构建规则、C++/C# 源码和可选的 Editor 证据转换成结构化 JSON，并提供文件图谱与本地浏览器，帮助定位类型、函数、依赖、委托和业务链路。

## 能力范围

| 子系统 | 作用 |
| --- | --- |
| `sourcetools/` | 17 个核心 CLI，覆盖工程、构建、模块、Include、类型、函数、依赖和 Scope 导航 |
| `edittools/` | 20 个 Editor/离线 CLI，覆盖资产、Blueprint、配置、Gameplay Message 和知识图谱 |
| `information_pool/` | 扫描工程文件并生成带证据的 SQLite 文件图谱 |
| `show/` | 在浏览器中搜索、查看文件关系和证据 |
| `mcp_connection_pool/` | 被动匹配宿主已经暴露的 UE 5.8 只读连接 |
| `tests/` | 统一运行核心、组件和 Lyra 回归测试 |

核心数据流如下：

```text
.uproject / .uplugin / Build.cs / Target.cs / 源码
                         │
                         ▼
               sourcetools / edittools
                         │
                JSON + validation + limits
                         │
             文件图谱、浏览器或 Agent 查询
```

## 快速开始

需要 Python 3.10 或更高版本。首次使用时初始化语法子模块并安装依赖：

```bash
git submodule update --init parsers/tree-sitter-ue-cpp
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

先发现并明确选择工程：

```bash
python sourcetools/ue_find_projects.py --search-root D:/Projects
python sourcetools/ue_list_tools.py
```

选择工程后按问题调用最小工具。例如查看某个函数：

```bash
python sourcetools/ue_list_cxx_functions.py \
  --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp \
           D:/Projects/MyGame/Source/MyGame/Public/MyActor.h
```

所有 CLI 都输出 JSON。`validation` 表示本次扫描是否有问题，`limits` 表示工具边界；退出码 0、1、2 分别表示完成、发现阻断问题、参数或输入失败。

## 测试

从仓库根目录执行：

```bash
python -m tests                         # 核心 SourceTools
python -m tests --suite components      # Editor/离线、文件图谱、MCP 连接池
python -m tests --suite lyra -v         # 本地 Lyra 回归
python -m tests --suite all             # 核心 + 组件 + Lyra
python -m tests --suite core --list     # 查看选中的模块
```

Lyra 工程默认使用 `LyraStarterGame/LyraStarterGame.uproject`，也可以通过 `UE_ITPS_LYRA_PROJECT` 指定其他路径。缺少参考工程时，`lyra` 和 `all` 会以退出码 2 明确报告环境问题；不会伪装成通过。

页面测试需要进入 `show/` 后执行 `npm test`。这些测试覆盖 TypeScript 检查、生产构建和内存 SQLite 查询，不等同于浏览器端到端测试。

## 设计边界

- 源码工具只解析明确选择的文件或配置范围，不执行预处理、编译、UHT 或跨文件语义绑定。
- 候选调用、委托和有限 UE API 契约用于导航和复核，不代表编译可见性、重载决议或运行时派发已经确定。
- Editor 结果是现场证据；离线扫描结果不能替代真实 Editor、PIE、网络模式或资产行为验证。
- 文件图谱当前是文件级存储，没有 Git 提交绑定、不可变历史快照或增量更新。
- `LyraStarterGame/` 和 `ExternalProjects/` 是本地参考工程，不属于工具实现。

更细的入口说明见 [工具清单](docs/TOOLS.md)，架构边界见 [架构说明](docs/ARCHITECTURE.md)，测试约定见 [测试说明](docs/TESTING.md)。

## 许可证

仓库尚未声明项目级许可证。第三方许可信息见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 `LICENSES/`。
