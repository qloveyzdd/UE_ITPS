# 技术栈研究

**领域：** Unreal Engine 棕地项目的本地、可审计权威图谱与 Agent 治理层  
**研究日期：** 2026-07-12  
**总体置信度：** HIGH（版本可用性与接口边界为 HIGH；Lyra 资产级字段在实现前仍需对冻结快照做一次探测性验证，相关项为 MEDIUM）

## 结论摘要

首个 MVP 应固定为 **Unreal Engine 5.7.4 + 与 5.7 对应的 Lyra Starter Game 快照**，而不是 2026-06-23 才发布的 UE 5.8。UE 5.7.4 已经过四轮热修复，Epic 的 5.7 文档完整覆盖 Lyra、Enhanced Input、GAS、Asset Registry、UHT/UBT 与 Automation Test；它能减少“引擎刚升级”这一无关变量。Lyra 的 Fab 资产没有足以充当供应链锁文件的公开语义版本，因此除“5.7 兼容”外，还必须把实际下载物的项目清单、引擎 build/changelist、关键资产导出清单和 Git commit 一起冻结。

技术上采用两层边界：

1. **UE 内部的 C++ Editor Commandlet** 只做 UE 才能可靠完成的机械事实读取与受限资产写入：反射、Asset Registry、Blueprint 图、Gameplay Ability/Effect CDO、Gameplay Tag、资产保存和 UE Automation Test。
2. **UE 外部的 Python 本地 Agent** 负责权威图谱、上下文匹配、查询、审计、Patch、Git、构建/测试编排和 MCP 接口。外部进程不直接解析 `.uasset`，UE 插件也不直接承载 Agent/LLM 逻辑。

权威源使用 **Git 版本化、JSON Schema 约束、RFC 8785 规范化哈希的 JSON 记录**；SQLite 只是可重建的本地查询索引。MVP 图很小，邻接表加递归 CTE 已足够，Neo4j、RDF/OWL、向量库和通用语义发现都不应进入首版。

## 推荐技术栈

### 核心技术

| 技术 | 固定版本/范围 | 用途 | 推荐理由 | 置信度 |
|---|---|---|---|---|
| Unreal Engine | **5.7.4**，记录 `Build.version` 的 `Changelist`、`CompatibleChangelist` 和安装来源 | 唯一 UE 事实解释器、编译与测试环境 | 5.7.4 是 5.7 的第四个热修复；相较刚发布的 5.8，更适合作为低变量实验基线 | HIGH |
| Lyra Starter Game | **Fab 中与 UE 5.7 兼容的快照**；下载后以仓库 commit + 资产清单 SHA-256 二次固定 | 首个参考实现与目标管线语料 | Epic 明确说明 Lyra 随 UE 大版本更新，且样例只在安装兼容 Engine 时出现；因此不能只写“最新版 Lyra” | HIGH（版本策略）；MEDIUM（具体资产指纹需下载后生成） |
| UE-ITPS 项目插件 | 插件版本 `0.1.0`，`EngineVersion`/兼容声明限制到 5.7 | C++ Editor Commandlet、UE 元数据提取、窄写入器、Automation Tests | 使用 UE 自身对象模型读取资产，避免逆向 `.uasset`；Editor 模块不会进入 Shipping | HIGH |
| Python | **3.14.6**，项目要求 `>=3.14,<3.15` 并锁定解释器补丁版本 | 本地 Agent、图谱编译、Git/UBT/Editor 子进程编排、MCP server | Windows 支持成熟；标准库足以覆盖子进程、哈希、JSON 与基础 SQLite，减少运行时复杂度 | HIGH |
| SQLite | **3.53.3**；数据库文件声明 `user_version`，启动时核验实际库版本 | 可重建图查询索引、审计/验证运行索引、全文检索 | 单文件、无守护进程；邻接表 + recursive CTE 可遍历小图；JSON 与 FTS5 足够 MVP 查询 | HIGH |
| Git | **2.55.0** 基准；Agent 最低支持范围 `>=2.45,<3` | 基线身份、文本/二进制 Patch、状态检查、回滚与审计 | `--porcelain=v2 -z` 适合机器解析；`git diff --binary --full-index` 与 `git apply --check` 提供确定性 Patch 边界 | HIGH |
| JSON Schema | **Draft 2020-12** | 权威记录、Commandlet 导出、计划、审计清单的契约 | 当前最新发布的 meta-schema；适合严格关闭未声明字段并给每类记录独立版本 | HIGH |
| MCP | Python SDK **1.27.2** 且依赖约束 `mcp>=1.27.2,<2`；使用 stdio，协议版本通过初始化协商 | Codex/Claude/Cursor 等本地 Agent 的最小接口 | v1 是当前稳定线，v2 尚未稳定；stdio 不开放端口，最适合单机 MVP | HIGH |

### Windows/UE 构建工具链

| 工具 | 固定版本 | 用途 | 备注 |
|---|---|---|---|
| Visual Studio 2022 | **17.14.x** | UE 5.7 C++ 工具链与调试 | Epic 对 UE 5.7 的推荐版本；VS 2019 不支持 |
| MSVC | **14.44.35214** | C++ 编译器 | 使用 Epic 对 5.7 的推荐/默认工具集，不跟随机器上的“最新 MSVC”漂移 |
| Windows SDK | **10.0.22621.0** | Win64 SDK | 固定推荐版本，避免开发机差异 |
| .NET SDK/Runtime | **8.0.x** | UBT/UHT/AutomationTool 的托管运行时 | 与 UE 5.7 文档推荐一致；由 Engine 安装/前置条件统一提供 |
| UBT + UHT | **随 UE 5.7.4 一起固定** | 反射代码生成和项目编译 | 正常验证只调用 UBT；官方流程本身会先调用 UHT，再调用 C++ 编译器 |
| Unreal Automation Test | **随 UE 5.7.4 一起固定** | 约定测试、编辑器/网络/功能验证 | 使用命名空间过滤，只跑 `UEITPS.Sprint.*`，结果输出到独立证据目录 |

