# UE Incremental Trust Programming System（UE-ITPS）

## What This Is

UE-ITPS 的长期目标是成为面向 Unreal Engine 项目的功能级工程知识图谱、可验证复用平台与 AI 信任治理层，让程序员只审查真正新增或因上下文变化而失去验证依据的工程知识。

当前项目尚未进入信任系统实现阶段。第一个里程碑以 UE 5.6.1 和 Epic 可追溯的 Lyra 样例快照为可复现基准，先建立对 Lyra 架构、启动流程和最小运行边界的事实认知；这些结论将作为后续设计 Lyra-derived 最小项目及增量信任模型的工程基础。

## Core Value

先用可复现证据理解 Lyra 如何运行，再决定最小项目需要保留什么，避免在错误架构认知上构建信任系统。

## Requirements

### Validated

- [x] UE 5.6.1 源码 Engine 已定位并由 `Build.version`、Target 与运行日志交叉验证。— 2026-07-14
- [x] `LyraEditor Win64 Development` 已完成 455 个动作的项目构建，并通过重复 UBT 验证。— 2026-07-14
- [x] L0 本机曾观察通过：Editor、PIE、默认 Experience、前端 Experience、CommonUI 根布局和正常退出；原始日志于 2026-07-15 被轮转，需重跑留存后恢复为可审计证据。— 2026-07-14
- [x] Lyra 顶层启动主链已归档到 Experience、Game Feature、PawnData、PlayerState ASC、InitState、Input/GAS 与 UI。— 2026-07-14
- [x] UE 5.6.1 实时 Asset Registry 已验证关键 UserFacingExperience、Experience、ActionSet、PawnData 与地图直接依赖。— 2026-07-14
- [x] Engine 运行版本、Git 修订、VS/MSVC/Windows SDK/.NET 工具链已冻结。— 2026-07-15
- [x] Lyra 工程壳已追溯到 Epic UnrealEngine 历史提交，5 处标签差异已解释。— 2026-07-15
- [x] 9,656 个权威文件已生成逐文件 SHA-256 清单，Target、Module、Plugin 与目录职责已归档。— 2026-07-15
- [x] PIE 启动、Experience、玩家等待、回调顺序、Pawn/ASC 所有权与 InitState 静态主链已归档。— 2026-07-15
- [x] Frontend、UserFacingExperience、Host/Join Session、Hard Travel、World 重建与返回前端静态主链已归档。— 2026-07-15
- [x] L0/L1 原始日志的不可覆盖复制、SHA-256 manifest 规则与最小捕获工具已建立。— 2026-07-15

### Active

- [ ] 明确后续长期基线采用当前 Marketplace/Epic 历史快照，还是在隔离副本中对齐 `5.6.1-release` 的 5 处工程壳差异；当前不修改已验证样例。
- [ ] 继续归档 Client、Listen Server、Dedicated Server 与 Seamless Travel 的时序差异及失败边界。
- [ ] 使用已建立的捕获工具重跑 L0，补回可审计原始证据并定位历史 `LogAutomationTest` 异常。
- [ ] 运行 `ShooterGym + ControlPoints` L1 切片，验证 ShooterCore Active、Pawn GameplayReady、ASC、Input→Ability 与 Shooter HUD。
- [ ] 运行并归档 Gauntlet BootTest，补齐自动化基线。
- [ ] 追踪 L1 从 Experience 激活到可操作 Pawn 的实际运行主链，而不仅是源码与资产静态证据。
- [ ] 为关键架构结论绑定可核验的源码、配置、资产或运行日志位置，明确区分事实、推断和待验证假设。
- [ ] 补齐 Ability Set 授予、输入标签到 Ability 激活以及 UI 注入的运行证据。
- [ ] 区分“当前 Lyra 基线可运行所必需的机制”“官方示例玩法内容”“当前最小运行分析中的可选系统”，但本阶段不通过删除组件来证明。
- [ ] 在 L1 通过后收敛 Lyra-derived 最小运行项目的保留边界和删减实验顺序。

### Out of Scope

- 体力冲刺或其他具体玩法功能——当前先理解 Lyra 样例架构，不让单一功能预设系统边界。
- 权威图谱、权威等级、增量审查、自动晋升和信任失效实现——这些属于架构基线建立后的后续里程碑。
- 创建或删减 Lyra-derived 项目——当前只运行和归档已冻结的 Lyra 基线。
- 通过删除插件或资产试错来推断最小依赖——先建立有证据的架构模型，再设计最小化实验。
- 自动发现任意 UE 项目的 Feature Graph 或 Pipeline Graph——当前只研究一个固定官方样例。
- 修改 Engine、Lyra Gameplay、Blueprint 或二进制资产——本阶段以只读调查和可复现运行验证为主。
- 支持 UE 5.6.1 之外的版本兼容、升级或迁移。
- Perforce、私有 Engine、跨项目权威库、企业审批、权限体系、内网部署和商业化能力。
- 完整知识图谱数据库、可视化编辑器、MCP 产品接口或通用 Agent 执行层。

## Context

当前 AI 辅助 UE 编程的根本问题不是代码产量不足，而是缺少可靠的项目上下文：AI 不知道已有标准实现、功能跨越哪些 C++ 与资产节点、一次修改影响哪些生命周期和网络边界，也无法把上一次正确结果沉淀为下一次可复用的证据。

长期系统仍将围绕 Code Graph、Feature Graph、Lineage Graph，以及 Feature、Pipeline、Implementation、Decision、Authority Context、Evidence 和 Review Boundary 等概念展开。权威必须分别作用于节点、连接和完整管线，并绑定引擎、项目、插件、平台、构建、网络、测试及代码版本上下文。

