# Feature Research

**Domain:** UE 棕地项目的增量信任编程与可验证复用系统  
**Researched:** 2026-07-12  
**Confidence:** HIGH（首个 MVP 范围）；MEDIUM（验证后的扩展顺序）

> **研究边界：** 本文只研究固定 UE/Lyra 版本下“消耗体力的冲刺能力”这一条 Enhanced Input → Gameplay Ability → Gameplay Effect 垂直管线。除标注为“官方事实”的内容外，功能优先级、产品价值、复杂度和版本划分均为基于项目约束的**产品推断**，需要用真实对照实验验证。

## 结论摘要

首个 MVP 不是通用 UE 代码理解器，也不是新的 GAS 框架。UE 已经提供 Enhanced Input、Gameplay Ability、Gameplay Effect、Gameplay Tag、Asset Registry、Data Validation、UHT/UBT 和 Automation Test 等基础机制；Lyra 还提供了以 Input Tag 激活 AbilitySet 中能力的参考管线。[S1][S2][S3][S4][S5][S6]

MVP 应只补齐现有工具之间缺失的产品闭环：**人工策展权威图谱 → 需求定位与上下文匹配 → 可解释复用计划 → 节点/连接/管线三级权威边界 → 受限 Patch → 确定性验证 → 增量审查 → 人工晋升与写回 → 对照实验**。

最需要验证的产品假设是：把“已验证复用”与“仍需审查的非权威增量”分开，能在不提高缺陷遗漏率的前提下降低审查时间。任何不能直接服务于这个假设的能力，都不属于首个 MVP。

## Feature Landscape

### Table Stakes（缺失即无法验证 MVP）

| Feature | Why Expected | Complexity | MVP 边界与验收 |
|---------|--------------|------------|----------------|
| 固定、可复现的 UE/Lyra 基线 | 权威与证据必须依附于确定版本；Lyra 会随 UE 版本持续更新，未锁定版本则同一图谱无法重复解释。[S1] | MEDIUM | 固定 Engine/Lyra 版本、仓库提交、插件清单、目标平台、构建配置、网络模式和测试入口；同一基线可重复构建/测试。**产品推断。** |
| 人工策展的最小权威图谱 | MVP 明确不做通用语义发现，但仍必须有可查询的 Feature、Implementation、Decision、Evidence、Authority Context、Review Boundary | HIGH | 只录入体力冲刺所需节点、连接和完整管线；稳定 ID、实现定位和版本化格式必备；允许文本/JSON/YAML，不要求图编辑器。**产品推断。** |
| 固定冲刺功能契约 | 没有明确行为契约，就无法判断复用是否正确或测试是否充分 | MEDIUM | 明确按下/保持/释放输入、体力门槛、消耗节奏、速度变化、能力结束、耗尽、取消、死亡/失控、客户端/服务器职责；UI、动画和音效仅在影响验证时纳入。**产品推断。** |
| 确定性实体与关系核验 | Asset Registry 可枚举未加载资产；Data Validation 可执行自定义资产规则；UHT/UBT 可验证反射元数据和编译关系。[S5][S6][S7] | HIGH | 验证图谱所指 C++ 符号、模块、插件、资产、Gameplay Tag、Input Action、Input Config、Ability、Effect、Attribute/Test 是否存在且关键机械关系仍成立；不推断功能语义。 |
| 需求到 Feature Family/管线的定位 | 系统必须先证明“这是已知冲刺家族的相似任务”，才能谈复用 | MEDIUM | 对固定需求模板得到唯一候选功能族、对应管线及置信依据；歧义时停止并要求人工选择，不进行开放域搜索。**产品推断。** |
| 上下文指纹与兼容性比较 | GAS 的网络执行、预测、资源成本和 Gameplay Effect 生命周期会影响正确性，不能只比较代码文本。[S3][S4] | HIGH | 比较 Engine/Lyra、插件、模块、平台、构建、网络模式、ASC/Avatar 所有权、激活策略、输入标签、属性/Effect 语义、测试范围及基线提交；不匹配项自动进入待审查。**产品推断。** |
| 复用计划与五类决策 | 用户需要在修改前知道什么被复用、什么将改变 | MEDIUM | 将候选项分类为：原样复用、配置适配、已有实现修改、新增连接、新增逻辑；每项列依据、目标定位、依赖、验证计划和拒绝理由。**产品推断。** |
| 节点/连接/管线三级权威边界 | 两个已验证节点的新连接不等于已验证管线；这是产品防止过度信任的核心约束 | HIGH | 每个输出片段都能回溯到节点、边或管线状态；新连接、生命周期/网络语义变化不得继承节点权威；边界计算同输入同输出。**产品推断。** |
| 受限、可预览、可回滚 Patch | AI 写入若不可控，会抵消信任收益；Git 可生成范围明确的 diff，并可在应用前检查 Patch 是否适用。[S8][S9] | MEDIUM | 显式允许目录/文件；文件数、行数、重试次数上限；先预览再应用；保留 before/after、命令和结果；禁止工作区外写入。二进制资产首版原则上只允许已有引用/配置选择，不做通用二进制编辑。**产品推断。** |
| 分层确定性验证编排 | 编译通过不代表功能正确，但不通过一定不能晋升 | HIGH | 固定顺序执行：图谱引用/关系检查 → UHT/UBT → 约定的 Automation/功能测试 → 必需的网络模式测试；命令行测试可导出机器可读报告。[S7][S10] |
| 证据包与可追溯审计 | 审查者必须能复现“为何信任”和“验证了什么” | MEDIUM | 保存基线提交、权威库版本、计划、Patch、验证命令、退出码、报告摘要、待审范围、审查决定、写回差异；证据不可只存自然语言总结。**产品推断。** |
| 增量审查界面/报告 | 核心价值要求审查者直接看到非权威增量，同时仍可展开完整 Diff | HIGH | 按新逻辑、新连接、上下文偏差、验证失败/缺口分组；展示被折叠的权威复用及证据链接；审查者可逐项确认/拒绝，且完整 Diff 始终可访问。**产品推断。** |
| 人工晋升与原子写回 | 没有写回，审查不能减少未来审查；自动晋升又会破坏权威语义 | HIGH | 仅人工确认后写回新节点/边/管线/Decision/Evidence；代码提交与图谱更新要么共同成功，要么均不晋升；保留 reviewer、时间和验证上下文。**产品推断。** |
| 对照实验与指标采集 | MVP 的目标是验证审查负担下降且遗漏不增加，而非演示代码生成 | HIGH | 同一固定基线、任务和缺陷集，对比“完整 Diff 审查”与“权威边界审查”；记录审查时间、缺陷遗漏、误报/漏报、非权威增量比例、重复实现和第二次任务收益。**产品推断。** |

