# UE-ITPS

面向 Unreal Engine 项目的可验证功能复用、工程知识管理与增量信任编程系统。

当前阶段不开发具体玩法或信任系统，先以 **UE 5.6.1 运行基线 + Epic 可追溯 Lyra 快照** 为可复现研究对象，归档工程组成、启动架构并界定最小运行链路。

当前入口：

- [基线与复现状态](.planning/codebase/BASELINE.md)
- [工程栈与依赖全景](.planning/codebase/STACK.md)
- [目录结构与职责边界](.planning/codebase/STRUCTURE.md)
- [Lyra 顶层架构与启动主链](.planning/codebase/ARCHITECTURE.md)
- [最小运行边界](.planning/codebase/MINIMAL-RUNTIME.md)

当前已完成 UE 5.6.1 本机编译与 L0 运行验证，冻结 9,656 个权威文件的 SHA-256 清单，并归档 Engine/Lyra 来源、Target、Module、Plugin、目录职责及核心 Asset Registry 关系。

当前本地 Lyra 工程壳可追溯到 Epic UnrealEngine 历史提交，但不是 `5.6.1-release` 标签的逐字节副本；完整差异与证据边界见基线文档。下一批继续研究启动与生命周期，不急于执行 L1，也不修改或删减 Lyra。