### Python 支撑库

| 库 | 固定版本 | 用途 | 使用边界 | 置信度 |
|---|---|---|---|---|
| `mcp` | **1.27.2**，`<2` | MCP stdio server | 仅暴露薄工具层；不得把数据库连接或任意 shell 暴露给调用方 | HIGH |
| `pydantic` | **2.13.4** | MCP 输入/输出模型与内部命令 DTO | 用于 Python 类型边界，不替代权威 JSON Schema | HIGH |
| `jsonschema` | **4.26.0** | Draft 2020-12 验证 | 每次读取、写回和建立索引前都校验；显式启用所需 `format` 检查 | HIGH |
| `rfc8785` | **0.1.4** | JCS 规范化后计算 SHA-256 | 只处理 JSON/I-JSON 可表达值；64 位标识、时间和精度敏感数值用字符串 | MEDIUM（实现小且稳定，但发布频率低，必须跑 RFC 向量） |
| Python `sqlite3` | 随 **3.14.6** | SQLite 连接 | 启动时断言 `sqlite3.sqlite_version` 满足功能下限；若系统绑定库不一致，改用官方 3.53.3 amalgamation 构建的薄适配，不静默降级 | MEDIUM |

不需要在 MVP 引入 ORM、Web 框架、队列、容器编排或 LLM 框架。SQL 数量很小，显式参数化 SQL 和迁移脚本更清楚，也更易审计。

## UE/Lyra 基准固定策略

### 推荐基准

固定以下组合：

- UE Launcher 二进制版 **5.7.4**（若必须使用 Epic GitHub 源码版，则固定官方 5.7.4 tag/commit，不能混用 Launcher 与源码版证据）。
- Fab 下载的 **Lyra 5.7 兼容版本**，首次导入后立即提交到专用基准仓库或记录可复现的内容清单。
- Win64、Development Editor、VS 2022 17.14、MSVC 14.44.35214、Windows SDK 10.0.22621.0、.NET 8.0。
- 网络验证至少包含 standalone/单客户端 PIE 与 listen-server + 1 client 两种上下文；是否加入 dedicated server 由首个管线验收定义决定，不能在权威上下文里省略网络模式。

基准清单至少保存：

```json
{
  "ue": {
    "major_minor_patch": "5.7.4",
    "build_id": "<Build.version BuildId>",
    "changelist": "<Build.version Changelist>",
    "compatible_changelist": "<Build.version CompatibleChangelist>",
    "distribution": "launcher"
  },
  "lyra": {
    "compatible_engine": "5.7",
    "uproject_sha256": "<sha256>",
    "curated_asset_manifest_sha256": "<sha256>",
    "git_commit": "<40/64-hex object id>"
  },
  "toolchain": {
    "vs": "17.14.x",
    "msvc": "14.44.35214",
    "windows_sdk": "10.0.22621.0",
    "dotnet": "8.0.x"
  }
}
```

### 为什么不固定 UE 5.8

Epic 在 2026-06-23 发布 UE 5.8，距本次研究不足三周。5.8 的 Unified Input、工具链和底层框架有新变化，但这些不是 MVP 要验证的产品假设。立即采用 5.8 会把潜在差异混入“权威边界是否减少审查”的实验结果。建议在 MVP 闭环成立后，把 **5.7.4 → 5.8.x** 升级作为第一组 `Authoritative → Suspect → re-verify` 的真实失效测试。

### Lyra 版本的现实限制

Epic 的官方说明是 Lyra 随 UE 大版本更新，Fab 只向已安装兼容 Engine 的用户展示相应样例。它并不提供适合依赖管理器使用的公开、不可变包坐标。因此这里不能虚构 `Lyra 5.7.4`。可靠做法是：固定“Lyra 5.7 兼容快照”，再对下载物建立本地内容指纹。该限制必须进入 Authority Context，而不是写成模糊的“最新 Lyra”。

## UE 插件与命令行边界

### 插件形态

首版只建一个项目插件 `UEITPS`，包含一个 **`Editor` 类型模块**，不要一开始拆成长线规划中的九个组件。模块依赖只包含实际读取目标所需项：

```text
Core, CoreUObject, Engine, Projects,
AssetRegistry, UnrealEd, BlueprintGraph, KismetCompiler,
EnhancedInput, GameplayAbilities, GameplayTags, GameplayTasks
```

选择 `Editor` 而不是 `Runtime`，因为 Blueprint 图节点、资产编辑和部分 Kismet API 是 Editor-only；选择 `Editor` 而不是 `EditorNoCommandlet`，因为核心入口就是 Commandlet。插件不进入 Game/Client/Server Shipping 目标。

### 唯一 UE 入口

定义一个窄入口，例如 `UUEITPSCommandlet`：