### Differentiators（应形成竞争优势）

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| 可证明的审查减法 | 不只给“相关代码”，而是明确哪些内容已有适用证据、哪些内容仍需人工判断 | HIGH | 首要差异化；必须用缺陷遗漏不升高作为护栏。**产品推断。** |
| 节点、连接、完整管线权威相互独立 | 避免把可靠组件的新组合误判为可靠系统行为 | HIGH | 对跨 Input Tag → Ability → Effect → Attribute 的组合尤其关键。**产品推断。** |
| 上下文绑定权威与自动失效 | 权威不是永久标签；环境、接口、网络或测试上下文改变时转为 Suspect | HIGH | MVP 先实现精确匹配与显式不匹配；复杂兼容规则延后。**产品推断。** |
| 复用计划先于代码修改 | 让审查者在 Patch 前校正复用方向，减少错误实现后的返工 | MEDIUM | 计划必须引用具体权威资产与证据，而不是通用 LLM 解释。**产品推断。** |
| 语义边界与确定性工具分工 | 人工策展语义；机械事实交给 Asset Registry、Data Validation、UHT/UBT、测试和 Git | HIGH | 降低 LLM 猜测可确定事实的风险；不重复实现 UE 原生验证能力。[S5][S6][S7][S8][S9][S10] |
| 审查结果复利写回 | 第一次人工审查成为第二次相似任务可复用的证据资产 | HIGH | 第二个受控变体任务必须能观察到审查范围或重复实现下降，否则核心飞轮未成立。**产品推断。** |
| 面向功能管线而非纯文件 Diff | 将 C++、Blueprint/资产、标签、配置和测试放回同一功能链路解释 | HIGH | 首版只覆盖人工策展的冲刺管线，不承诺任意 UE 功能。**产品推断。** |
| 可审计的拒绝与不晋升 | “验证失败”“上下文不匹配”“审查拒绝”同样成为未来决策证据 | MEDIUM | 防止失败历史丢失后被重复建议。**产品推断。** |

