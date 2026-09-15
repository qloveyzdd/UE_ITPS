# 实现架构与边界

## 当前数据流

```text
.uproject / .uplugin / Build.cs / Target.cs / 显式 C++ 文件
                         │
                         ▼
              sourcetools/ue_project_tools
                         │
              JSON + validation + limits
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
 information_pool/ue_file_graph   命令行或 Agent
            │
        SQLite 文件
            │
            ▼
       show/ 本地浏览器
```

Editor 证据经 `edittools/ue_editor_tools/remote_client.py` 与 `runtime/` 从明确选择的已连接节点取得。配置、C++ Gameplay Message 和知识图谱离线处理也位于 `edittools/`，不能把离线推断当作 Editor 实测。

`mcp_connection_pool/` 是独立的宿主连接目录与匹配库；它不启动 Editor，也不是当前 Editor CLI 的远程执行传输层。

## 源码分析分层

| 层 | 实现位置 | 职责 |
|---|---|---|
| 公开入口 | `sourcetools/ue_*.py` | 参数、退出码与 JSON 输出 |
| 工程与构建 | `descriptor.py`、`engine.py`、`rule_source.py` 等 | 声明读取、文件定位、直接字面量依赖 |
| 文件选择 | `project_cxx_sources.py`、`source_context.py` | 模块边界、头源配对、选中文件上下文 |
| 语法前端 | `cpp_frontend.py`、`syntax_tree.py` | Tree-sitter UE C++ / C# AST 事实 |
| 局部分析 | `source_type_*.py`、`source_function_references.py`、`source_delegate_analysis.py` | 类型成员、函数引用、名称解析及委托操作 |
| 检索展示 | `source_priority.py`、`source_scope.py`、`navigation_guidance.py` | 优先级视图、分页、快照标识和证据导航 |
| UE 规则 | `ue_cpp_conventions.py` | UE 宏、委托 API 与检索规则的共同来源 |

各工具保持独立 Schema，不把后续查询结果塞回较早的工程描述符结果。核心 Schema 位于 `schemas/`，采用 Draft 2020-12。

## 文件图谱与页面

`information_pool/ue_file_graph/` 当前实现文件层图谱，SQLite 契约为 `ue-itps.file-graph.v1`：

- `metadata`：工程路径、Schema 与节点/边/警告数量。
- `nodes`、`edges`：工程、文件及声明关系。
- `edge_evidence`：关系对应的路径、行号、提取器和细节。
- `warnings`：未解析或不完整的扫描信息。

写入使用临时数据库再替换指定输出文件。当前没有 Git 提交绑定、历史快照库、增量更新或通用增删改查服务。源码导航的 `snapshot` 也不等同于数据库版本管理。

页面通过 sql.js 在本地读取该数据库，支持搜索、上下游关系、类型过滤和证据查看。TypeScript 检查、构建与数据库查询测试不等同于浏览器交互的端到端测试。

## 证据与校验边界

- 源码工具读取显式文件；Include 来源定位不会递归读取被引用文件。
- 不执行预处理、编译器重载解析、传递依赖求值或跨文件语义绑定。
- `identified` 委托表示选中文件中有类型证据且 API 形状匹配；`candidate`、`unknown` 保留不确定性。
- `function_id` 与 Scope 选择 ID 依赖文件选择和解析快照，不能当作跨版本稳定实体 ID。
- 人工职责、入口和导航提示属于配置；文件指纹一致不等于已经理解整个类型或系统。
- 核心 CLI 退出码为 0（完成且无阻断问题）、1（扫描发现阻断问题）、2（参数/输入/读取失败）。`warning` 可以与退出码 0 并存。
- 静态校验、模拟 Editor 测试、真实 Editor 观察、构建和运行测试分别报告。

## 尚未完成

完整职责覆盖、业务管线自动识别、跨文件调用图、自动自然语言路由、变更监控、提交绑定信息池、权威晋升/失效、隔离写入和多任务编排均未形成当前产品能力。长期设想保存在[项目状态](../.planning/PROJECT.md)中，不作为现有接口契约。
