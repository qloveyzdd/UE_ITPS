# 项目研究综合摘要

**项目：** UE Incremental Trust Programming System（UE-ITPS）  
**领域：** Unreal Engine 棕地项目的本地、可审计、人工策展权威图谱与增量信任编程  
**研究日期：** 2026-07-12  
**总体置信度：** HIGH（MVP 边界与 UE 工具机制）；MEDIUM（具体 Lyra 资产定位、网络验收矩阵和产品效应需实测）

> **判读规则：** “项目边界”来自当前 [PROJECT.md](../PROJECT.md) 的 Active Requirements、Constraints 与本任务约束；精确版本、阶段划分、存储实现和实验阈值属于**研究建议，尚未获用户批准**。PROJECT.md 的 Key Decisions 当前仍为 Pending，本摘要不会替代产品决策。

## 执行摘要

UE-ITPS 首个 MVP 应验证一个很窄的产品假设：在固定、可复现的 UE/Lyra 环境中，用人工策展的“消耗体力的冲刺能力”权威图谱，把已验证复用与新逻辑、新连接、上下文漂移分开，能否在**缺陷遗漏不增加、错误权威为零**的前提下降低人工审查时间。它不是通用 UE 代码理解器、自动语义发现器或新的 GAS 框架，也不应覆盖 Lyra 全项目。

推荐基准是 **UE 5.7.4 + Fab 中与 UE 5.7 兼容、下载后本地指纹冻结的 Lyra 快照**。推荐最小架构是一个外部本地 core/CLI 加一个薄的 Editor-only C++ Commandlet 插件：插件只读取 UE 内部机械事实并执行极窄的白名单资产操作；外部 core 负责权威模型、上下文比较、边界计算、Git Patch、构建/测试编排、审查和原子写回。Git 中经 JSON Schema 校验、RFC 8785 规范化哈希的 JSON 是唯一权威源；首条小图可直接以内存邻接表查询，SQLite 只在需要时作为可重建派生索引。

最大风险不是“代码生成失败”，而是系统错误隐藏本应审查的连接、生命周期、网络或资产变化。因此必须先实现失败关闭规则，再实现 Patch 和晋升：任何关键上下文未知/不匹配、探针失败、测试集合为空、证据不完整、新组合无独立权威、Patch 越界、构建/测试失败或人工拒绝，都不得应用或晋升。第一轮实验若审查更快但遗漏率上升或出现错误权威，应判定 MVP 失败，而不是用生成速度或复用率抵消。

## 范围与决定状态

### 必须保持的项目边界

- 只覆盖一个固定 UE/Lyra 基线中的 **Enhanced Input → Input Tag → Ability Set/Gameplay Ability → Gameplay Effect → Stamina/Movement** 体力冲刺管线。
- 语义由资深 UE/GAS 工程师人工策展；扫描器只核验点名实体、关系和行为契约，不做开放域语义发现。
- 节点、连接和完整管线分别拥有权威断言；新组合不能继承组件权威。
- 权威必须绑定上下文、证据、代码版本和人工决定；不允许无条件永久正确。
- Agent 写入必须受路径、文件数、行数、轮次、预览、审计和回滚约束。
- Lyra 只是首个参考实现，领域模型不得固化为“所有 UE 项目都采用 Lyra”。

### 研究建议，待用户确认

1. **精确基准：** UE 5.7.4 Launcher 二进制版、Lyra 5.7 兼容快照、Win64 Development Editor、VS 2022 17.14.x、MSVC 14.44.35214、Windows SDK 10.0.22621.0、.NET 8.0.x。
2. **网络验收：** 至少 standalone/单客户端 PIE 与 listen server + 1 client；是否将 dedicated server、受控延迟/丢包列为首版发布门禁，需要在行为契约冻结时明确。
3. **实现运行时：** 外部 core 推荐 Python 3.14.6；MCP 仅在领域 API 稳定后加 `mcp==1.27.2` 的 stdio 薄适配。MCP 不是首个阶段依赖。
4. **索引策略：** 首条管线优先内存邻接表；若确定性查询、审计运行索引或全文检索确有需要，再加入 SQLite 3.53.3 派生索引。
5. **资产写入：** 首版优先文本 Patch 和复用既有资产；只有垂直闭环确实无法完成时，才加入少量白名单 `ApplyAssetOps`，不做通用 Blueprint 图编辑。

## 关键研究结论

详细依据见 [STACK.md](./STACK.md)、[FEATURES.md](./FEATURES.md)、[ARCHITECTURE.md](./ARCHITECTURE.md) 与 [PITFALLS.md](./PITFALLS.md)。

### 推荐技术基准