### Anti-Features（首个 MVP 明确不构建）

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| 任意 UE 项目的自动 Feature/Pipeline 语义发现 | 看起来可快速扩展覆盖面 | 语义正确性难以用确定性方式证明，会把研究风险从权威边界转成开放域理解 | 人工策展单条冲刺图谱；扫描器只核验实体和关系。**产品推断。** |
| 覆盖 Lyra 全项目或所有 GAS 能力 | Demo 更“完整” | 资产、玩法插件、UI、动画和网络分支迅速扩大，无法归因审查收益 | 只覆盖体力冲刺闭环和必要相邻依赖。**产品推断。** |
| 自动把通过测试的实现晋升为 Authoritative | 减少人工操作 | 测试只证明其覆盖的条件；不能替代团队对语义、架构和风险的确认 | 自动生成晋升候选，人工确认后写回。**产品推断。** |
| “权威组件任意组合都可信” | 最大化复用率 | 新连接可改变生命周期、网络、取消和资源语义，产生虚假权威 | 节点、连接、管线分别验证。**产品推断。** |
| LLM 判断符号、资产或编译关系是否存在 | 实现简单、输出自然 | 这些事实可由确定性工具获得；概率判断降低复现性 | Asset Registry/Data Validation/UHT/UBT/测试/Git 作为事实源。 |
| 完整可视化知识图谱编辑器 | 展示效果好、便于探索 | UI 成本高且不验证核心假设 | 版本化结构文件 + 最小列表/报告界面。**产品推断。** |
| 无限 Agent 写权限与自动多轮修复 | 看起来更自治 | 扩大损害半径，模糊每次变更与证据的因果关系 | 路径、规模、次数和超时预算；每轮生成独立 Patch 与证据。**产品推断。** |
| 把代码生成速度作为主指标 | 易测且容易展示 | 可能更快地产生更多需审代码，与减少审查的核心价值相反 | 以审查时间和缺陷遗漏为主指标，生成耗时只做诊断指标。**产品推断。** |
| 通用跨项目权威库与版本兼容矩阵 | 商业想象空间大 | 尚未证明单项目权威可迁移；错误传播成本高 | 单项目、单版本、单管线闭环后再研究。**产品推断。** |
| Perforce、私有 Engine、SSO/RBAC、审批流、内网部署 | 企业客户常见诉求 | 属于治理与交付集成，不影响首个价值假设；会引入大量非核心依赖 | MVP 使用本地 Git 和单一人工 reviewer，保留可替换接口。**产品推断。** |
| 通用 Blueprint 二进制自动编辑/合并 | UE 项目大量逻辑位于资产 | 首版难以安全预览、文本审查和回滚语义变化 | 首版复用既有资产并验证引用；必要新增逻辑优先受控 C++/文本配置，二进制编辑延后。**产品推断。** |
| 完整企业度量平台与实时仪表盘 | 便于管理汇报 | 数据量不足时会制造虚假精度并消耗开发资源 | 导出结构化实验记录和一次性分析报告。**产品推断。** |
| 纯“代码行级”权威折叠 | 容易接到 Diff UI | UE 功能语义跨资产、标签、生命周期和网络边界；行级不等于功能级安全 | 用节点/连接/管线边界解释 Diff，保留完整 Diff 兜底。**产品推断。** |

## Feature Dependencies

```text
[固定 UE/Lyra 基线]
    ├──requires──> [固定冲刺功能契约]
    ├──requires──> [人工策展最小权威图谱]
    │                  └──requires──> [稳定 ID + 实现定位 + Authority Context]
    └──requires──> [确定性实体/关系核验]

[需求定位]
    └──requires──> [人工策展最小权威图谱]

[上下文比较]
    ├──requires──> [Authority Context]
    └──requires──> [确定性实体/关系核验]

[复用计划]
    ├──requires──> [需求定位]
    └──requires──> [上下文比较]
                       └──enables──> [节点/连接/管线权威边界]

[受限 Patch]
    └──requires──> [复用计划 + 写入预算]
                       └──requires──> [分层确定性验证]
                                          └──produces──> [证据包]

[增量审查]
    ├──requires──> [权威边界]
    ├──requires──> [Patch]
    └──requires──> [证据包]
                       └──requires human approval──> [晋升与原子写回]
                                                          └──enhances──> [下一次需求定位/复用计划]

[对照实验]
    ├──requires──> [稳定端到端闭环]
    └──conflicts──> [同时扩大版本、项目、功能和工具范围]
```

