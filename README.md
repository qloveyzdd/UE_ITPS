# UE-ITPS

面向 Unreal Engine 项目的可验证功能复用、工程知识管理与增量信任编程系统。

当前阶段不开发具体玩法或信任系统，先以 **UE 5.6.1 运行基线 + Epic 可追溯 Lyra 快照** 为可复现研究对象，归档工程组成、启动架构并界定最小运行链路。

当前入口：

- [基线与复现状态](.planning/codebase/BASELINE.md)
- [工程栈与依赖全景](.planning/codebase/STACK.md)
- [目录结构与职责边界](.planning/codebase/STRUCTURE.md)
- [Lyra 顶层架构与启动主链](.planning/codebase/ARCHITECTURE.md)
- [启动、Experience 与玩家初始化管线](.planning/codebase/PIPELINES.md)
- [前端、会话与地图旅行管线](.planning/codebase/TRAVEL.md)
- [L0/L1 运行证据捕获规范](.planning/codebase/RUNTIME-EVIDENCE.md)
- [最小运行边界](.planning/codebase/MINIMAL-RUNTIME.md)

当前已完成 UE 5.6.1 本机编译，冻结 9,656 个权威文件的 SHA-256 清单，并归档 Engine/Lyra 来源、Target、Module、Plugin、目录职责、核心 Asset Registry 关系，以及 PIE 启动、Frontend、Session/Travel、Experience、PlayerState、Pawn、ASC、InitState 和输入的静态主链。原始日志不可覆盖复制与 SHA-256 manifest 工具已经就绪。

当前本地 Lyra 工程壳可追溯到 Epic UnrealEngine 历史提交，但不是 `5.6.1-release` 标签的逐字节副本。L0 曾在本机观察通过，但原始运行日志已被 UE 日志轮转清理，必须重跑并受控留存后才能恢复为可审计权威证据；完整边界见基线文档。当前仍不执行 L1，也不修改或删减 Lyra。