**核心技术：**

- **Unreal Engine 5.7.4：** 唯一 UE 事实解释器、编译与测试环境；相比刚发布的 5.8，可减少与产品假设无关的升级变量。
- **Lyra 5.7 兼容快照：** 首个参考实现；必须记录 `.uproject`、资产清单、Git commit、Engine BuildId/Changelist，不能虚构 `Lyra 5.7.4` 或写“最新版 Lyra”。
- **Editor-only C++ Commandlet：** 使用 Asset Registry、反射、Blueprint/CDO 和 Automation API 核验人工策展事实；不承载 Agent/LLM 权威判断。
- **外部本地 core/CLI：** 负责纯领域规则、Git/worktree、进程编排、证据与审查；推荐 Python，但领域模型不依赖 MCP。
- **Git + JSON Schema 2020-12 + RFC 8785/SHA-256：** 可 diff、可审计、可迁移的权威记录与证据身份。
- **内存邻接表 / 可选 SQLite：** 图规模只有几十到数百 assertion 时优先 KISS；SQLite 永远是可重建查询层，不是事实源。

### Table Stakes（缺失即无法验证 MVP）

- 精确 baseline lock 与固定冲刺行为契约，覆盖输入开始/保持/释放、体力阈值与持续消耗、速度变化、耗尽、取消、Pawn/Experience 生命周期和网络职责。
- 人工策展最小三层图与稳定 ID；locator、fingerprint、identity 必须分离。
- 版本化 Authority Context、Evidence、Decision 和节点/连接/管线独立 assertion。
- 点名实体与关系的确定性核验，以及 `MATCH / MISMATCH / UNKNOWN` 的失败关闭上下文比较。
- 固定需求入口、功能族定位、五类复用决策与可解释计划。
- 可预览、可回滚、受预算限制的 Patch；文本与二进制资产分轨。
- 分层验证：schema/图完整性 → 静态 locator → UE probe → UBT（含 UHT）→ Automation/网络行为测试。
- 完整证据包、增量审查报告、人工确认/拒绝和 CAS 原子写回。
- 一次完整 Diff 对照实验，以及写回后第二个相似任务的复利实验。

### 关键差异化

- **可证明的审查减法：** 默认突出非权威增量，但完整 Diff 与证据始终可展开。
- **组合不继承权威：** 节点、边、管线分别验证，直接消除“旧组件新组合也可信”的危险捷径。
- **上下文绑定与可解释失效：** Engine、插件、网络、测试或主体指纹变化时，确定性传播为 Suspect。
- **计划先于代码：** 在产生变更成本前，由人校正复用方向和 Review Boundary。
- **审查结果复利：** 人工接受和拒绝都成为下一任务可检索的证据，第二任务必须观察到待审范围或重复实现下降。

### 明确延期

- 任意 UE 项目的自动 Feature/Pipeline 语义发现、向量检索和 embedding 权威判定。
- Lyra 全项目覆盖、跨项目/跨版本权威传播、非 Lyra/非 GAS 实现支持。
- 通用 Blueprint/二进制资产自动编辑、完整图谱可视化编辑器。
- Perforce、私有 Engine、远程服务、多租户、RBAC/SSO 和企业审批。
- Neo4j、RDF/OWL、PostgreSQL、队列、Web 框架和完整度量平台。

## 最小架构

```text
request.json
  → 外部 core/CLI（schema、上下文、权威边界、计划、Git、证据、审查）
      ↔ 版本化 JSON 请求/响应
        → Editor-only UE Commandlet（Asset Registry、反射、CDO、点名关系探针）
      → 隔离 Git worktree → UBT/UHT → Automation/网络合约测试
      → review decision → CAS + 原子 authority 写回

Git JSON = 唯一权威源
内存图 / SQLite = 可重建查询视图
run artifacts = 按 run ID 隔离、内容寻址、只追加
```

**最小组件：**

1. **Domain/Core：** request、三层图、authority/context/evidence/decision schema，确定性匹配、边界闭包和状态机纯函数。
2. **UE Probe：** 一个 Editor 模块和一个窄 Commandlet，仅接受版本化 JSON 与白名单 mode；插件无晋升权。
3. **Git/Process Adapters：** worktree、Patch preimage/预算、UBT、Automation、超时和结构化报告采集。
4. **Review/Writeback：** 最小 CLI/JSON 审查，逐项接受/拒绝，旧摘要 CAS 与原子替换。
5. **Experiment Fixture：** 固定冲刺金标准、植入缺陷、完整 Diff 基线和第二任务复利数据。

### 研究冲突的协调结果