### Dependency Notes

- **固定基线先于一切权威结论：** Lyra 是随 UE 更新的样例项目；若版本、提交和插件不固定，失败可能来自环境漂移而不是复用模型。[S1]
- **功能契约先于图谱策展：** 图谱节点存在不等于冲刺行为正确；先定义开始、维持、消耗、耗尽、取消和网络结果，才能策展“完整管线”。**产品推断。**
- **确定性核验先于权威匹配：** 已删除或已改名的资产、标签、类和关系不能继续作为权威依据。Gameplay Tag 必须登记在 Tag Dictionary 中，适合作为明确核验项。[S11]
- **上下文比较先于复用分类：** GAS 的预测、服务器执行、资源成本及 Effect 生命周期会改变实现语义；仅代码相似不足以判定可复用。[S3][S4]
- **复用计划先于 Patch：** 计划是人工纠正错误复用方向的低成本关口。**产品推断。**
- **验证证据先于人工晋升：** UHT/UBT、资产规则和测试是必要证据，但不是充分的权威授权；最终晋升仍由 reviewer 决定。**产品推断。**
- **写回增强下一轮复用：** 没有第二个相似任务，无法验证“每次审查减少未来审查”的复利效应。**产品推断。**
- **对照实验与范围扩张冲突：** 同时支持多版本、多功能或多项目会引入混杂变量，使审查收益无法归因。**产品推断。**

## MVP Definition

### Launch With（首个 MVP）

- [ ] **锁定一个实际可运行的 UE/Lyra 版本与仓库提交** — 版本选择本身待环境验证；不能仅写“UE5 最新版”。
- [ ] **一条明确的体力冲刺验收契约** — 覆盖输入开始/保持/释放、Ability 激活/取消、体力成本/持续消耗、速度 Effect、耗尽结束以及约定网络模式。
- [ ] **人工策展最小权威图谱** — 只包含该管线必需的 Input Action/Input Config/Input Tag、AbilitySet、Gameplay Ability、Gameplay Effect、Attribute/AttributeSet、关键类/模块/插件、测试和关系。
- [ ] **版本化 Authority Context 与 Evidence 格式** — 支持节点、连接、管线独立状态；至少记录代码提交、环境、测试、审查人和依赖条件。
- [ ] **确定性扫描器** — 只检查已策展实体、资产、标签、模块和关系仍存在；输出稳定机器可读结果，不做开放域语义发现。
- [ ] **单一固定需求入口与功能定位** — 接受预定义的冲刺变体任务；映射到已知 Feature Family，不承诺任意自然语言需求。
- [ ] **可解释复用计划** — 五类复用/变更分类，明确引用依据、上下文差异和验证计划。
- [ ] **权威边界计算** — 将新逻辑、新连接、上下文偏差和验证缺口全部纳入人工审查；同输入、同图谱快照、同代码版本输出一致。
- [ ] **受限 Patch 执行器** — 路径/文件/行数/轮次预算、预览、适用性检查、审计和回滚；首版不做通用二进制资产编辑。
- [ ] **固定验证流水线** — 关系检查、UHT/UBT、Data Validation/约定测试和固定网络场景；保存命令、退出码和报告。
- [ ] **最小审查报告** — 默认突出非权威增量，可展开完整 Diff 和证据；支持确认、拒绝、备注。
- [ ] **人工晋升与写回** — 审查确认后，将新节点/连接/管线/Decision/Evidence 写回；失败或拒绝不得晋升。
- [ ] **一次基线实验 + 一次复利实验** — 基线比较完整 Diff 与边界审查；复利实验用第二个受控冲刺变体检查重复实现和审查范围是否下降。

**MVP 完成门槛（产品推断）：**

1. 在相同提交和权威库快照上，扫描、计划、边界与验证结果可重复。
2. 所有新连接、上下文偏差、生命周期或网络语义变化均进入待审范围，不得伪装成权威复用。
3. Treatment 组的审查时间相对完整 Diff 基线下降，同时缺陷遗漏率不高于基线；样本过小时只报告效应量和置信区间，不宣称统计显著。
4. reviewer 确认的知识能写回，并在第二个相似任务中实际减少重复实现或待审范围。