但这些模型只有在正确理解真实 UE 工程架构后才有意义。Lyra 集成了 Experience、Game Feature Plugin、Modular Gameplay、Pawn Data、Gameplay Ability System、Enhanced Input、Gameplay Tags、Common UI、武器、队伍、死亡与重生等机制，是第一个合适的参考项目；它不是未来所有 UE 项目的强制架构。

本里程碑采用第一性原理顺序：

```text
固定 UE 5.6.1 与 Epic 可追溯 Lyra 快照
→ 证明项目可生成、编译、启动和运行
→ 追踪启动与 Pawn 初始化主链路
→ 归档模块、插件、资产与运行时职责
→ 区分必要机制、示例内容和可选系统
→ 提出最小运行边界假设
→ 下一里程碑再通过派生项目验证
```

2026-07-12 完成的“体力冲刺增量信任 MVP”研究建立在过早选定具体玩法的前提上。该研究没有删除，已整体归档为历史探索，但不再驱动当前需求和路线图。

## Constraints

- **Engine 基线**：固定 UE 5.6.1，不使用 UE 5.7 结论替代实际 5.6.1 行为。
- **项目基线**：使用已冻结且可追溯到 Epic 历史的 Lyra 样例快照，不先创建删减版或自定义派生版。
- **调查优先**：当前先理解与归档，不实现具体玩法和信任系统。
- **只读优先**：除构建生成物和必要的本地运行配置外，不修改 Lyra 源码、Blueprint 或资产。
- **事实可追溯**：每个关键架构结论必须引用源码、配置、资产、构建输出或运行证据；无法验证的内容明确标为假设。
- **可复现性**：版本、来源、插件、Target、构建配置、启动参数与所选 Experience 必须能够在另一环境中复现。
- **最小化顺序**：不得从“看起来可以删除”推导最小依赖；先观察原版运行，再设计隔离且可回滚的删减实验。
- **架构中立**：Lyra 是首个参考架构，不是长期数据模型唯一允许的 UE 架构。
- **范围控制**：首个里程碑只覆盖影响最小运行与核心启动链路的架构，不追求逐个解释所有 Lyra 玩法系统。

## Success Signals

- 在记录明确的环境、源码修订和文件指纹下，当前 Lyra 基线可以重复生成、编译、启动并进入选定官方 Experience。
- 架构归档能够从项目入口解释到可操作 Pawn 出现，且每个关键跳转都有源码、配置、资产或日志证据。
- 模块、插件、Game Feature 和核心对象的职责边界清晰，不把示例玩法内容误认为引擎或框架必需机制。
- 对关键初始化顺序、数据来源、扩展点和运行时所有权的描述不存在互相矛盾的结论。
- 下一阶段能够根据归档提出一个有证据的 Lyra-derived 最小运行方案，并列出尚需实验验证的依赖，而不是凭文件名猜测。

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Engine 基线固定为 UE 5.6.1 | 降低环境漂移，匹配当前实际目标版本 | ✓ 本机验证通过 |
| Epic 可追溯 Lyra 快照作为首个可复现基准 | 先理解官方样例的真实运行链路，再判断哪些部分可删减 | △ 本地指纹通过；L0 曾观察但原始日志待补，非标签镜像，L1 待验证 |
| 架构归档先于具体玩法与信任系统实现 | 避免在错误或过窄的 Lyra 认知上设计长期抽象 | ✓ 保持当前顺序 |
| 当前不创建 Lyra-derived 最小项目 | 最小化应建立在基线运行证据和依赖分析之上 | ✓ 等待 L1 |
| L1 首选 ShooterGym + ControlPoints | 保留完整 Lyra 主链，同时避免 ShooterMaps 和数百至数千地图软依赖 | ✓ 已由 Asset Registry 选定 |
| 关键架构结论必须绑定工程证据 | 将可确定事实与推断分开，为未来权威模型建立正确习惯 | ✓ 已用于本次归档 |
| 体力冲刺研究归档而不删除 | 保留历史思考，同时阻止旧范围继续驱动当前路线图 | ✓ 已归档 |
| Session 成功与 Travel/World/Experience Ready 分开验证 | Session 回调发生在实际旅行之前，不能提前继承权威 | ✓ 已写入 Travel 管线 |
| 原始日志先捕获、后评估 | 防止 UE 日志轮转和“有日志即通过”的错误晋升 | ✓ 协议与工具已就绪，待重跑 L0 |
| Lyra 是参考架构而非长期唯一标准 | 为未来支持非 Lyra、非 GAS 和项目自定义架构保留空间 | ✓ 保持架构中立 |

## Evolution

本文档在阶段转换和里程碑边界持续演化。

**每次阶段转换后：**

1. 已失效的需求移入 Out of Scope 并记录原因。
2. 已交付并被验证的需求移入 Validated，并标注阶段。
3. 新出现且属于当前目标的需求加入 Active。
4. 将影响未来工作的关键取舍加入 Key Decisions。
5. 检查 What This Is 是否仍与实际产品一致。

**每个里程碑完成后：**

1. 复查全部章节。
2. 确认 Core Value 仍是最高优先级。
3. 审计 Out of Scope 的延期或排除理由是否仍成立。
4. 使用真实运行结果、工程证据和验证指标更新 Context。

---
*Last updated: 2026-07-15 after mapping Frontend/session/travel and establishing immutable runtime-log capture*