```powershell
UnrealEditor-Cmd.exe "<Project>.uproject" -run=UEITPS `
  -Mode=Inspect -Request="<absolute-request.json>" -Output="<absolute-output.json>" `
  -unattended -nop4 -NullRHI -NoSplash -NoShaderCompile
```

Commandlet 只接受版本化 JSON 请求，不接受任意 C++ 表达式、任意 Python 或任意 console command。建议固定四种 mode：

| Mode | 能力 | 是否写 UE 资产 |
|---|---|---|
| `Fingerprint` | 输出 Engine/项目/插件/资产清单和关键配置指纹 | 否 |
| `Inspect` | 对明确列出的实体、属性、关系做存在性与值核验 | 否 |
| `Validate` | 编译 Blueprint、运行关系断言、输出确定性结果 | 否 |
| `ApplyAssetOps` | 对 allowlist 资产执行 allowlist 属性操作，支持 `-DryRun` | 是；必须在外部审批后 |

Commandlet 必须使用退出码表达成功/失败，并把结构化结果写到指定文件；stdout/stderr 只作为诊断证据。所有路径在进入 UE 前由外部 Agent 解析为绝对路径并验证位于项目或证据根目录内。

### 外部 Agent 边界

Python Agent 负责：

- 读取/验证权威 JSON，建立 SQLite 索引并查询；
- 对 Authority Context 做精确比较，生成复用计划和 Review Boundary；
- 生成并检查 Git Patch；
- 调用 Commandlet、UBT 和 Automation Test，捕获命令、退出码、日志与产物哈希；
- 组织人工确认和只追加的权威事件；
- 通过 MCP stdio 暴露有限工具。

Python Agent 不负责：

- 直接解析或改写 `.uasset`；
- 推断任意 Blueprint 的业务语义；
- 执行客户端传入的任意 shell/SQL；
- 绕过 dry-run、文件/行数限制、脏工作区检查或人工晋升。

## C++、Blueprint 与 GAS 元数据提取

### 提取原则

提取器的输入不是“扫描整个项目并理解功能”，而是人工策展记录中的 **expected entities / expected relations**。输出只有三态：`observed`、`missing`、`mismatch`，外加可重现的机械证据。任何未在策展清单中的新关系都只能成为 Candidate，不自动获得语义。

### C++ 反射实体

推荐顺序：

1. 通过 UHT/UBT 成功作为语法与反射声明有效性的第一道事实门；正常构建不单独调用 UHT，因为官方流程明确由 UBT 先调用 UHT。
2. 在 Commandlet 中通过 `UClass`、`UScriptStruct`、`UEnum`、`UFunction`、`FProperty` 读取已加载反射元数据，稳定键采用完整对象路径/字段路径。
3. 对 `.uproject`、`.uplugin`、`.Build.cs`、模块名和插件依赖做文本/descriptor 核验。
4. 对非反射的普通 C++ 函数，只验证人工记录的 `repo-relative file + qualified symbol + source span fingerprint`；MVP 不建立通用 C++ AST/调用图。

UHT 自带 JSON exporter，可作为一次性探测/诊断手段，但不建议把其内部导出格式直接当长期领域 schema。领域 schema 应由 UE-ITPS 自己控制，以免随 Engine 内部实现变化。

### 资产与 Blueprint

先用 Asset Registry 获取 `FAssetData`、对象路径、包名、类路径、tags、依赖/引用关系。Asset Registry 能在资产未加载时提供权威的磁盘资产索引，但它只描述可登记的资产事实，不能证明 Blueprint 中某条执行边或业务意图。

仅对人工列出的 Blueprint 加载资产，然后读取：

- `UBlueprint` / `UBlueprintGeneratedClass`、父类、interfaces、CDO 与默认属性；
- Simple Construction Script 组件结构；
- `FBlueprintEditorUtils::GetAllNodesOfClass` 查找明确节点类型；
- `UK2Node_CallFunction` 的目标 `UFunction`；
- `UEdGraphNode`/pins 的确定性连接，用于核验策展的特定执行边或数据边；
- Blueprint 编译状态与编译结果。

不要将节点标题、屏幕坐标、注释文本或自动生成的临时 graph 名作为稳定 ID。稳定定位器至少应包含 `asset object path + graph GUID/name + node GUID + referenced field path`，并允许在 Blueprint 重建导致 node GUID 变化时降级为 `Suspect`，而不是错误地自动匹配。

不推荐用 Unreal Python API 作为核心提取层：Epic 将其文档标记为 Experimental，且 Python 封装面不等于完整 Editor C++ API。Python 可以做人工调试脚本，但不能成为权威证据链的唯一来源。

### Enhanced Input → Gameplay Ability

对首条管线只核验策展的以下关系：

```text
Input Action / Mapping Context
  -> Lyra Input Config 中的 InputTag
  -> Lyra Ability Set 中 Ability + InputTag grant
  -> Lyra ASC 对输入 tag 的激活路径
```

Lyra 官方文档确认：通过 `ULyraAbilitySet` 授予的能力会在收到匹配 Input Tag 时检查激活；`GA_Hero_Dash` 使用 `InputTag.Ability.Dash`。这可作为“输入 tag 驱动 Ability”的权威参考节点，但 **Dash 与持续消耗体力的 Sprint 不是同一语义**。Sprint 应作为 sister implementation/新管线接受重新验证，不能因复用 Dash 的输入与激活机制而继承完整管线权威。

### Gameplay Ability / Gameplay Effect / Attribute

对明确列出的 Ability Blueprint 加载 generated class CDO，提取：