### Add After Validation（v1.x）

- [ ] **Authority 自动失效规则** — 当首个 MVP 证明上下文匹配有效后，加入 Engine/插件/模块接口/网络模式/测试结果变化触发 Suspect。
- [ ] **更多同家族冲刺变体** — 例如不同消耗曲线、不同移动模式或服务器规则；仅在不改变核心架构时扩展，用于测试姊妹实现而非万能参数化。
- [ ] **更精细的 Blueprint/资产只读检查** — 当首版证据显示资产关系是主要审查盲点时增加，不先做通用写入。
- [ ] **失败/拒绝知识检索** — 当同类错误重复出现时，将“不应复用/不应晋升”的证据纳入计划。
- [ ] **多 reviewer 与冲突处理** — 当真实团队试用产生并发审查需求时加入；仍不等于完整 RBAC。
- [ ] **实验报告自动化** — 当样本量足以比较不同任务/审查者时，自动生成效应量、误报/漏报和学习曲线。
- [ ] **有限的第二条垂直管线** — 只有体力冲刺闭环已通过验收，才选择一个能检验模型迁移但复杂度相近的功能。

### Future Consideration（v2+）

- [ ] **受约束的半自动图谱候选发现** — 只生成 Candidate，由人工策展；必须先有足够已验证样本评估精确率和召回率。
- [ ] **多 UE/Lyra 版本兼容与迁移** — 需要明确版本差异、重验证和证据继承规则。
- [ ] **多项目/跨项目权威传播** — 只有单项目上下文失效模型可靠后研究，默认不继承 Authoritative 状态。
- [ ] **非 Lyra、非 GAS 和简化单机架构** — 数据模型保持中立，但实现支持延后到核心闭环成立之后。
- [ ] **安全的 Blueprint/资产 Patch** — 需要可解释 Diff、确定性验证、回滚和审查体验达到与文本 Patch 相当的水平。
- [ ] **Perforce、私有 Engine、企业权限/审批、内网部署** — 商业化阶段能力，不应倒灌首个产品实验。
- [ ] **完整图谱可视化与影响分析** — 仅当用户已形成规模化检索/维护需求时建设。

### Do Not Build（即使 v2 也不应成为默认方向）

- [ ] **无证据的永久权威标签** — 与上下文绑定权威的根本语义冲突。
- [ ] **以 LLM 输出替代确定性编译、资产和测试事实** — 可获得机械证据时不得猜测。
- [ ] **自动批准自身生成的变更** — 生成者不能替代团队权威确认。
- [ ] **默认无限写权限或静默修改** — 必须始终保留范围、预览、审计和回滚。
- [ ] **把任意相似代码直接视为可复用实现** — 语义、生命周期、网络和上下文证据优先于文本相似。
- [ ] **强迫所有 UE 项目采用 Lyra 架构** — Lyra 是首个参考实现，不是产品数据模型的唯一合法形态。

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| 固定 UE/Lyra 基线与冲刺契约 | HIGH | MEDIUM | P1 |
| 人工策展最小权威图谱 | HIGH | HIGH | P1 |
| Authority Context / Evidence / 稳定 ID | HIGH | HIGH | P1 |
| 确定性实体与关系核验 | HIGH | HIGH | P1 |
| 固定需求定位与上下文比较 | HIGH | HIGH | P1 |
| 复用计划与五类决策 | HIGH | MEDIUM | P1 |
| 节点/连接/管线权威边界 | HIGH | HIGH | P1 |
| 受限 Patch 与完整审计 | HIGH | MEDIUM | P1 |
| UHT/UBT/Data Validation/测试编排 | HIGH | HIGH | P1 |
| 增量审查报告与人工确认 | HIGH | HIGH | P1 |
| 晋升与原子写回 | HIGH | HIGH | P1 |
| 对照实验与第二任务复利验证 | HIGH | HIGH | P1 |
| 自动 Suspect/重验证规则 | HIGH | HIGH | P2 |
| 同家族多冲刺变体 | MEDIUM | MEDIUM | P2 |
| Blueprint/资产深度只读检查 | MEDIUM | HIGH | P2 |
| 失败/拒绝知识复用 | MEDIUM | MEDIUM | P2 |
| 多 reviewer 协作 | MEDIUM | HIGH | P2 |
| 半自动语义候选发现 | MEDIUM | VERY HIGH | P3 |
| 多版本/多项目权威传播 | MEDIUM | VERY HIGH | P3 |
| 通用 Blueprint/资产写入 | MEDIUM | VERY HIGH | P3 |
| 企业治理与部署 | MEDIUM | VERY HIGH | P3 |
| 完整图谱编辑器 | LOW（对 MVP） | VERY HIGH | P3 |

