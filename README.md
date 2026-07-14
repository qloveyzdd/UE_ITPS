# UE-ITPS

面向 Unreal Engine 项目的可验证功能复用、工程知识管理与增量信任编程系统。

当前阶段不开发具体玩法或信任系统，先以 **UE 5.6.1 原版 Lyra** 为可复现基准，归档顶层架构并界定最小运行链路。

当前入口：

- [基线与复现状态](.planning/codebase/BASELINE.md)
- [Lyra 顶层架构与启动主链](.planning/codebase/ARCHITECTURE.md)
- [最小运行边界](.planning/codebase/MINIMAL-RUNTIME.md)

当前已完成 UE 5.6.1 本机编译与 L0 运行验证，并通过实时 Asset Registry 归档核心 Experience、UserFacingExperience、ActionSet 和 PawnData 关系。

下一步是验证 `ShooterGym + ControlPoints` 的 L1 最小可玩链路；在此之前不修改或删减原版 Lyra。
