<!-- generated-by: gsd-doc-writer -->
# UE ITPS 架构

## 系统概览

UE ITPS 是一套面向 Unreal Engine 工程的只读检查与关系浏览系统。它接收调用方明确选择的 `.uproject`、`.uplugin`、`Build.cs`、`Target.cs`、C++ 源文件或运行中的 Unreal Editor 会话，输出带证据、校验状态和能力边界的确定性 JSON；这些静态与现场事实还可以被汇总为绑定 Git 提交的不可变 SQLite 信息池快照，并由本地浏览器加载展示。整体采用“薄 CLI 入口 → 聚焦领域服务 → 统一结果契约”的分层结构，信息池与 Editor 工具则作为独立管线复用或补充核心探针，不替代 UnrealBuildTool、UnrealHeaderTool、编译器、Editor 或运行时验证。

## 组件图

```text
显式文件入口                         运行中的 Unreal Editor
     │                                        │
     ▼                                        ▼
+----------------+                  +----------------------+
| sourcetools/ue_*.py |             | edittools/ CLI       |
| 21 个薄 CLI    |                  +----------+-----------+
+-------+--------+                             │ Remote Execution
        │                                      ▼
        ▼                           +----------------------+
+------------------------+         | Editor 运行时适配层  |
| sourcetools/ue_project_tools |   +----------+-----------+
| 领域服务与解析器       |                    │
+-----+-------------+----+                    │
      │             │                         │
      ▼             ▼                         ▼
+-----------+  +-----------+             确定性 JSON
| Clang/C# TS|  | 图算法层  |
+-----+-----+  +-----+-----+
      └──────┬───────┘
             ▼
       确定性 JSON
             │
             ▼
+--------------------------+
| information_pool/        |
| 探针编排、图模型、SQLite |
+------------+-------------+
             │ 不可变快照
             ▼
+--------------------------+
| show/ 本地关系浏览器     |
| sql.js + React + Cytoscape|
+--------------------------+
```

`schemas/` 与 `edittools/schemas/` 分别约束静态 CLI 和 Editor CLI 的 JSON 输出；它们是各自管线的公共契约层，未在图中单独画成运行节点。

## 数据流

### 静态项目检查

1. 调用方通过 `sourcetools/ue_*.py` 传入一个搜索根、项目描述符、构建规则文件或 C++ 源文件。CLI 只负责参数、双语帮助、退出码和 JSON 输出。
2. `sourcetools/ue_project_tools/` 中对应的领域服务校验入口并限定扫描边界；遇到多个候选项目、Plugin 或伴随源码时返回歧义或警告，不自行猜测目标。
3. 描述符与版本文件由严格 JSON/Unreal JSON 读取器解析；C++ Source 由 Clang 按选定编译数据库建立翻译单元，C# 继续由 Tree-sitter 投影。UE 宏、委托和生命周期使用领域投影补充，依赖、继承、循环和影响查询使用确定性图算法处理。
4. 领域结果通过公共组装器补充 `schema_version`、`validation` 和 `limits`，稳定序列化到 stdout。调用失败、扫描阻断和带警告的完成状态通过不同退出码表达。
5. 消费方用 `schemas/` 下同名 JSON Schema 校验结果，并根据 `limits` 判断这些静态事实不能证明的运行时语义。

### Editor 现场检查

1. `edittools/` 中的 CLI 根据 `.uproject` 解析项目与 Engine 上下文，再发现与目标工程匹配的 Unreal Editor Remote Execution 会话。
2. `EditorSession` 对同一 Engine 的命令连接加进程锁，将请求分派给 Editor 进程内的 `ue_editor_tools/runtime/` 操作。
3. 运行时适配器通过 Gameplay Tags、Asset Registry 和 Blueprint API 读取标签、引用、图节点、Pin 与消息发布/订阅事实；[`edittools/ue_editor_tools/scanner.py`](../edittools/ue_editor_tools/scanner.py) 分批聚合并排序结果。
4. CLI 将 Editor 身份、脏包状态和领域事实包装为只读 JSON。需要关系数据时，[`edittools/ue_editor_tools/graph_export.py`](../edittools/ue_editor_tools/graph_export.py) 再把扫描结果转换为节点、关系和证据数组。

### 信息池构建与查询

1. `information_pool/build_information_pool.py` 要求输入工程处于明确的 Git 提交，并确认工程子树和信息池位置符合构建约束。
2. `probe_adapter.scan_project()` 复用核心静态探针，对项目结构和 C++ 源码单元并行扫描；源码内容哈希用于复用缓存。
3. `build_graph_model()` 将探针文档归一化为稳定节点、出现位置、语义关系和关系证据，再写入隔离的候选 SQLite 数据库。
4. 候选库通过 SQLite 完整性、外键、数量、证据链和全文索引验证后，构建器再次确认 Git 修订未变化，将数据库移入 `snapshots/`，最后通过 [`information_pool/ue_itps_information_pool/manifest.py`](../information_pool/ue_itps_information_pool/manifest.py) 原子替换池目录中的激活清单。
5. [`information_pool/query_information_pool.py`](../information_pool/query_information_pool.py) 从激活或指定历史快照执行搜索、继承、影响、调用者、循环、最短路径、测试范围与快照差异查询，并输出 JSON。