- ability class、parent、Asset/Ability tags；
- activation policy、instancing policy、net execution/security policy；
- cost/cooldown GE 引用以及 Lyra additional costs；
- activation required/blocked、cancel/block 关系；
- 蓝图中明确策展的 `CommitAbility`、Apply GE、End/Cancel 和移动速度切换节点关系；
- Ability Set 的 grant、InputTag、level 等绑定。

对明确列出的 `UGameplayEffect` CDO 提取：

- duration/period/stacking；
- modifiers 的 attribute、operation 与 magnitude 类型；
- executions、attribute captures；
- Gameplay Effect Components 及 tag requirements/grants；
- Gameplay Cue 与相关 tags；
- 目标 `UAttributeSet` 的 `FGameplayAttributeData` 属性路径。

UE 5.3 起 Gameplay Effect 行为逐步由 GE Components 承载，因此 5.7 提取器不能只读旧式单体字段；旧字段若被标记 deprecated，应记录但不能作为唯一事实。运行时 `GameplayEffectSpec` 是实例数据，不应写回为长期权威定义；长期定义指向 GE asset/CDO，运行证据另存为 validation evidence。

### 不提取的内容

- 任意 C++ 调用图、所有 Blueprint 执行流、动画/UI/音频全链路；
- 根据名字、注释或 embedding 自动断言 Feature/Pipeline；
- “看起来相似”资产的自动 sister implementation 归类；
- 未经人工选择的项目全量资产加载。

## 图谱与权威注册表存储

### 双层存储

**权威源：Git 中的 JSON 记录。** 每个节点、连接、管线、上下文、证据清单、审查和权威事件都是独立、schema-versioned 的 JSON 文档。它们适合代码审查、合并、签名/哈希和长期迁移。

**查询层：SQLite。** 从 JSON 全量或增量重建，数据库文件不作为权威、通常不提交 Git。任何 SQLite 丢失或损坏都可由相同 commit 的 JSON 重新生成，并得到相同 logical index hash。

推荐目录概念（不是要求本阶段立即创建）：

```text
authority/
  records/<kind>/<id>.json
  events/<utc>-<event-id>.json
  schemas/<schema-id>.schema.json
evidence/
  objects/sha256/<first2>/<hash>
  manifests/<run-id>.json
.ueitps/cache/authority.sqlite3
```

### 稳定标识

- 领域 ID：不可变、无语义的 UUIDv7 字符串，例如 `urn:ueitps:node:<uuid>`；显示名可改，ID 不改。
- UE 对象定位器：`/PluginOrGame/Path/Asset.Asset_C`、top-level asset path、字段完整路径；不使用磁盘绝对路径作身份。
- C++ 定位器：仓库相对路径 + qualified symbol + declaration fingerprint；行号只作展示，不作身份。
- Git 身份：完整 object ID，通过 `git rev-parse --show-object-format` 同时记录 `sha1`/`sha256` 算法，避免假定永远是 40 位。
- 内容身份：`sha256:<hex>`，输入为 RFC 8785 规范化 JSON 或原始证据字节。

### 节点、连接、管线的独立权威

权威断言统一指向 `subject_kind = node | edge | pipeline` 和 `subject_id`。不得由两个 Authoritative 节点推导出 Authoritative edge，也不得由所有 edge 分别 Authoritative 推导出完整 pipeline Authoritative。SQLite 视图只能显示当前状态，不能隐含晋升规则。

建议权威状态流：

```text
Candidate -> Reviewed -> Verified -> Adopted -> Authoritative
                    \-> Rejected
Authoritative -> Suspect -> Verified/Deprecated
```

状态变化使用不可变事件；“当前状态”是按事件序列计算的 materialized view。晋升事件必须引用 reviewer、Authority Context hash、Evidence manifest hash 和 Git commit。

### 证据存储

大日志、Automation 报告、Commandlet 输出和 Patch 按 SHA-256 内容寻址存储；JSON 权威记录只引用 hash、媒体类型、大小、生成命令、退出码和相对对象路径。不要把重复的大日志塞进 SQLite BLOB，也不要把机器绝对路径、token 或环境秘密写入权威库。

## Schema 与查询

### JSON Schema 规则

所有顶层文档都应包含：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "schema_id": "urn:ueitps:schema:<kind>:1",
  "schema_version": 1,
  "id": "urn:ueitps:<kind>:<uuid>",
  "kind": "<kind>",
  "created_at": "<RFC3339 UTC string>",
  "payload": {}
}
```

规则：

- 顶层及稳定对象默认 `unevaluatedProperties: false`；扩展必须经过 schema 升版。
- 时间一律 UTC RFC 3339 字符串；Git object ID、64 位整数、精度敏感 magnitudes 和哈希用字符串。
- 枚举用于 node/edge/evidence/authority 状态；显示文本不承担机器语义。
- `context` 不嵌入任意自由文本：Engine、Lyra fingerprint、module/plugin、platform、target/configuration、network mode、test suite、validated commit、dependencies 都是显式字段。
- Commandlet 输出 schema 与领域 schema 分离；先验证观察结果，再由编译器映射进领域记录。
- schema 迁移是显式 `vN -> vN+1`，旧记录不可被读取时“顺便修复”。

### SQLite 规范化表

建议最小表集：

```sql
node(id TEXT PRIMARY KEY, type TEXT NOT NULL, semantic_key TEXT, payload_json TEXT NOT NULL);
edge(id TEXT PRIMARY KEY, type TEXT NOT NULL, from_id TEXT NOT NULL, to_id TEXT NOT NULL,
     payload_json TEXT NOT NULL, FOREIGN KEY(from_id) REFERENCES node(id),
     FOREIGN KEY(to_id) REFERENCES node(id));