**Priority key：** P1 = 验证首个闭环必需；P2 = 核心假设成立后加入；P3 = 产品市场验证后再考虑。所有优先级均为**产品推断**。

## 相邻能力与替代方案分析

这里不把 UE 原生机制或通用代码 Agent 误称为完整直接竞品；它们是用户当前会组合使用的相邻能力/替代方案。表中事实来自官方资料，产品比较为**推断**。

| 能力 | UE 原生工具 / Lyra | Git + 完整 Diff 审查 | 通用 AI 编码 Agent | UE-ITPS 首个 MVP |
|------|--------------------|---------------------|------------------|------------------|
| 输入到能力参考管线 | Lyra 以 Enhanced Input 为基础，并支持 Input Tag 激活 AbilitySet 中匹配能力。[S1][S2] | 不提供 | 可读取/生成代码，但默认没有项目权威语义 | 人工策展该固定管线，并记录其权威上下文 |
| GAS 资源与网络语义 | GAS 原生提供 Ability、Attribute、Effect、成本、复制与预测机制。[S3][S4] | 仅展示文本变化 | 可解释或修改，但结论需验证 | 复用原生机制，不重建 GAS；把语义变化纳入审查边界 |
| 机械事实验证 | Asset Registry、Data Validation、UHT/UBT、Automation 可提供资产、规则、构建和测试证据。[S5][S6][S7][S10] | 可查看代码差异 | 常能调用这些工具，但结果未必形成长期权威资产 | 编排确定性工具并把结果绑定到节点/边/管线证据 |
| Patch 预览/适用性 | UE 不负责通用文本 Patch 工作流 | Git 提供 diff 和 apply/check。[S8][S9] | 通常可生成/应用 Patch | 增加目录、规模、次数预算及证据审计 |
| 审查范围 | 工具分别报告各自结果 | 默认审查完整 Diff | 通常给摘要或文件级说明 | 只突出非权威增量，同时保留完整 Diff |
| 权威与写回 | 无本项目定义的功能级权威模型 | commit 记录变化，不表达上下文权威 | 会话知识通常不构成可审计团队权威 | 人工晋升并写回版本化图谱，供下一任务复用 |
| 成功度量 | 构建/测试是否通过 | 审查完成 | 生成或任务完成 | 审查时间下降且缺陷遗漏不增加 |

## MVP 度量与对照实验

### 必测指标

| Metric | Definition | Guardrail |
|--------|------------|-----------|
| 人工审查时间 | reviewer 从收到材料到提交最终缺陷判断/批准的主动时长 | Treatment 中断、工具等待和人工阅读分别记录，避免把构建时间误算为审查收益 |
| 缺陷遗漏率 | 预先植入或专家金标准缺陷中，reviewer 未发现的比例 | Treatment 不得高于完整 Diff 基线；这是发布护栏 |
| 审查边界召回率 | 专家认定必须审查的项中，被系统纳入边界的比例 | 新连接、上下文/网络/生命周期变化应达到 100% 召回目标 |
| 审查边界精确率 | 系统标为待审的项中，专家认定确需审查的比例 | 用于衡量噪声；不得通过牺牲召回率优化 |
| 非权威增量比例 | 待审节点/连接/管线相对受影响总项的比例 | 必须同时报告数量和类型，避免用拆分粒度操纵比例 |
| 权威复用率 | 在完全匹配上下文中直接复用且证据有效的项 / 候选项 | 只有节点、边或管线各自满足条件才计入 |
| 重复实现数 | 相同语义能力被新建而已有可用实现的次数 | 第二个相似任务应低于基线 |
| 写回复利 | 第二任务较第一任务减少的待审项、审查时间或重复实现 | 没有可观察下降则核心飞轮未验证 |
| 错误权威率 | 被系统折叠为权威、但专家认为需要审查的项 / 被折叠项 | 关键安全指标，目标为 0；出现即阻断发布 |