| 议题 | 研究分歧 | 综合建议（未批准） |
|---|---|---|
| 查询存储 | STACK 将 SQLite 列为 MVP 核心；ARCHITECTURE 建议首版内存图、规模化后再加 SQLite | 权威始终是 Git JSON；先用内存邻接表，只有查询/审计需求证明价值后再加 SQLite 派生索引 |
| UE 版本表述 | ARCHITECTURE 以 UE 5.7 为基线；STACK 精确推荐 5.7.4 | 采用 5.7.4 作为研究推荐，但在 baseline 实机预检通过前不视为批准/可用事实 |
| 资产变更 | FEATURES 倾向首版不做通用二进制编辑；STACK/ARCHITECTURE允许极窄白名单 mutation | 默认只做文本 Patch；垂直切片被真实资产写入阻塞时，才加入经过 dry-run 和人工批准的最小 `ApplyAssetOps` |
| 自动失效 | FEATURES 将完整自动 Suspect 规则列为 v1.x；PITFALLS 要求关键失配立即失败关闭 | MVP 必须在每次复用时把 mismatch/unknown 当非权威；持久化的全量反向失效传播可在核心闭环后完善，但不得影响当次安全边界 |

## 必须前置的失败关闭规则

在任何 Patch 应用、资产操作或 authority 晋升之前，至少满足以下规则：

1. baseline、request、manifest、probe 响应或 evidence schema 无效，立即停止。
2. Engine/Lyra/project/plugin/target/network/test 等 required context 任一 `MISMATCH` 或 `UNKNOWN`，相关项进入待审；不得作为权威复用。
3. 点名 probe 崩溃、Asset Registry 未就绪、资产加载失败或无结果，整体验证失败；不得用旧结果替代。
4. 新连接、新 pipeline、生命周期/网络/失败路径变化，无独立 assertion 即为 Candidate；节点权威不得传递。
5. preimage 改变、Patch 冲突、路径越界或文件/行数/轮次超预算，停止并重新规划；不自动 `--3way`，不扩大权限。
6. UBT/UHT 失败、Automation 报告缺失、目标测试发现数为 0、上下文错误、测试失败/超时，均禁止晋升。
7. 每个计划最多两次“修改后重编译”；仍失败则保留全部证据并回到计划，不进行无界修复。
8. 验证通过只产生 promotion proposal；人工拒绝、不完整决定或 authority CAS 冲突不得写回 Authoritative。
9. 失败、拒绝和重试证据只追加，不覆盖；敏感路径/环境值需归一化或脱敏。
10. 实验中错误权威率必须为 0；审查时间下降但缺陷遗漏率高于完整 Diff 基线时，MVP 判定失败并停止权威折叠。

## 对 REQUIREMENTS 的明确影响

当前 Active Requirements 方向正确，但形成正式 `REQUIREMENTS.md` 时应补足以下可验收约束：

- 将“固定 UE/Lyra 版本”细化为 baseline lock 字段和预检；精确 5.7.4 仍标为待确认建议。
- 将“体力冲刺”写成行为契约，而非只写资产/类清单；必须包含开始、保持、释放、耗尽、取消、重生/Experience 切换、服务端接受/拒绝和最终协调。
- 将“稳定标识”拆成 opaque identity、可变 locator 与可重算 fingerprint，并包含重命名/Redirector 验收夹具。
- 将“确定性检查”拆成 schema、静态定位、UE probe、UBT/UHT、Automation/网络测试；`exit_code=0` 或空测试不能算通过。
- 将“权威边界”明确为 entity/relation/pipeline 三层独立 assertion 与保守闭包；UNKNOWN 永不当 PASS。
- 将“可回滚 Patch”定义为隔离 worktree、preimage、预算、文本/资产分轨、失败注入恢复；不能只要求 reverse diff。
- 将“人工写回”限定为验证通过后的逐项决定、CAS、原子替换；代码与知识不得部分晋升。
- 将成功标准设为审查时间效应、遗漏率护栏、边界召回、错误权威率、第二任务复利；代码生成速度仅作诊断指标。

## 对 ROADMAP 的明确影响

### 阶段 0：冻结基线与行为契约

**理由：** 版本和行为未冻结时，后续证据不可复现。  
**交付：** baseline lock、实际 Lyra 资产/类/tag 清单、冲刺行为契约、目标/网络/测试矩阵、金标准 fixture。  
**验收：** 空 Editor 插件 UBT 通过；目标测试入口可发现非零测试；所有精确版本与网络决定已由用户确认。  
**规避：** 版本/网络失配、代码相同误判语义相同、评测污染。

### 阶段 1：权威模型与人工策展图谱