pipeline(id TEXT PRIMARY KEY, feature_family_id TEXT NOT NULL, payload_json TEXT NOT NULL);
pipeline_member(pipeline_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                subject_kind TEXT NOT NULL, subject_id TEXT NOT NULL,
                PRIMARY KEY(pipeline_id, ordinal));
authority_event(id TEXT PRIMARY KEY, subject_kind TEXT NOT NULL, subject_id TEXT NOT NULL,
                state TEXT NOT NULL, context_hash TEXT NOT NULL,
                evidence_manifest_hash TEXT NOT NULL, git_object_id TEXT NOT NULL,
                reviewer_id TEXT, occurred_at TEXT NOT NULL);
validation_run(id TEXT PRIMARY KEY, context_hash TEXT NOT NULL, status TEXT NOT NULL,
               manifest_hash TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT);
```

启用 `PRAGMA foreign_keys=ON`，写入使用显式事务；单写者模型足够。可选启用 WAL 改善 Agent 查询与索引重建并发，但每次发布证据前必须 checkpoint，不把 `-wal/-shm` 文件视为权威资产。

### 确定性查询模式

1. 先按 `feature_family + explicit tags + implementation kind` 找候选，不做 embedding 相似度搜索。
2. 连接 `current_authority` 视图，分别读取 node/edge/pipeline 权威。
3. 用结构化字段对 Context 做等值/允许范围比较；任一关键字段未知都不是 match。
4. 用 recursive CTE 查询明确 edge types 的上下游影响，并设置 depth/row limit 防止环和失控遍历。
5. FTS5 只用于 reviewer 查找描述、decision 和证据摘要；FTS 命中不能晋升权威，也不能生成语义边。

同一 Git commit、相同 authority source hash、相同 request JSON 必须生成相同排序后的结果。所有集合输出都显式 `ORDER BY`，不能依赖 SQLite 当前实现的隐含顺序。

## Patch 与 Git 边界

### 文本文件

文本变更采用标准 Git Patch：

1. 记录 `HEAD`、object format、`git status --porcelain=v2 -z` 和允许修改的 pathspec。
2. 若允许范围内存在用户未纳入本次任务的脏改动，则拒绝生成/应用，不自动 stash/reset。
3. Agent 在隔离工作区或内存候选树生成变更。
4. 输出 `git diff --binary --full-index -- <allowlisted paths>`，保存 patch hash、diffstat、文件数和增删行数。
5. 应用前运行 `git apply --check --index`；基线变化即判定 stale 并重新规划。
6. MVP 不自动使用 `--3way` 解决冲突；冲突代表上下文改变，应回到人工审查。

默认硬限制应由每个 request 明示：允许目录、文件 glob、最大文件数、最大新增/删除行数、是否允许新文件、是否允许 `.uasset`、编译重试次数。任何超限都是失败，不由 Agent 自行扩大范围。

### `.uasset` 与其他二进制资产

禁止在 UE 外部生成或拼接二进制 `.uasset`。确有必要修改已策展资产时：

1. `Inspect` 导出 before snapshot；
2. `ApplyAssetOps -DryRun` 返回结构化、property-level 预览；
3. 人工批准具体 asset/object/property/op；
4. Commandlet 在 UE 内执行并保存；
5. 再次 `Inspect` 生成 after snapshot，比较语义 diff；
6. Git 使用 `--binary --full-index` 保存实际二进制差异以支持精确回滚。

Reviewer 审查 before/after 语义快照和操作清单，不把不可读的 Git binary hunk 当语义证据。首个 MVP 只支持少量 allowlist 操作，例如已知 Ability/Effect 默认属性和已知 Data Asset 数组项；不支持任意 Blueprint 节点创建/重连。

## UHT、UBT 与 Automation Test 验证链

### 分层验证

| 层 | 命令/机制 | 证明什么 | 不能证明什么 |
|---|---|---|---|
| Schema | `jsonschema` + registry compiler | 记录结构、引用、枚举和基础不变量 | UE 实体仍存在 |
| Entity | `UEITPS -Mode=Validate` | 策展实体、属性、资产与关系匹配观察值 | 运行时行为正确 |
| UHT/UBT | `Build.bat <Project>Editor Win64 Development ...` | 反射声明、生成代码、模块依赖、C++ 编译/链接成功 | 功能语义正确 |
| Blueprint compile | Commandlet 内编译明确资产 | 目标 Blueprint 能编译 | 网络与时序行为正确 |
| Automation | `Automation RunTest UEITPS.Sprint` | 约定的功能、成本、结束/取消和网络断言 | 未覆盖平台/模式正确 |
| Human review | review boundary + evidence | 新语义和新组合被负责人接受 | 未来上下文永久正确 |

### UBT/UHT 命令

```powershell
& "<UE_ROOT>\Engine\Build\BatchFiles\Build.bat" `
  "<ProjectName>Editor" Win64 Development `
  "-Project=<absolute-project.uproject>" -WaitMutex -NoHotReloadFromIDE
