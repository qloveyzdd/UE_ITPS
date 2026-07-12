# Architecture Research

**Domain:** Unreal Engine 棕地项目的可验证复用、权威边界与增量审查系统  
**Researched:** 2026-07-12  
**Confidence:** HIGH（MVP 边界与 UE 工具链机制）；MEDIUM（体力冲刺的具体 Lyra 资产定位需在固定样本中实测）

## 研究结论

首个 MVP 应是一个**本地、单进程、文件驱动的控制面**，外加一个**只做 UE 内部事实探测的薄 Editor 插件**。核心闭环不需要服务端、分布式图数据库、向量库、通用项目扫描器或完整图谱编辑器。

推荐基准为 **UE 5.7 + 与该引擎版本匹配的 Lyra 5.7 样本**；初始化时还必须把 `Build.version`、Engine `BuildId/Changelist`、`.uproject` 的 `EngineAssociation`、Lyra 工作树/内容摘要写入基准锁文件。这里选择 5.7 是 MVP 的架构取舍，不宣称其普遍优于其他版本；Epic 明确说明 Lyra 会随 UE 版本更新，带 C++ 的 Lyra 跨版本通常需要人工迁移，并建议下载与目标引擎匹配的 Lyra 样本。因此，**版本升级等同于权威上下文变化，不能透明沿用旧权威**。

最小数据面使用 Git 版本化、可做 JSON Schema 校验的规范 JSON：一个人工策展 authority manifest 表达 Code / Feature / Lineage 三层最小图、上下文、证据和审查决策；运行产物放入按 run ID 隔离的目录。图只是内存中的有向邻接表，不引入图数据库。

## 事实、推断与取舍

### Epic 官方机制事实