**理由：** 先定义可证明对象，再写探针或 Patch。  
**交付：** request、entity/relation/pipeline、context、evidence、decision、authority schema；稳定 ID；规范哈希；第一份最小 sprint manifest；纯函数边界测试。  
**验收：** 新边不得继承节点权威；悬挂引用失败；重命名保持 ID；同输入产生相同排序和 hash。  
**规避：** 节点权威传递、ID 漂移、失效不传播。

### 阶段 2：确定性 UE 探针与证据链

**理由：** 权威匹配前必须证明策展事实仍存在。  
**交付：** 外部静态 validator、只读 Fingerprint/Inspect/Validate Commandlet、批量 probe、UBT/Automation 编排、不可变 run manifest。  
**验收：** pass/fail/unknown 清晰；空测试、错 Context、探针失败和旧报告均失败关闭；单机与已确认网络场景通过。  
**规避：** Blueprint/软引用遗漏、Editor/runtime 混淆、UHT/UBT/Test 证据误读。

### 阶段 3：复用计划、边界报告与受限 Patch

**理由：** 先让边界可解释，再允许修改。  
**交付：** 固定需求定位、五类决策、Review Boundary、worktree 文本 Patch transaction、preimage/预算/回滚证据；仅在必要时加入极窄资产 mutation。  
**验收：** stale/冲突/越界/超预算均无写入；失败注入后 worktree 与 authority 保持 preimage；完整 Diff 始终可查看。  
**规避：** Patch 可预览但回滚不完整、无限权限、二进制语义不可审。

### 阶段 4：人工审查、晋升、写回与失效

**理由：** 验证不等于团队权威，写回是复利闭环的唯一入口。  
**交付：** 逐项接受/拒绝、promotion proposal、CAS 原子写回、拒绝记录、当次保守失效；按需要完善持久反向依赖传播。  
**验收：** 失败/拒绝不晋升；并发摘要冲突不覆盖；节点/上下文/证据改变使依赖关系和管线不可直接复用。  
**规避：** 自动晋升、部分写回、失效只作用局部。

### 阶段 5：对照实验与复利验证

**理由：** 只有真实审查结果能证明产品价值。  
**交付：** 配对/交叉实验、原始指标、缺陷金标准、第一任务写回和第二任务复利比较。  
**验收：** Treatment 可展开完整 Diff；遗漏率不高于基线、错误权威率为 0；审查时间下降和第二任务待审范围/重复实现下降均有原始证据。  
**规避：** 学习效应、任务差异、计时口径和信息隐藏造成的虚假收益。

### 构建顺序依据

- 依赖链是“基线/契约 → schema/策展 → 事实探针 → 权威边界 → Patch → 人审写回 → 实验”，不得把 Patch、MCP 或 UI 提前。
- 阶段 0—2 已能验证“边界是否真实”；如果失败，应在产生自动写入成本前停止。
- 文本 Patch 先于资产 mutation，领域 API 先于 MCP，内存图先于 SQLite，CLI/JSON 先于图形 UI。
- 每个阶段都应提供失败夹具，而非只验 happy path；失败关闭行为本身是发布能力。

### 研究标志

**规划时仍需深入研究/实机探测：**

- **阶段 0：** Fab 下载物没有不可变公开包坐标，必须在目标机器生成 Lyra 快照与资产指纹；具体 sprint 资产名不可从研究阶段猜测。
- **阶段 2：** UE 5.7 中 Gameplay Effect Components、Lyra Ability Set/InputTag、Blueprint 节点 locator 和目标网络测试 API 需对冻结快照做探测性实现。
- **阶段 3：** 是否必须写 `.uasset` 取决于真实垂直切片；先以手工/既有资产完成性验证，再决定 mutation 范围。
- **阶段 5：** 样本量、reviewer 数量、缺陷金标准与发布阈值属于产品实验设计，需用户确认。

**标准模式，可跳过独立研究阶段：**

- **阶段 1 的 JSON Schema、RFC 8785、纯函数图校验；**规范和模式成熟。
- **阶段 3 的 Git worktree、diff/apply-check、CAS/原子替换；**工具行为成熟，但仍需项目级失败测试。
- **MCP stdio 适配；**只有领域 API 稳定后才实施，属于薄接口而非核心研究问题。

## 主要风险与应对优先级