```

正常管线不要先手工运行 UHT 再运行 UBT。Epic 文档明确说明 UBT 会先调用 UHT 解析 UObject 元数据并生成代码，再调用 C++ 编译器；直接跑 UHT 主要用于 UHT 开发或 exporter 调试。将 UBT 日志中 UHT 阶段结果一起保存即可满足可重复证据。

### Automation Test 命令

```powershell
& "<UE_ROOT>\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" `
  "<absolute-project.uproject>" `
  -unattended -nop4 -NullRHI `
  '-ExecCmds=Automation RunTest UEITPS.Sprint;Quit' `
  '-ReportExportPath=<absolute-evidence-report-dir>'
```

测试至少覆盖：

- InputTag 到 Ability grant/activation 的约定；
- stamina 足够/不足、持续消耗、耗尽自动结束；
- cancel/end 后移动速度和 tags 恢复；
- cost GE 修改正确 Attribute、operation 和 magnitude；
- owning client/server 的激活、资源消耗与最终状态一致；
- 新连接或 net execution policy 改变会把完整 pipeline 标为 Suspect，而不是只标单节点。

禁止无限编译修复循环。建议每个 plan 最多两次“修改后重编译”；仍失败则保存证据并回到重新规划，不继续扩大变更。

## 审计证据模型

每次 plan/apply/validate/review 产生一个不可变 run manifest，至少包含：

```text
run_id, parent_run_id, request_hash, plan_hash,
authority_source_commit, authority_source_hash,
project_head, git_object_format, dirty_state_hash,
ue_build_id/changelist, lyra_manifest_hash, tool_versions,
allowed_paths/limits, patch_hash, before/after_snapshot_hash,
commands (argv array, cwd id, start/end UTC, exit code),
stdout/stderr/report object hashes,
tests selected + results, reviewer decision,
promotion/rejection event ids
```

安全要求：

- `argv` 以数组记录，避免重新拼接 shell 字符串；环境变量只记录 allowlist 和敏感值的 redacted hash。
- 每个外部命令有 timeout、输出大小上限和可取消句柄。
- 证据对象创建后不可原地覆盖；同 hash 已存在则校验长度/hash 后复用。
- promotion 引用完整 manifest；任何缺失证据、失败命令或 context mismatch 都不能产生 Authoritative 事件。
- 失败证据同样保留，它用于解释为什么候选未晋升和何时需要重新验证。

## 本地 Agent 接口

### MCP stdio 推荐接口

stdio 是首版唯一 transport。MCP 规范要求客户端启动 server 子进程，stdin/stdout 只承载 UTF-8 JSON-RPC；日志必须写 stderr。无需 HTTP 端口、鉴权服务器或后台 daemon。

只暴露以下高层工具：

| 工具 | 副作用 | 返回 |
|---|---|---|
| `authority.search` | 无 | 明确过滤条件下的候选及 node/edge/pipeline 独立权威 |
| `authority.explain` | 无 | context 对比、证据引用、为何可/不可复用 |
| `plan.create` | 只写 run evidence | 复用分类、变更计划、review boundary、限制 |
| `patch.preview` | 只写隔离候选和 evidence | Patch、语义 asset ops、规模和风险 |
| `patch.apply` | 有；需显式 approved plan token | 应用结果和 before/after hashes |
| `validate.run` | 生成构建/测试产物 | 每层验证结果和证据 manifest |
| `review.record` | 追加 review event | 接受/拒绝及 reviewer 信息 |
| `authority.promote` | 追加 authority event；需 review + pass manifest | 新状态与失效依赖 |

不要暴露 `run_shell(command)`, `execute_sql(sql)`, `write_file(path, text)` 或 `edit_asset(path, arbitrary_payload)`。MCP 只是受控领域 API，不是给 Agent 绕过治理边界的后门。

### 版本策略

当前 Python MCP SDK v1.27.2 是稳定线；官方仓库说明 v2 仍在发布前阶段，并建议依赖方加 `<2` 上界。MVP 固定 v1.27.2，协议版本通过 MCP 初始化协商，不把 draft 版本常量散落在业务代码。v2 稳定后作为独立升级任务，先跑 conformance 与所有副作用工具授权测试。

## 安装与基准检查

以下是预期安装形态，不要求把系统级组件 vendoring 进仓库：

```powershell
# 1. Epic Games Launcher 安装 UE 5.7.4，并从 Fab 创建与 5.7 兼容的 Lyra 项目。
# 2. Visual Studio Installer 固定 VS 2022 17.14、MSVC 14.44.35214、Windows SDK 10.0.22621.0。

# 3. Python 依赖（实际项目应生成并提交 pylock.toml/等价 lock，且校验 hashes）
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install `
  "mcp==1.27.2" "pydantic==2.13.4" "jsonschema==4.26.0" "rfc8785==0.1.4"

# 4. 记录实际运行时，不信任 PATH 上的隐含版本
git --version
.venv\Scripts\python --version
.venv\Scripts\python -m sqlite3 -v
```

基准预检必须比较实际输出与 baseline manifest；仅检查“主版本相同”不够。UE、Lyra、工具链、插件依赖或目标网络模式不同，都应让相关权威进入 Suspect。

## 替代方案