- UBT 管理不同目标/配置下的 UE 构建；模块的 `.Build.cs` 声明依赖。正常构建由 UBT 调用 UHT，再调用 C++ 编译器，因此 MVP 应以一次 UBT 构建作为 UHT + 编译的正式门禁，而不是把“单独跑 UHT”当作常规构建流程。[Unreal Build Tool](https://dev.epicgames.com/documentation/unreal-engine/unreal-build-tool-in-unreal-engine?lang=en-US)、[Unreal Header Tool](https://dev.epicgames.com/documentation/unreal-engine/unreal-header-tool-for-unreal-engine?lang=en-US)
- Asset Registry 是 Editor 子系统，可异步收集未加载资产的信息并维护内存索引；它适合验证资产存在、类型、包依赖和可搜索标签，但不能单独证明“输入标签会以预期网络语义激活某 Ability”这种功能语义。[Asset Registry](https://dev.epicgames.com/documentation/en-us/unreal-engine/asset-registry-in-unreal-engine)
- Enhanced Input 的核心对象包括 Input Action 与 Input Mapping Context；Mapping Context 可在运行时按玩家状态增删。Lyra 的输入层建立在 Enhanced Input 之上，Ability Set 中的能力会在接收到匹配 Input Tag 时检查激活。[Enhanced Input](https://dev.epicgames.com/documentation/unreal-engine/enhanced-input-in-unreal-engine)、[Lyra Input Settings](https://dev.epicgames.com/documentation/unreal-engine/lyra-input-settings-in-unreal-engine?lang=en-US)、[Abilities in Lyra](https://dev.epicgames.com/documentation/unreal-engine/abilities-in-lyra-in-unreal-engine?lang=en-US)
- GAS 由 Ability System Component、Gameplay Ability、Attribute Set/Attribute 和 Gameplay Effect 等组成；ASC 在多人游戏中还承担复制、客户端到服务器通信和授权校验。Gameplay Effect 用于修改 Attribute，预测 Ability 被服务器拒绝时存在回滚语义限制，因此网络执行策略、成本 Effect 和属性修改关系都必须进入权威上下文与测试证据，不能只做静态类存在检查。[Understanding GAS](https://dev.epicgames.com/documentation/unreal-engine/understanding-the-unreal-engine-gameplay-ability-system)、[Gameplay Attributes and Attribute Sets](https://dev.epicgames.com/documentation/en-us/unreal-engine/gameplay-attributes-and-attribute-sets-for-the-gameplay-ability-system-in-unreal-engine)、[Gameplay Effects](https://dev.epicgames.com/documentation/unreal-engine/gameplay-effects-for-the-gameplay-ability-system-in-unreal-engine?lang=en-US)
- Lyra 是模块化学习样本，Gameplay Feature Plugins 会随 Experience 加载；这意味着激活的 Experience / Game Feature 集合是权威上下文的一部分，而不是可忽略的资产组织细节。[Lyra Sample Game](https://dev.epicgames.com/documentation/unreal-engine/lyra-sample-game-in-unreal-engine)、[Game Features and Modular Gameplay](https://dev.epicgames.com/documentation/en-us/unreal-engine/game-features-and-modular-gameplay-in-unreal-engine)
- Automation Test Framework 支持单元、功能、Smoke 和内容压力测试；测试可从命令行运行，并用 `-ReportExportPath` 导出 JSON 与 HTML 结果。网络测试可连接 Editor/Client 实例。因此它适合作为可保存的验证证据，而不是只记录“命令返回 0”。[Automation Test Framework](https://dev.epicgames.com/documentation/unreal-engine/automation-test-framework-in-unreal-engine?lang=en-US)、[Run Automation Tests](https://dev.epicgames.com/documentation/unreal-engine/run-automation-tests-in-unreal-engine)

### 架构推断与取舍

- **推断：外部 core 拥有权威语义。** 权威状态、上下文匹配、边界计算、Patch 策略和图谱写回必须能在不启动 Editor 时被审计和测试；将这些放进 Editor 插件会增加启动成本、耦合 Slate/UObject 生命周期，并让确定性逻辑难以复用。
- **推断：UE 插件只做按需事实探测。** Asset Registry、UObject 反射、CDO/资产属性、Blueprint 生成类和 Package 操作只有在 UE 进程内可靠；插件接收明确 probe 列表并返回 JSON，不尝试自动理解整个项目。
- **取舍：JSON 文件优于图数据库。** MVP 图规模只覆盖一条冲刺管线，规范 JSON + 内存邻接表已经足够，且最易 diff、review、签名、回滚和开源。
- **取舍：文本 Patch 与二进制资产变更分轨。** C++、配置、描述符使用 unified diff；`.uasset` 不伪装成文本 Patch。首版优先复用已策展资产；确需资产写入时，只能由 Editor 插件执行显式 mutation plan，并在隔离 worktree 中保存包级前后摘要。
- **取舍：失败关闭。** 缺失证据、探针无法回答、上下文关键字段不匹配、节点权威但边/管线未权威，全部进入人工审查边界；不使用概率分数把它们自动降级为“可复用”。

## Standard Architecture

### System Overview

```text
┌──────────────────────────── 外部 CLI / core（控制面）────────────────────────────┐
│ Requirement Contract → Manifest Loader → Context Matcher → Authority Boundary │
│                                  │                         │                    │
│                         Entity/Relation Validator       Plan + Patch Guard      │
│                                  │                         │                    │
│                         Build/Test Orchestrator ← Sandbox/Worktree             │
│                                  │                         │                    │
│                         Evidence Recorder → Review Decision → Atomic Writeback │
├──────────────────────────────────┬──────────────────────────────────────────────┤
│ Git-versioned authority.json     │ .itps/runs/<run-id>/ immutable run artifacts│
└──────────────────────────────────┴──────────────────────────────────────────────┘
                                      │ request/response JSON + process exit code
                                      ▼
┌──────────────────────────── UE Editor 进程边界 ──────────────────────────────────┐
│ ITPSProbe Editor Plugin / Commandlet Adapter                                   │
│ Asset Registry queries │ UObject/CDO reflection probes │ optional asset mutation│
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────── 固定 UE/Lyra 基准项目 ───────────────────────────────┐
│ Enhanced Input → Input Tag → Ability Set → Gameplay Ability                    │
│              → Cost/Active Gameplay Effect → Stamina / Movement Attributes      │
│ UBT(UHT + C++ compile) → Automation Tests (unit + PIE/network contract)          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

依赖方向是单向的：

```text
cli → application/core → domain model
cli → adapters/git, process, filesystem, ue-probe-client
ue-probe-plugin → UE Editor APIs
ue-probe-plugin ──JSON──> core

domain model 不依赖 Git、进程、UE SDK、Editor 或具体 Lyra 类型。
外部 core 不链接 UE 模块；UE 插件不读取或修改 authority 状态机。
```

### Component Responsibilities

| Component | Responsibility | MVP implementation |
|---|---|---|
| Requirement Contract | 把自然语言需求收敛成显式 feature family、目标行为、允许目录、预算、网络/平台/测试约束 | `request.json`；允许 Agent 起草，但执行前必须 schema-valid，关键枚举不得由模糊文本替代 |
| Authority Manifest Loader | 校验 schema、引用完整性、ID 唯一性、图无悬挂边、pipeline 步骤合法性 | 规范 JSON + JSON Schema；加载后转为只读内存模型 |
| Context Matcher | 对当前环境和 authority context 做字段级比较，生成 match/mismatch/unknown | 纯函数；关键字段 exact/set containment，规则显式版本化 |
| Entity/Relation Validator | 验证人工声明的节点、边和管线锚点仍然存在 | 外部静态检查 + UE probe；只验证 manifest 点名实体，不做项目级发现 |
| Authority Boundary Engine | 独立计算节点、连接、完整 pipeline 的可复用性和待审查闭包 | 纯函数 + 邻接表；无 ML/LLM 判定 |
| Patch Guard / Executor | 预览、预算检查、preimage 校验、受限应用、审计 | dedicated Git worktree；文本 unified diff；二进制走显式 UE mutation plan |
| Build/Test Orchestrator | 按固定命令运行 UBT、Automation Test，并收集退出码和结构化报告 | 外部进程适配器；命令模板属于 baseline lock，不写死机器路径 |
| Evidence Recorder | 记录输入、环境、探针、diff、构建、测试、审查的摘要和原始产物 | append-only run directory；SHA-256 内容摘要；`run.json` 状态机 |
| Review Decision | 让审查者逐项接受/拒绝非权威增量，记录理由和审查人 | CLI 最小交互或 JSON 决策文件；MVP 不做图形化编辑器 |
| Atomic Graph Writeback | 只把已通过验证且人工接受的 assertion/decision 写回 | authority 文件 CAS（比较旧摘要）+ 临时文件原子替换 |
| ITPSProbe Editor Plugin | 查询 Asset Registry、反射和指定资产属性；必要时执行白名单资产变更 | Editor-only C++ module + commandlet/命令行入口；输出版本化 JSON |
| Contract Tests | 证明冲刺的输入、激活、成本、持续/结束、体力边界与网络语义 | C++ Automation tests；至少一组快速结构测试和一组 PIE/网络行为测试 |

## 必须在 UE 内与必须在外部的边界

| 能力 | UE Editor 插件内 | 外部 CLI/core | 原因 |
|---|---:|---:|---|
| Asset Registry 查询、包依赖、资产类/标签 | 必须 | 仅消费结果 | Registry 是 Editor 子系统，外部猜 `.uasset` 不可靠 |
| UObject/Blueprint generated class、CDO、反射属性路径 | 必须 | 仅声明 probe | 需要加载 UE 类型系统或指定资产 |
| 资产创建/保存/重命名（若 MVP 真的需要） | 必须 | 发 mutation plan、校验输出 | 二进制包必须通过 UE 资产 API，不能文本 patch |
| authority manifest、稳定 ID、状态机 | 禁止拥有 | 必须 | 保持可审计、可 diff、与 Editor 生命周期解耦 |
| Requirement、上下文匹配、边界计算 | 禁止拥有 | 必须 | 纯领域逻辑应快速、确定、可单测 |
| Git worktree、text diff、预算与回滚 | 不应拥有 | 必须 | 属于仓库事务，不属于 UE 内容系统 |
| UBT/Editor 命令编排、超时、重试预算 | 不应拥有 | 必须 | 进程生命周期和证据归档由单一 orchestrator 管理 |
| Automation Test 实现 | 项目测试模块内 | 触发并收集报告 | 测试需要 UE/GAS/PIE；调度和结果治理不需要 |
| 人工审查与图谱写回 | 不应拥有 | 必须 | 防止 Editor 内隐式操作晋升权威 |

## Recommended Project Structure

```text
UE-ITPS/
├── core/                              # 不依赖 UE 的领域与应用逻辑
│   ├── domain/                        # Code/Feature/Lineage、context、authority、review
│   ├── matching/                      # 上下文与权威边界纯函数
│   ├── validation/                    # schema、图完整性、外部静态 validator
│   └── workflow/                      # run 状态机与用例编排
├── cli/                               # prepare/plan/apply/verify/review/promote 命令
├── adapters/
│   ├── git/                           # diff、worktree、preimage、commit identity
│   ├── process/                       # UBT/Editor/Automation 启动与日志
│   └── ue_probe/                      # 与 Editor 插件交换版本化 JSON
├── schemas/                           # request、manifest、probe、evidence、decision schema
├── ue-plugin/ITPSProbe/               # Editor-only 插件；不包含 authority 决策
│   ├── ITPSProbe.uplugin
│   └── Source/ITPSProbeEditor/
├── fixtures/lyra-5.7-stamina-sprint/  # 最小人工策展样例和期望 probe，不复制 Lyra 内容
└── tests/                             # core 单测、golden manifest、CLI 集成测试

target-ue-project/
├── .itps/
│   ├── baseline.lock.json             # Engine/Lyra/project/test/probe 精确身份
│   ├── authority.json                 # 人工策展、Git 版本化的最小权威图
│   └── runs/<run-id>/                 # request、plan、patch、probe、logs、reports、decision
└── Plugins/ITPSTests/                 # MVP 合约测试；产品化后可与项目测试约定合并
```

`.itps/runs` 是否提交由团队决定；MVP 至少提交 `authority.json`、baseline lock、被晋升 evidence 的小型索引与 decision，原始大日志可本地保留。权威记录只能引用可解析的 evidence URI 和 SHA-256，不能只写“测试通过”。

## 最小领域模型

### 1. Code Graph

Code Graph 只记录这条垂直管线需要的实体和机械关系。

**Entity 最小字段：**

```json
{
  "id": "ent_01...",
  "kind": "cpp_class | cpp_function | property | module | plugin | asset | gameplay_tag | test",
  "locator": { "scheme": "ue_object | ue_asset | source_symbol | gameplay_tag", "value": "..." },
  "owner": { "plugin": "ShooterCore", "module": "LyraGame" },
  "fingerprint": "sha256:...",
  "probe": { "type": "...", "args": {} }
}
```

**Relation 最小字段：**

```json
{
  "id": "rel_01...",
  "type": "maps_input | routes_tag | grants_ability | uses_cost_effect | modifies_attribute | controls_movement | covered_by",
  "from": "ent_...",
  "to": "ent_...",
  "fingerprint": "sha256:...",
  "probe": { "type": "reflection_predicate | asset_dependency | runtime_test", "args": {} }
}
```

MVP 只允许预先登记的 relation type。`asset_dependency` 证明包级依赖，不等同于 `routes_tag` 等语义边；后者必须由具体属性 predicate 或行为测试证明。

### 2. Feature Graph

| Object | 最小字段 | 作用 |
|---|---|---|
| FeatureFamily | `id`, `name`, `intent_schema` | 固定为“可消耗资源的移动能力”族；不做开放式语义聚类 |
| Feature | `id`, `family_id`, `behavior_contract`, `implementations[]` | 本次为“消耗体力的冲刺能力” |
| Pipeline | `id`, `feature_id`, `ordered_steps[]`, `edge_ids[]`, `preconditions`, `failure_paths`, `network_boundary` | 对整条组合单独授予/撤销权威 |
| Implementation | `id`, `feature_id`, `entity_ids[]`, `pipeline_ids[]`, `variant_dimensions` | 连接功能语义和 Code Graph |

推荐的最小 pipeline 步骤是：

```text
Enhanced Input Action
→ active Mapping Context
→ Lyra Input Tag
→ Ability Set grant/input binding
→ Gameplay Ability activation policy
→ stamina precondition/cost Gameplay Effect
→ sprint movement modifier while active
→ input release / stamina exhausted / server rejection end path
→ movement and stamina rollback/reconciliation
```

具体资产名由固定 Lyra 基准实测后写入 manifest；研究阶段不猜测不存在的 `GA_Sprint` 或 `GE_StaminaCost`。

### 3. Lineage Graph

Lineage 不复制 Code Graph，只表达实现与决策的演进：

```json
{
  "implementations": [{
    "id": "impl_01...",
    "derived_from": ["impl_..."],
    "sister_of": ["impl_..."],
    "replaces": [],
    "decision_ids": ["dec_..."]
  }],
  "decisions": [{
    "id": "dec_01...",
    "kind": "reuse | configure | modify | new_relation | new_logic | promote | reject | invalidate",
    "subject_ids": ["..."],
    "run_id": "run_...",
    "reviewer": "team-identity",
    "evidence_ids": ["ev_..."],
    "reason": "..."
  }]
}
```

`sister_of` 用于保留网络模型、生命周期或资源语义不同的平行实现；不能用一组布尔参数把它们压成万能实现。

### 4. Authority Assertion

节点、边、管线分别有 assertion，不能继承：

```json
{
  "id": "auth_01...",
  "subject_kind": "entity | relation | pipeline",
  "subject_id": "...",
  "status": "candidate | reviewed | verified | adopted | authoritative | suspect | deprecated",
  "context_id": "ctx_...",
  "subject_fingerprint": "sha256:...",
  "evidence_ids": ["ev_..."],
  "decision_id": "dec_...",
  "verified_at_commit": "<git object id>"
}
```

只有 `authoritative` 且上下文匹配、fingerprint 未漂移、证据策略满足的 assertion 才进入可复用集合。`verified_at_commit` 用于追溯，不要求整个仓库永远停在该 commit；是否仍可复用由被引用主体 fingerprint、关系 probe 和上下文共同决定。

## 稳定 ID、定位与证据

### ID 规则

1. `ent_ / rel_ / pipe_ / impl_ / auth_ / ctx_ / dec_ / run_` 使用创建时分配的 UUIDv7 或 ULID；创建后永不改变、永不复用。
2. UE 对象路径、资产包路径、C++ qualified name 都是**可变 locator**，不是 identity。资产移动、类改名时更新 locator，并保留 redirect/lineage decision；不能因为路径变了就悄悄创建“同一”权威对象。
3. gameplay tag 字符串同样放在 locator；重命名必须产生显式 relation/decision 变更。
4. fingerprint 是可重算的内容/结构摘要，不是 identity。规范 JSON 使用排序键、UTF-8、无无意义空白后计算 SHA-256。
5. evidence 可用 `ev_<sha256-prefix>` 做内容寻址；原始文件还要记录完整 SHA-256、大小、生成工具版本和相对 URI。

### Evidence 最小字段

```json
{
  "id": "ev_abcd...",
  "kind": "probe | diff | uht_ubt | automation | review | environment",
  "artifact_uri": "runs/run_.../reports/...",
  "sha256": "...",
  "producer": { "name": "itps", "version": "..." },
  "command": ["..."],
  "exit_code": 0,
  "started_at": "...",
  "finished_at": "..."
}
```

命令参数中机器绝对路径在入库前归一化或脱敏；原始本地日志可保留绝对路径，但不得用它参与可跨机器比较的 fingerprint。

## Authority Context 与匹配规则

### Context 最小字段

| 维度 | MVP 规则 |
|---|---|
| Engine | `major.minor.patch`、Changelist/BuildId、source/launcher 标识；必须 exact |
| Lyra | 匹配 5.7 样本标识 + 样本 Git/tree/content digest；必须 exact |
| Project | project ID、架构 profile、`.uproject` digest；project ID 必须 exact |
| Plugins | 启用插件、版本/descriptor digest、Game Feature 集合；被 pipeline 引用者必须 exact |
| Modules | 相关 `.Build.cs`/public API digest；相关模块必须 exact |
| Target | target、platform、configuration；必须被 authority context 允许 |
| Network | standalone/listen/dedicated、client count、prediction policy；必须 exact 或 assertion 显式声明集合包含 |
| Tests | suite IDs、test implementation fingerprints、probe schema version；必须满足 assertion 的最低集合 |
| Verification | verified commit、reviewer、evidence policy version | 用于追溯和策略匹配 |

不要使用“相似度 0.92”决定权威。匹配结果只有：

- `MATCH`：所有 required predicate 为真；
- `MISMATCH`：至少一个 required predicate 明确为假，相关 assertion 标记 `suspect` 候选；
- `UNKNOWN`：信息缺失或探针失败，按非权威处理，但不自动改写历史状态。

### 权威边界计算

```text
1. 校验 request、baseline lock、authority manifest 的 schema 和摘要。
2. request 必须给出已策展 FeatureFamily/Feature ID；自然语言只作审计说明。
3. 定点验证候选 implementation 引用的 entity、relation 和 pipeline。
4. 对每个 subject 独立求：status ∧ context ∧ fingerprint ∧ evidence policy。
5. pipeline 仅在自身 assertion 可用，且它引用的所有必需节点/边可用时才算权威复用。
6. 根据计划操作分类：reuse / configure / modify / new_relation / new_logic。
7. Review Boundary = 所有非权威操作
   ∪ 漂移或验证失败的 subject
   ∪ 由这些 subject 沿“当前策展 pipeline 的影响边”到达的必要上下游契约。
8. 输出逐项理由；不遍历未策展的整个项目，不推断图外语义。
```

边界闭包必须有上限：只沿当前 feature 的 pipeline edge types、最多固定深度，并把截断记录为 `UNKNOWN`。否则一个共享 Gameplay Tag 或模块依赖可能把审查范围扩散到整个项目，失去 MVP 价值。

## Entity / Relation Validator

### 两段式验证

**外部静态验证器：**

- 锁定 `.uproject`、`.uplugin`、相关 `.Build.cs`、模块/插件存在性和摘要；
- 验证 source locator 指向的文件、声明锚点和 preimage fingerprint；
- 验证 Git commit、worktree clean state、allowed roots、文件/行数预算；
- 不自行解析 Blueprint，不以正则结果替代 UHT/UBT。

**UE Probe 验证器：**

- `asset_exists_and_is_class(object_path, class_path)`；
- `asset_registry_dependency(from_package, to_package, category, property)`；
- `class_is_child_of(class_path, base_class_path)`；
- `property_equals(object_or_cdo, property_path, canonical_value)`；
- `array_contains_struct(object, property_path, key_fields)`；
- `gameplay_tag_exists(tag)`；
- `blueprint_generated_class_resolves(asset_path)`；
- 可选 `asset_mutation`，但只接受白名单对象、属性和预期 preimage。

Probe 输入必须包含 manifest digest、probe schema version 和精确 object path；输出对每个 probe 返回 `pass/fail/unknown`、观察值摘要、加载警告与引擎身份。插件崩溃、异步 Asset Registry 未就绪、资产加载失败都返回整体失败，外部 core 不把“没有结果”解释为“没有变化”。

### 关系证据强度

| 关系 | 最低验证 |
|---|---|
| 资产存在/类型 | Asset Registry 或反射 probe |
| 包 A 依赖包 B | Asset Registry dependency probe |
| Input Action 映射到 Tag | 对指定 Input Config/Mapping Context 的属性 probe |
| Tag 激活 Ability | 指定 Ability Set 条目的属性 probe + 至少一个行为测试 |
| Ability 使用成本 GE | Ability CDO/配置属性 probe + 构建 |
| GE 修改 Stamina | GE modifier/attribute 属性 probe + 行为测试 |
| Sprint 生命周期/网络回滚 | PIE/网络 Automation contract test；静态图不能替代 |

## End-to-End Data Flow

### 1. Prepare / Plan（只读）

```text
requirement.json
→ baseline lock + manifest schema validation
→ external facts + UE point probes
→ context matching
→ reuse candidates and drift report
→ authority boundary
→ plan.json + review-boundary.json + proposed.patch/mutation-plan.json
```

`plan.json` 必须逐条说明为什么是原样复用、配置适配、修改、新连接或新逻辑，并列出所依赖 assertion 和 evidence。此阶段不写目标项目。

### 2. Apply（隔离写）

```text
baseline commit
→ create dedicated worktree
→ verify preimage hashes and budgets
→ git apply --check
→ apply text patch
→ optional Editor mutation plan
→ capture exact git diff + binary package hashes
```

允许目录、最大文件数、最大新增/删除行数、是否允许新文件、是否允许 `.uasset`、最大重试次数都来自 request policy。任何超限先停，不自动扩大权限。

### 3. Verify（门禁）

```text
graph/entity probes
→ UBT target build（其内触发 UHT）
→ fast Automation structural/contract tests
→ PIE/network sprint contract tests
→ final probes + final diff
→ evidence index
```

建议门禁顺序从便宜到昂贵：schema/图完整性 → 静态 locator → UE probe → UBT → fast tests → PIE/network tests。正式证据中单独标出 UHT 阶段日志，但执行仍由 UBT 统一触发。

冲刺最小行为合约至少覆盖：

1. 未激活 Input Tag 时不启动；按下后匹配 Ability 被请求激活；
2. 体力不足拒绝或结束，且不保留移动增益；
3. 激活期间体力按约定扣减，释放输入后停止扣减并恢复移动参数；
4. 客户端预测被服务器拒绝时，最终 Stamina、Tag、Ability 状态和移动状态一致；
5. Ability 被取消、Pawn/Experience 切换或 Game Feature 卸载时清理持续 Effect；
6. 重复激活/结束不会叠加泄漏 Effect 或永久改变移动速度。

### 4. Review / Promote（唯一写回入口）

```text
review boundary + diff + evidence
→ reviewer accepts/rejects each non-authoritative item
→ accepted items become decision records
→ only if all required gates pass: create/update assertions
→ compare-and-swap authority file digest
→ atomic writeback
```

验证通过不等于自动权威。首次通过可进入 `verified`；只有满足团队 policy 且人工显式确认时才进入 `authoritative`。拒绝记录也写入 Lineage/Decision，避免下一次重复提出同一错误方案。

## Patch 执行、失败与回滚

### 事务边界

每个 run 以 dedicated Git worktree 为写入边界，绑定 baseline commit 和 authority manifest digest。主工作树有用户改动时不触碰它；run worktree 可安全丢弃。禁止 `git reset --hard` 作为产品回滚机制。

### 失败矩阵

| 失败点 | 系统行为 | 回滚/恢复 |
|---|---|---|
| schema/manifest 悬挂引用 | `PLAN_FAILED`，不启动 UE | 无写入 |
| Engine/Lyra/context 不匹配 | 候选变 `UNKNOWN/MISMATCH`，扩大到明确审查项 | 不自动改历史 authority；人工决定是否另建 context |
| Probe 崩溃/未知 | `VERIFY_FAILED`，失败关闭 | 保留日志，按预算最多重试；不得以旧 probe 结果代替 |
| preimage 改变/patch 冲突 | `APPLY_FAILED` | 不做三方“聪明合并”；重新计划新 baseline |
| Patch 超预算/越界 | `POLICY_BLOCKED` | 不应用；需要新的显式 request policy |
| Editor mutation 部分保存 | `APPLY_FAILED` | 丢弃 run worktree；证据记录被写包列表与摘要 |
| UHT/UBT 失败 | `VERIFY_FAILED` | 不写回图谱；保留完整日志；有限重试只允许计划内修复 |
| Automation Test 失败/超时 | `VERIFY_FAILED` | 终止残留 UE 进程，保留 report；不晋升 |
| 审查拒绝 | `REJECTED` | 丢弃 patch worktree；写拒绝 decision，但不创建 authority |
| authority 写回摘要冲突 | `WRITEBACK_CONFLICT` | 不覆盖并发修改；重新加载、重新计算边界后再审查 |
| 写回中断 | 原文件保持 | 临时文件 fsync 后原子 rename；启动时清理孤立 temp |

通过验证后也不应自动合并到用户分支；MVP 交付物是可审查 worktree/patch、证据和 promotion proposal。最终合并仍是显式人工操作。

## Architectural Patterns

### Pattern 1: Functional Core, Imperative Shell

领域模型、上下文比较、边界闭包和晋升规则是无 I/O 纯函数；Git、UE、进程和文件系统通过 adapter 注入。优点是同一输入可重放并得到相同边界，符合成功指标。代价是需要先定义清晰 JSON contract，但这正是权威可审计的必要成本。

### Pattern 2: Curated Assertions, Deterministic Probes

人工声明“这条边意味着什么”，工具只证明声明的机械前提和行为合约是否仍成立。它避免把 Asset Registry 包依赖误当成功能语义，也避免 MVP 演变成通用 UE 理解器。代价是初次策展需要资深 UE 工程师投入。

### Pattern 3: Evidence-Carrying Authority

authority assertion 不是布尔标签，而是 `subject + context + fingerprint + evidence + reviewer decision`。任何关键上下文漂移使其不可直接复用。代价是数据比简单标签多，但能解释、失效、重验和审计。

### Pattern 4: Transactional Patch Run

计划、应用、验证、审查和写回由 run 状态机串联；worktree 提供代码事务，authority CAS 提供知识事务。代码验证失败时知识不写回，知识写回冲突时不覆盖其他人的判断。

## Internal Boundaries

| Boundary | Contract | Rule |
|---|---|---|
| CLI → Core | typed command/request objects | CLI 不直接改 manifest |
| Core → Git adapter | repository/worktree/diff interface | domain 不见 shell 命令字符串 |
| Core → UE probe client | versioned request/response JSON | 插件升级必须改变 probe schema/tool fingerprint |
| Core → Build/Test adapter | argv、cwd、timeout、env allowlist | 不通过 shell 拼接未转义参数 |
| Probe plugin → UE | Asset Registry/reflection/editor asset APIs | 只访问 request 中白名单对象 |
| Validator → Boundary engine | pass/fail/unknown facts | unknown 永不提升为 pass |
| Review → Writeback | signed/identified decision + old manifest digest | 只能 CAS + atomic replace |

## 构建顺序

1. **固定基准与验收 fixture。** 安装 UE 5.7 和匹配 Lyra 5.7；记录精确 Build/Lyra 摘要；由 UE 专家在固定样本中确认实际冲刺/体力相关资产、类、标签与网络行为。没有这一步，不应猜 manifest。
2. **先建 schema 与纯 core。** 实现 request、三层最小图、authority/context/evidence/decision schema，图完整性校验、规范 JSON、稳定 ID 和纯函数匹配测试。
3. **人工策展第一份 manifest。** 只覆盖 Enhanced Input → Ability → Effect → Stamina/Movement 的必需节点、边、pipeline 和测试，不扫描全项目。
4. **实现外部静态 validator。** Engine/project/plugin/module/Git/preimage/预算检查；用 golden fixture 测可重放结果。
5. **实现最薄 ITPSProbe。** 先做资产存在、类、属性 predicate、依赖和 tag；以命令行 JSON 往返验证。不要先做 UI 或通用 Blueprint 图解析。
6. **实现边界与解释报告。** 用“节点权威但新边”“边权威但新 pipeline”“上下文漂移”三个反例证明不会误复用。
7. **实现 worktree Patch transaction。** 先只支持文本；若真实垂直切片无法完成，再增加最小白名单 asset mutation，而不是先做通用资产编辑器。
8. **接入 UBT 与 Automation。** 固化目标、平台、配置、测试筛选、超时和报告路径；补齐 sprint 的单机与网络行为合约。
9. **实现人工 decision 与原子写回。** 先支持 CLI/JSON，证明拒绝、冲突和失败不晋升。
10. **跑对照实验。** 同一任务比较完整 diff 审查与 authority boundary 审查的时间、遗漏、非权威比例和第二次复用收益；结果决定是否值得扩展。

每一步都可独立验收；第 1—6 步已经能验证“边界是否真实”，不必等待自动 Patch 才获得产品信号。

## Scaling Considerations

MVP 的尺度不是用户并发，而是**一个项目、一条 pipeline、几十到数百个 assertion、串行 run**。单进程和 JSON 足够。

| 触发条件 | 才考虑的调整 |
|---|---|
| manifest diff/加载明显变慢，或达到数万 assertion | 在保持 JSON 为交换/审查格式的前提下增加本地 SQLite 派生索引；索引可重建、不是事实源 |
| 多个 run 争用 UE/编译资源 | 本地作业队列和资源锁；仍不需要远程服务 |
| 多项目共享权威成为已验证需求 | 先定义项目/版本隔离和导入签名，再评估服务化；禁止直接把单项目 assertion 当跨项目权威 |

第一个瓶颈更可能是 Editor 启动与 UBT/PIE 时长，而不是图查询。先缓存**由 baseline digest + probe request digest 定址的只读探针结果**；任何相关文件、资产、插件或引擎摘要变化即失效。不要先优化图存储。

## Anti-Patterns

### 把 Asset Registry 当语义图谱生成器

包依赖和资产标签只能证明机械关系，不能证明输入、Ability、Effect 和网络生命周期的业务含义。应由人工策展语义边，再用反射 predicate 和行为测试验证。

### 节点权威传递为组合权威

两个 authoritative 节点或边的新组合仍可能改变顺序、生命周期、预测和失败清理。必须给 relation 和 pipeline 独立 assertion。

### 用路径或符号名充当稳定 ID

资产移动、类重命名会破坏身份或导致旧证据误挂。应使用不可变 opaque ID，把路径作为可变 locator，并用 lineage/decision 表达迁移。

### 让插件拥有全部业务逻辑

这会让每次计划都依赖 Editor 启动，也让 authority 规则难以纯测和重放。插件只提供 UE 事实与受限资产操作。

### 直接修改主工作树再尝试逆向回滚

并发用户改动和二进制资产会让 inverse patch 不可靠。使用 dedicated worktree，把丢弃 worktree 作为失败回滚。

### 把编译成功当作行为正确

UBT/UHT 只能证明反射代码生成和编译门禁；输入路由、成本扣减、取消清理和网络收敛必须由 Automation 行为合约覆盖。

### 为首版拆成长期开源产品清单中的全部服务

`ue-feature-graph`、`ue-authority-registry`、`ue-impact-analyzer` 等只是未来逻辑边界，不应变成首版独立进程/仓库。MVP 保持一个 core 包、一个 CLI、一个 Editor probe 插件。

## 明确不构建

- 不构建分布式/远程图数据库、GraphQL 服务、权限中心或企业审批；
- 不做任意 UE 项目的全量语义扫描、通用 Blueprint 图反编译或自动 Feature 发现；
- 不做向量检索/embedding 权威判定；
- 不做完整 Slate 图谱编辑器；
- 不让 LLM 决定 Engine、模块、资产、关系、构建或测试的机械事实；
- 不自动跨 UE/Lyra 版本迁移 authority；
- 不自动提交、推送或合并经验证 Patch；
- 不在 MVP 中支持 Perforce、私有 Engine 分支、多租户或跨项目权威传播。

## Sources

全部 UE/Lyra/GAS/Asset Registry/测试机制事实仅使用 Epic 官方一手资料：

- [Unreal Header Tool for Unreal Engine](https://dev.epicgames.com/documentation/unreal-engine/unreal-header-tool-for-unreal-engine?lang=en-US)
- [Unreal Build Tool in Unreal Engine](https://dev.epicgames.com/documentation/unreal-engine/unreal-build-tool-in-unreal-engine?lang=en-US)
- [Asset Registry in Unreal Engine](https://dev.epicgames.com/documentation/en-us/unreal-engine/asset-registry-in-unreal-engine)
- [Enhanced Input in Unreal Engine](https://dev.epicgames.com/documentation/unreal-engine/enhanced-input-in-unreal-engine)
- [Lyra Input Settings](https://dev.epicgames.com/documentation/unreal-engine/lyra-input-settings-in-unreal-engine?lang=en-US)
- [Abilities in Lyra](https://dev.epicgames.com/documentation/unreal-engine/abilities-in-lyra-in-unreal-engine?lang=en-US)
- [Gameplay Ability System](https://dev.epicgames.com/documentation/en-us/unreal-engine/gameplay-ability-system-for-unreal-engine?lang=en-US)
- [Understanding the Unreal Engine Gameplay Ability System](https://dev.epicgames.com/documentation/unreal-engine/understanding-the-unreal-engine-gameplay-ability-system)
- [Gameplay Attributes and Attribute Sets](https://dev.epicgames.com/documentation/en-us/unreal-engine/gameplay-attributes-and-attribute-sets-for-the-gameplay-ability-system-in-unreal-engine)
- [Gameplay Effects](https://dev.epicgames.com/documentation/unreal-engine/gameplay-effects-for-the-gameplay-ability-system-in-unreal-engine?lang=en-US)
- [Lyra Sample Game](https://dev.epicgames.com/documentation/unreal-engine/lyra-sample-game-in-unreal-engine)
- [Upgrading the Lyra Starter Game](https://dev.epicgames.com/documentation/unreal-engine/upgrading-the-lyra-starter-game-to-the-latest-engine-release-in-unreal-engine?lang=en-US)
- [Game Features and Modular Gameplay](https://dev.epicgames.com/documentation/en-us/unreal-engine/game-features-and-modular-gameplay-in-unreal-engine)
- [Automation Test Framework](https://dev.epicgames.com/documentation/unreal-engine/automation-test-framework-in-unreal-engine?lang=en-US)
- [Run Automation Tests](https://dev.epicgames.com/documentation/unreal-engine/run-automation-tests-in-unreal-engine)

---
*Architecture research for: UE-ITPS first MVP*  
*Researched: 2026-07-12*