| 优先级 | 风险 | 首要应对 |
|---|---|---|
| CRITICAL | 审查更快但遗漏/错误权威上升 | 错误权威率 0、遗漏率不升为硬发布门；失败即停止折叠 |
| CRITICAL | 节点权威传播到新连接/管线 | 三层独立 assertion；新组合默认 Candidate |
| HIGH | 版本、网络、Experience/Game Feature 上下文漂移 | 精确 baseline lock；MISMATCH/UNKNOWN 失败关闭 |
| HIGH | Blueprint、Data Asset、软引用或未保存资产遗漏 | 人工资产闭包、Asset Registry 就绪、点名 probe、冷启动/行为测试 |
| HIGH | Patch/资产/authority 无法整体回滚 | dedicated worktree、preimage manifest、资产分轨、CAS 原子写回 |
| HIGH | 证据绿色但实际未运行目标测试 | 非零发现数、实际集合/上下文/报告 hash 门禁，保留所有重试 |
| HIGH | 失效不传播导致旧管线继续折叠 | 反向依赖闭包；当次至少保守标非权威，后续完善持久传播 |
| MEDIUM | 实验被学习效应与任务差异污染 | 冻结材料、配对/交叉顺序、完整 Diff 可见、原始数据与不确定性 |

## 置信度评估

| 领域 | 置信度 | 说明 |
|---|---|---|
| 技术栈 | HIGH / MEDIUM | UE/Git/JSON Schema/MCP 版本与边界有官方依据；Lyra 下载物和 Python 绑定 SQLite 需实机确认 |
| 功能范围 | HIGH | 与 PROJECT.md 的首个 MVP 约束一致；差异化价值和效应大小仍需实验 |
| 架构 | HIGH / MEDIUM | 外部 core + 薄 UE 插件、Git JSON 权威和失败关闭边界明确；具体资产 probe 为 MEDIUM |
| 风险 | HIGH / MEDIUM | UE 工具链/GAS/资产风险有官方依据；产品阈值、恢复成本和样本规模为研究推断 |

**总体置信度：HIGH（方向与边界），MEDIUM（具体实现定位与产品成效）。**

### 必须补齐的缺口

- **用户批准：** PROJECT.md 中全部 Key Decisions 仍为 Pending；ROADMAP 前至少确认精确基准、网络门禁、资产写入范围和实验成功阈值。
- **Lyra 快照事实：** 下载并冻结后确认真实资产、标签、Ability Set、GE/Attribute、Experience/Game Feature 与测试 locator。
- **行为契约：** 明确 sprint 与 Lyra Dash 的复用边界；Dash 的输入/激活机制可参考，但持续体力消耗 sprint 是新 sister implementation，不继承完整管线权威。
- **运行目标：** 明确 packaged Game/Client/Server、dedicated server、网络仿真和 Cook 是否属于首版晋升证据。
- **实验可行性：** 确认资深 reviewer、配对任务和缺陷金标准来源；样本过小时只报告效应量和不确定性。

## 来源

### 研究文档

- [技术栈研究](./STACK.md) — 精确基准、Commandlet/Agent 边界、权威存储、验证和 MCP。
- [功能研究](./FEATURES.md) — table stakes、差异化、反功能、依赖和实验指标。
- [架构研究](./ARCHITECTURE.md) — 最小组件、领域模型、数据流、事务和构建顺序。
- [风险研究](./PITFALLS.md) — 失败模式、预警、恢复和阶段映射。

### 一手资料（HIGH）

- [Epic Lyra Sample Game](https://dev.epicgames.com/documentation/unreal-engine/lyra-sample-game-in-unreal-engine) — Lyra 与 UE 版本、模块化样本边界。
- [Epic Abilities in Lyra](https://dev.epicgames.com/documentation/en-us/unreal-engine/abilities-in-lyra-in-unreal-engine?application_version=5.7) — Ability Set、Input Tag、生命周期。
- [Epic Gameplay Ability System](https://dev.epicgames.com/documentation/en-us/unreal-engine/gameplay-ability-system-for-unreal-engine) — ASC、Ability、Effect、Attribute 与网络职责。
- [Epic Asset Registry](https://dev.epicgames.com/documentation/en-us/unreal-engine/asset-registry-in-unreal-engine) — 未加载资产与机械依赖事实。
- [Epic Unreal Header Tool](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-header-tool-for-unreal-engine) 与 [Unreal Build Tool](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-build-tool-in-unreal-engine) — UBT/UHT 构建边界。
- [Epic Run Automation Tests](https://dev.epicgames.com/documentation/en-us/unreal-engine/run-automation-tests-in-unreal-engine) — 命令行筛选与结构化报告。
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)、[RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html) 与 [Git 文档](https://git-scm.com/docs) — 结构契约、规范哈希和 Patch/审计基础。

---
*研究综合完成：2026-07-12*  
*可进入 REQUIREMENTS/ROADMAP：是，但必须保留上述待确认决定，不得视为已批准。*