| 推荐 | 替代 | 何时才使用替代 |
|---|---|---|
| Git JSON 权威源 + SQLite 派生索引 | PostgreSQL | 多用户并发写、服务化权限/备份成为真实需求后 |
| SQLite 邻接表 + recursive CTE | Neo4j/专用图数据库 | 图达到跨项目大规模、复杂路径查询被实测证明是瓶颈后 |
| 领域 JSON Schema | RDF/OWL/SHACL/SPARQL | 产品明确转向跨组织本体互操作，而非单项目人工策展后 |
| C++ Editor Commandlet | Unreal Python | 一次性人工编辑/探测脚本，且结果不进入唯一权威证据链时 |
| UE 反射 + 策展 locator | Clang/Tree-sitter 全项目索引 | 经验证确实需要非反射 C++ 全量调用图，且该投入直接降低审查时 |
| MCP stdio | Streamable HTTP | 需要跨进程长期服务或远程客户端，并具备 Origin、认证和最小绑定面设计后 |
| Git Patch + UE property ops | 直接改 `.uasset` bytes | 不应使用；二进制资产必须由匹配版本 UE 读写 |

## 明确不推荐

| 不推荐 | 原因 | 替代 |
|---|---|---|
| **UE 5.8 作为首个实验基准** | 发布时间过近，引入与产品假设无关的 Engine/Lyra 迁移变量 | UE 5.7.4；之后把 5.8 当失效重验证用例 |
| **“最新版 Lyra”** | 不可复现，Fab 样例随兼容 Engine 更新 | 冻结 Lyra 5.7 下载物并生成资产清单 hash |
| **把 SQLite 文件当权威源提交** | 二进制 diff 难审查，迁移/重建不可解释 | Git JSON 记录为权威，SQLite 为派生缓存 |
| **Neo4j、向量数据库、embedding 搜索** | MVP 图小且语义人工策展；会把范围扩成通用发现 | 邻接表、精确 tags/context、递归 CTE |
| **全项目 Blueprint/C++ 语义扫描** | 无法从机械结构可靠恢复业务权威，且违背明确范围 | 只验证策展实体和关系 |
| **Unreal Python 作为唯一提取器** | 官方仍标 Experimental，API 面随 Engine 漂移 | C++ Editor Commandlet；Python 只做外部编排 |
| **仅解析源文件而不跑 UHT/UBT** | 无法证明 UE 反射生成、模块依赖、编译链接有效 | UBT 作为编译门，自动包含 UHT |
| **自动 `git apply --3way`** | 会在上下文已改变时静默形成新组合，破坏权威边界 | stale 即失败并重新规划/人工审查 |
| **用 Git binary diff 审查 Blueprint 语义** | 二进制 Patch 只能回滚，不能解释属性/图变化 | UE before/after snapshot + allowlist asset ops |
| **MCP 暴露任意 shell/SQL/文件写** | 直接绕过路径、规模、预览、审计和审批约束 | 高层领域工具 + approved plan token |
| **单一 `authoritative=true`** | 忽略 node/edge/pipeline 独立权威和上下文失效 | 事件化状态 + context/evidence/commit 绑定 |

## 版本兼容矩阵

| 组件 | 兼容对象 | 约束/备注 |
|---|---|---|
| UE 5.7.4 | Lyra 5.7 compatible snapshot | 不是 `Lyra 5.7.4`；必须另加本地资产清单指纹 |
| UE 5.7.x binary | VS 2022 >=17.8，推荐 17.14 | MVP 固定 17.14.x；VS 2019 不支持 |
| UE 5.7.x | MSVC 14.44.35214 / Windows SDK 10.0.22621 / .NET 8 | 按 Epic 推荐值固定 |
| UEITPS Editor plugin 0.1.0 | UE 5.7.x only | 首版不声明跨 5.8 兼容；升级需重编译和全套验证 |
| Python 3.14.6 | `mcp==1.27.2` | 官方 SDK 要求 Python >=3.10；固定 `<2` 防止即将到来的 major upgrade |
| Python 3.14.6 | `pydantic==2.13.4`, `jsonschema==4.26.0`, `rfc8785==0.1.4` | lock 文件固定完整传递依赖与 hashes |
| SQLite 3.53.3 | schema `user_version=1` | 权威 JSON 不依赖 SQLite 内部 JSONB 格式；索引可重建 |
| Git >=2.45,<3 | patch/audit contract v1 | 基准机固定 2.55.0；机器输出统一使用 porcelain v2 `-z` |
| JSON Schema 2020-12 | authority/command/evidence schema v1 | dialect URI 必须显式；未来 draft 不自动升级 |
| MCP SDK 1.27.2 | MCP negotiated protocol | stdio only；升级 SDK/协议视为接口变更并跑 conformance |

## 实施顺序建议

1. 先冻结 UE/Lyra/toolchain baseline manifest，并用空插件跑通 UBT + 空 Automation suite。
2. 定义 authority/evidence/commandlet-output 三组 JSON Schema 和 RFC 8785 hash 规则。
3. 人工策展最小 sprint 图；建立 Git JSON → SQLite 的确定性编译器和精确查询。
4. 实现只读 `Fingerprint/Inspect/Validate` Commandlet，先证明所列实体与关系能稳定核验。
5. 实现 plan/review boundary 与文本 Patch；再增加极窄的 `ApplyAssetOps`。
6. 接入 UBT/Automation 证据与人工 review/promotion 事件。
7. 最后加 MCP stdio 薄适配；MCP 不应先于领域 API 和副作用边界。

## 来源

### Epic Games 官方资料