### 建议实验设计（产品推断）

1. 固定同一 Engine/Lyra 版本、仓库提交、权威库快照、目标平台、网络模式和任务说明。
2. 准备至少两组复杂度相近的体力冲刺变体；由不参与审查的资深 UE/GAS 工程师建立缺陷与应审边界金标准。
3. 采用交叉/配对设计：同一 reviewer 分别使用完整 Diff 与 UE-ITPS 边界报告审查不同但配对的任务，并交换顺序，降低个人能力和学习效应偏差。
4. Treatment 始终允许展开完整 Diff；若系统通过隐藏信息获得更快速度，实验结论无效。
5. 第一轮验证“审查减法”；reviewer 确认并写回后，第二轮用相似任务验证“复利写回”。
6. 小样本优先报告原始数据、效应量、置信区间和个体差异，不用单一平均值宣称普遍有效。
7. 若审查时间下降但遗漏率上升、错误权威率非零，判定 MVP 失败；不得用更快生成速度抵消。

## Sources

所有行业/引擎事实仅引用一手官方资料；访问日期均为 2026-07-12。

- **[S1] Epic Games — [Lyra Sample Game](https://dev.epicgames.com/documentation/unreal-engine/lyra-sample-game-in-unreal-engine?lang=en-US)**：Lyra 是模块化 UE5 学习样例，并随 UE5 更新；包含定制 GAS。
- **[S2] Epic Games — [Abilities in Lyra](https://dev.epicgames.com/documentation/unreal-engine/abilities-in-lyra-in-unreal-engine?lang=en-US)**：AbilitySet、Input Tag 激活、Activation Policy/Group、Ability Cost 及 Lyra 能力生命周期。
- **[S3] Epic Games — [Gameplay Ability System Overview](https://dev.epicgames.com/documentation/unreal-engine/understanding-the-unreal-engine-gameplay-ability-system)**：ASC、Ability、Attribute、Gameplay Effect、资源成本、复制、客户端预测与回滚边界。
- **[S4] Epic Games — [Gameplay Effects](https://dev.epicgames.com/documentation/unreal-engine/gameplay-effects-for-the-gameplay-ability-system-in-unreal-engine?lang=en-US)**：Effect/Effect Spec、Instant/Duration/Infinite 生命周期及属性修改语义。
- **[S5] Epic Games — [Asset Registry](https://dev.epicgames.com/documentation/en-us/unreal-engine/asset-registry-in-unreal-engine)**：对未加载资产的异步信息收集和查询能力。
- **[S6] Epic Games — [Data Validation](https://dev.epicgames.com/documentation/unreal-engine/data-validation-in-unreal-engine)**：自定义资产规则、依赖验证及命令行执行方式。
- **[S7] Epic Games — [Unreal Header Tool](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-header-tool-for-unreal-engine)**：UHT 对 UObject 元数据的解析/代码生成及由 UBT 调用的构建关系。
- **[S8] Git Project — [git diff](https://git-scm.com/docs/git-diff)**：工作树、索引、提交之间的差异查看与 pathspec 范围限制。
- **[S9] Git Project — [git apply](https://git-scm.com/docs/git-apply)**：Patch 应用、`--check` 适用性检查和反向应用能力。
- **[S10] Epic Games — [Run Automation Tests](https://dev.epicgames.com/documentation/unreal-engine/run-automation-tests-in-unreal-engine)**：命令行运行测试及 `-ReportExportPath` 机器可读报告输出。
- **[S11] Epic Games — [Using Gameplay Tags](https://dev.epicgames.com/documentation/unreal-engine/using-gameplay-tags-in-unreal-engine?lang=en-US)**：Gameplay Tag 层级语义、Tag Dictionary 注册与查询方式。
- **[S12] Epic Games — [Enhanced Input](https://dev.epicgames.com/documentation/unreal-engine/enhanced-input-in-unreal-engine)**：Input Action、Mapping Context、Modifier、Trigger 和运行时上下文优先级。

---
*Feature research for: UE-ITPS 首个体力冲刺 MVP*  
*Researched: 2026-07-12*