### 本地关系浏览

1. 用户在 `show/` 页面中显式选择一个信息池 `.sqlite3` 快照；文件由内置 [`show/public/vendor/sql-asm.js`](../show/public/vendor/sql-asm.js) 加载到浏览器内存。
2. `GraphDatabase` 验证必要表，执行节点搜索、邻接遍历、最短路径和类级成员关系聚合。
3. `GraphExplorer` 将查询结果转换为 Cytoscape 节点与边，提供单节点浏览、多节点关系、证据明细和成员关系展开；浏览器不修改快照。

## 关键抽象

| 抽象 | 位置 | 职责 |
|---|---|---|
| `BilingualArgumentParser` / `result_document()` | [`sourcetools/ue_project_tools/common.py`](../sourcetools/ue_project_tools/common.py) | 统一静态 CLI 的双语参数处理、失败信封、Validation、Limits 与稳定 JSON 契约。 |
| Clang C++ 前端 | [`sourcetools/ue_project_tools/clang_frontend.py`](../sourcetools/ue_project_tools/clang_frontend.py) | 读取编译数据库，建立 C++ 翻译单元并输出类型、函数、继承、调用、变量、诊断和实际 include 事实。 |
| Tree-sitter C# 前端 | [`sourcetools/ue_project_tools/syntax_tree.py`](../sourcetools/ue_project_tools/syntax_tree.py) | 投影 Build.cs、Target.cs 和普通 C# 的声明、调用与位置事实。 |
| `DependencyGraph` | [`sourcetools/ue_project_tools/dependency_graph.py`](../sourcetools/ue_project_tools/dependency_graph.py) | 保存确定性的类型依赖节点与边，支持循环、继承和反向影响等图查询。 |
| `list_source_types()` 源码单元入口 | [`sourcetools/ue_project_tools/source_unit.py`](../sourcetools/ue_project_tools/source_unit.py) | 从一个显式 C++ 文件及唯一可推导伴随文件组装类型、成员和声明锚点结果。 |
| `EditorSession` | [`edittools/ue_editor_tools/remote_client.py`](../edittools/ue_editor_tools/remote_client.py) | 发现、选择并串行连接目标 Editor 会话，将结构化操作分派到 Editor 进程。 |
| `scan_gameplay_messages()` | [`edittools/ue_editor_tools/scanner.py`](../edittools/ue_editor_tools/scanner.py) | 分批扫描 Blueprint 消息节点，归并静态 Channel、动态连接与 Tag 引用者。 |
| `ProjectProbe` / `SourceUnitProbe` | [`information_pool/ue_itps_information_pool/probe_adapter.py`](../information_pool/ue_itps_information_pool/probe_adapter.py) | 定义信息池构建所消费的项目级与源码单元级探针结果，并承载缓存和并行扫描元数据。 |
| `Graph` / `build_graph_model()` | [`information_pool/ue_itps_information_pool/graph_model.py`](../information_pool/ue_itps_information_pool/graph_model.py) | 将多类探针事实归一化为稳定 ID 的节点、出现位置、关系与证据。 |
| `build_information_pool()` | [`information_pool/ue_itps_information_pool/builder.py`](../information_pool/ue_itps_information_pool/builder.py) | 编排 Git 修订检查、扫描、建图、候选库验证、不可变快照落盘与原子激活。 |
| `GraphDatabase` | [`show/app/lib/graph-db.ts`](../show/app/lib/graph-db.ts) | 在浏览器中只读打开信息池快照，验证结构并提供搜索、图遍历和成员关系展开。 |

## 目录结构与职责

```text
.
├─ sourcetools/              # 21 个正式静态 CLI 及其领域实现
│  └─ ue_project_tools/      # 解析、源码事实、图算法和公共输出组件
├─ schemas/                  # 静态 CLI 的公共及逐工具 JSON Schema
├─ edittools/                # 运行中 Editor 的独立只读 CLI、运行时适配器与 Schema
├─ information_pool/         # 提交绑定的图快照构建器、查询器和 SQLite 存储层
├─ show/                     # 只读加载快照的本地 React 关系浏览器
├─ tests/                    # 静态工具池的临时工程、契约与端到端测试
├─ data/                     # 本地信息池数据与生成快照的放置区域
├─ LyraStarterGame/          # 当前本地 Unreal/Lyra 参考基座
├─ ExternalProjects/         # 可选的外部 Unreal 参考工程
└─ docs/                     # 设计、架构和维护说明
```

该结构按事实来源和副作用边界拆分：`sourcetools/` 只读取磁盘上的 Unreal 项目与源码；`edittools/` 必须连接运行中的 Editor，因此保持独立的连接、运行时和 Schema；`information_pool/` 是唯一负责生成持久化派生快照的子系统；`show/` 只消费已有快照，不依赖扫描实现。`LyraStarterGame/` 与 `ExternalProjects/` 是验证和人工研究输入，不属于正式 CLI 的运行依赖，自动化测试使用 `tests/` 中临时构造的最小工程以保持隔离和可重复性。