- [UE 5.8 发布公告](https://www.unrealengine.com/news/unreal-engine-5-8-is-now-available) — 核验 5.8 发布时点与版本定位。
- [UE 5.7.4 Hotfix 公告](https://forums.unrealengine.com/t/5-7-4-hotfix-released/2705041) — 核验 5.7.4 及热修复时点。
- [Lyra Sample Game（UE 5.7）](https://dev.epicgames.com/documentation/unreal-engine/lyra-sample-game-in-unreal-engine?application_version=5.7) — 核验 Lyra 随 UE 更新、Fab/Launcher 获取和兼容 Engine 约束。
- [升级 Lyra 到新 Engine](https://dev.epicgames.com/documentation/en-us/unreal-engine/upgrading-the-lyra-starter-game-to-the-latest-engine-release-in-unreal-engine?application_version=5.6) — 核验 C++ Lyra 跨 UE 大版本需手工升级。
- [Abilities in Lyra（UE 5.7）](https://dev.epicgames.com/documentation/en-us/unreal-engine/abilities-in-lyra-in-unreal-engine?application_version=5.7) — 核验 Ability Set/Input Tag、Dash、GAS 扩展与资产命名。
- [Lyra Input Settings（UE 5.7）](https://dev.epicgames.com/documentation/en-us/unreal-engine/lyra-input-settings-in-unreal-engine?application_version=5.7) — 核验 Enhanced Input 与 Lyra Input Config 边界。
- [Gameplay Ability System（UE 5.7）](https://dev.epicgames.com/documentation/en-us/unreal-engine/understanding-the-unreal-engine-gameplay-ability-system?application_version=5.7) — 核验 Ability/Effect/Attribute/网络职责。
- [Gameplay Effects（UE 5.7）](https://dev.epicgames.com/documentation/en-us/unreal-engine/gameplay-effects-for-the-gameplay-ability-system-in-unreal-engine?application_version=5.7) — 核验 GE asset/spec、modifier、execution 与 GE components。
- [Asset Registry](https://dev.epicgames.com/documentation/en-us/unreal-engine/asset-registry-in-unreal-engine) — 核验未加载资产、FAssetData、tags 与查询能力。
- [FBlueprintEditorUtils API（UE 5.7）](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Editor/UnrealEd/FBlueprintEditorUtils?application_version=5.7) — 核验 Blueprint graph/node Editor API。
- [UK2Node_CallFunction API（UE 5.7）](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Editor/BlueprintGraph/UK2Node_CallFunction?application_version=5.7) — 核验 Blueprint 函数调用节点接口。
- [Unreal Header Tool](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-header-tool-for-unreal-engine) — 核验 UBT→UHT→C++ compiler 两阶段流程及 JSON exporter。
- [Unreal Build Tool（UE 5.7）](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-build-tool-in-unreal-engine?application_version=5.7) — 核验 UBT 与 Build.cs/Target.cs 边界。
- [运行 Automation Tests](https://dev.epicgames.com/documentation/en-us/unreal-engine/run-automation-tests-in-unreal-engine) — 核验 `-ExecCmds` 与 `-ReportExportPath`。
- [Plugins](https://dev.epicgames.com/documentation/en-us/unreal-engine/plugins-in-unreal-engine) — 核验 plugin/module 类型与 Editor/commandlet 边界。
- [UE 5.7 Visual Studio 配置](https://dev.epicgames.com/documentation/en-us/unreal-engine/setting-up-visual-studio-development-environment-for-cplusplus-projects-in-unreal-engine?application_version=5.7) — 核验 VS/MSVC/SDK/.NET 版本。

### 数据、协议与工具官方资料

- [SQLite 3.53.3](https://www.sqlite.org/releaselog/current.html) — 核验当前维护版本。
- [SQLite recursive CTE](https://www.sqlite.org/lang_with.html) — 核验图/层级递归查询能力和限制。
- [SQLite JSON](https://www.sqlite.org/json1.html) — 核验 JSON/JSONB 能力及 JSONB 仅供 SQLite 内部使用的边界。
- [SQLite FTS5](https://www.sqlite.org/fts5.html) — 核验本地全文索引能力。
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) — 核验当前发布 dialect 与 meta-schema。
- [RFC 8785 JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html) — 核验规范化哈希的确定性规则。
- [Git diff](https://git-scm.com/docs/git-diff) — 核验 `--binary --full-index`。
- [Git apply](https://git-scm.com/docs/git-apply) — 核验 `--check`、`--index`、`--3way` 行为。
- [Git status](https://git-scm.com/docs/git-status) — 核验 porcelain v2 与 `-z` 的机器解析稳定性。
- [Python 3.14.6 文档](https://docs.python.org/3.14/) — 核验 Python 固定版本。
- [Python sqlite3](https://docs.python.org/3.14/library/sqlite3.html) — 核验无独立 server 的本地数据库接口及运行时版本检查。
- [MCP transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) — 核验 stdio/JSON-RPC、UTF-8 与 stdout/stderr 规则。
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) — 核验 v1 稳定线、v2 状态与 `<2` 约束建议。
- [MCP Python SDK v1.27.2](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v1.27.2) — 核验固定 SDK 版本。
- [python-jsonschema](https://github.com/python-jsonschema/jsonschema) — 核验 Draft 2020-12 支持与 4.26.0 版本。
- [Pydantic](https://github.com/pydantic/pydantic) — 核验 2.13.4 版本。
- [Trail of Bits rfc8785.py](https://github.com/trailofbits/rfc8785.py) — 核验 0.1.4 实现及无依赖特性。

---
*本研究仅服务于 UE-ITPS 首个“人工策展最小权威图谱”MVP，不构成通用 UE 语义发现、跨项目权威库或企业部署方案。*
