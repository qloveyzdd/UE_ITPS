# UE ITPS 当前状态

更新日期：2026-10-01。当前能力以仓库代码和测试入口为准；历史调查只作为参考资料。

## 已完成

- 17 个 SourceTools 核心 CLI 及对应 JSON Schema。
- Tree-sitter UE C++/C# 前端、显式头源配对、类型、函数、委托和 Include 事实。
- full、behavior、structure 视图，以及 Scope 四级导航、分页、快照摘要和覆盖审计。
- 有限 UE API 语义契约、候选声明、未解析原因和人工导航提示。
- 20 个 Editor/离线 CLI，覆盖配置、资产、Blueprint、Gameplay Message 和知识图谱。
- SQLite 文件图谱、本地浏览器和被动 MCP 连接池。
- 统一测试入口：核心、组件、Lyra 和全量套件；问答路由测试已纳入组件回归。

## 当前边界

- 静态解析不执行预处理、编译、UHT、运行时派发或跨文件完整语义绑定。
- 候选关系和语义契约不等同于编译诊断；重载、可见性、模板实例化和虚调用仍需人工或独立工具确认。
- Editor 现场证据与离线推断分开保存；Python 测试不替代 Editor、PIE、网络模式或资产行为验证。
- 文件图谱没有 Git 提交绑定、不可变历史快照、增量更新或权威信息晋升。
- 职责标签、入口标签、业务管线识别、自然语言自动路由和跨扫描解析缓存尚未形成完整产品能力。

## 参考工程

`LyraStarterGame/` 和 `ExternalProjects/` 是本地参考工程，不属于工具实现。Lyra 回归默认使用 `LyraStarterGame/LyraStarterGame.uproject`，工程路径可由 `UE_ITPS_LYRA_PROJECT` 覆盖；Engine 版本必须通过实际 `Build.version` 解析，不能从 `EngineAssociation` 直接推断。

## 后续方向

后续工作按实际需求选择：跨文件关系验证、磁盘解析缓存、历史存储、职责覆盖或更可靠的业务链路识别。每项先定义范围和验收标准，不把静态候选结果直接升级为运行时结论。
