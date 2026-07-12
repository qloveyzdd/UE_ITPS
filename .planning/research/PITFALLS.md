# Pitfalls Research

**Domain:** 固定 UE 5.7 / 匹配 Lyra 5.7 的人工策展体力冲刺最小权威图谱与增量审查闭环  
**Researched:** 2026-07-12  
**Confidence:** HIGH（UE 工具链、资产、GAS 与网络机制）；MEDIUM（产品风险与实验阈值，需 MVP 实测）

## 研究边界与判读规则

本文只讨论首个 UE-ITPS MVP：固定一个 UE/Lyra 版本，在单一项目中人工策展 Enhanced Input → Gameplay Ability → Gameplay Effect 的体力冲刺垂直管线。它不推断任意 UE 项目，不设计跨版本或跨项目权威传播，也不把 Lyra 架构视为通用标准。

- **Epic 官方事实**：UE/Lyra/GAS、资产、构建和测试机制均由文末 Epic 一手资料支持。
- **风险推断**：凡涉及 UE-ITPS 的权威模型、失效策略、恢复成本和实验判定，均明确标为“风险推断”。
- **阶段名称**：当前尚无 ROADMAP；下文使用建议阶段：阶段 0「冻结基线与行为契约」、阶段 1「策展图谱与权威模型」、阶段 2「确定性探针与证据」、阶段 3「受限 Patch 与回滚」、阶段 4「审查、晋升与失效」、阶段 5「对照实验与复利验证」。

## Critical Pitfalls

### Pitfall 1: 把代码相同或相似误当成功能语义相同

**What goes wrong:**
两个实现拥有相同 C++ 函数、Gameplay Ability 类或 Gameplay Effect 资产，却因 Input Mapping Context、Input Tag、Ability Set 授予来源、Activation Policy、成本生命周期、取消路径或网络执行策略不同而产生不同冲刺语义。系统折叠 Diff 后，审查者看不到真正发生变化的连接和上下文。

Epic 官方事实：Enhanced Input 的 Mapping Context 可按运行时状态增删并具有优先级，Trigger/Modifier 会改变输入解释；Lyra Ability 可由 Pawn Data、Experience/Game Feature 或 Equipment 等不同来源授予；GAS Ability 具有激活、执行、取消及网络执行语义。[S1][S2][S3][S4]

**Why it happens:**
文本 diff 和符号指纹容易计算，而“按住输入、持续耗体力、耗尽结束、释放取消、服务端拒绝后协调”的行为契约跨越代码、资产和运行时。**风险推断：** 若权威匹配以源码或资产内容摘要为主键，团队会系统性高估复用安全性。

**How to avoid:**
先冻结冲刺行为契约，再匹配实现。权威断言至少同时绑定实体指纹、关系谓词、完整管线 ID、Activation/Net Execution Policy、网络模式、成本/持续 Effect、结束与失败路径。代码相同但任一语义字段不同，分类为“上下文适配”或“新连接”，失败关闭到人工审查。

**Warning signs:**

- 复用理由只写“类/函数/资产未变化”，没有行为契约字段。
- Input Action 到 Input Tag 或 Ability 到 Cost Effect 的边没有独立证据。
- 单机 PIE 通过便宣称网络冲刺可复用。
- 取消、体力耗尽、Pawn 重生或服务端拒绝不在测试矩阵中。

**Recovery strategy:**
撤销相关管线的 Authoritative 状态为 Suspect；重建从输入到属性变化的有序边；补齐开始、保持、释放、耗尽、取消、服务端接受/拒绝场景；重新计算审查边界，要求此前被折叠的变化重新审查。

**Phase to address:** 阶段 0 定义行为契约；阶段 1 将语义字段纳入管线；阶段 2 用行为测试证明。

---

### Pitfall 2: 把节点权威自动传递给新连接或完整管线

**What goes wrong:**
Input Action、Gameplay Tag、Ability、Gameplay Effect 和 Attribute 各自都已验证，但新连接改变了激活、授予、数据流、生命周期或网络边界。系统仍将组合标为权威，导致新逻辑逃逸审查。

**Why it happens:**
图模型若只有节点状态，路径查询会自然地把“所有节点可信”简化为“整条路径可信”。**风险推断：** 这是首个 MVP 最致命的模型错误，因为系统越擅长折叠权威节点，越容易隐藏组合缺陷。

**How to avoid:**
实体、关系、管线分别拥有不可继承的 authority assertion。新增边永远从 Candidate 开始；管线权威要求有序步骤、边集合、前置条件、失败路径与网络边界都匹配，且拥有独立证据。任何未知或缺失都进入审查闭包。

**Warning signs:**

- schema 中只有 `node.authoritative`，没有 relation/pipeline assertion。
- 新增 Input Tag 路由未增加待审项。
- 系统用节点权威比例估算管线权威比例。
- “全是旧组件”被当作免审理由。

**Recovery strategy:**
停止权威晋升；将所有由节点状态推导出的边和管线批量降为 Candidate/Suspect；从最近可信图谱快照重算边界；对已执行任务补做新连接审查和端到端测试。

**Phase to address:** 阶段 1 必须在 schema 与边界算法中根治；阶段 4 验证晋升不能跨层传递。

---

### Pitfall 3: 稳定 ID 随路径、名称或内容指纹漂移

**What goes wrong:**
资产移动/重命名、Blueprint 生成类路径变化、C++ 符号改名或内容摘要变化时，系统创建新 ID 或复用旧 ID 指向另一对象，造成权威丢失、错误继承、悬挂边和重复节点。

Epic 官方事实：UE 资产由对象/包路径引用；移动或重命名资产会留下 Redirector，未加载包可借此找到新位置；Blueprint 包还同时包含资产与生成类对象。Asset Registry 也提供重命名事件，但其异步扫描未完成前资产集合可能不完整。[S5][S6][S7]

**Why it happens:**
路径和 hash 都天然“看起来唯一”，实现简单，却分别代表可变定位与当前内容，不代表领域身份。Redirector 又可能暂时掩盖定位漂移。

**How to avoid:**
创建时分配不可变 UUIDv7/ULID 作为 identity；对象路径、qualified symbol、Gameplay Tag 字符串只作为可更新 locator；内容/结构摘要只作为 fingerprint。重命名必须记录显式 lineage/decision，先确认是同一对象再更新 locator；等待 Asset Registry 完成扫描，并检测 Redirector、重复 locator、悬挂边和 ID 复用。

**Warning signs:**

- ID 由资产路径、类名或 SHA-256 直接派生。
- 一次资产移动造成“删除一个节点、新增一个权威节点”。
- Redirector 存在时扫描通过，Fixup 后节点消失。
- 同一 ID 的 locator 无审计记录地改变。

**Recovery strategy:**
冻结写回；从 Git 历史、Redirector、Asset Registry rename 信息和人工确认建立旧 ID → 新 locator 对照；合并误生成的重复节点但保留 alias/lineage；重新计算所有入边、出边、pipeline fingerprint 与 authority assertion。

**Phase to address:** 阶段 1 定义 ID/locator/fingerprint 分离；阶段 2 实现漂移与悬挂引用检查；阶段 4 审计迁移决策。

---

### Pitfall 4: UE/Lyra/GAS 版本或网络上下文失配仍沿用权威

**What goes wrong:**
只记录“UE5”“Lyra”或代码提交，而没有 Engine BuildId/Changelist、Lyra 内容身份、插件/模块状态、Target/Configuration、网络模式和 Ability Net Execution Policy。旧证据被用于另一构建或另一客户端/服务端语义。

Epic 官方事实：Lyra 会随 UE5 更新且采用模块化 Game Feature/Experience；GAS 支持服务端执行、客户端预测及服务端拒绝后的协调；UBT 的 Game、Client、Server、Editor 是不同 Target，Development、Test、Shipping 等配置也不等价；PIE 的某些网络行为与独立进程存在差异。[S3][S8][S9][S19]

**Why it happens:**
固定“大版本”比固定可执行环境容易，Editor 本地双开又比独立客户端/服务端便宜。**风险推断：** 若上下文比较允许模糊匹配，版本冻结只是名义上的，实验结果不可复现。

**How to avoid:**
建立 baseline lock：精确记录 Engine `Build.version`、BuildId/Changelist、`.uproject EngineAssociation`、Lyra 样本/内容摘要、启用插件、Game Feature/Experience、平台、Target、Configuration、网络拓扑、Net Execution Policy、测试命令和代码/权威库提交。关键字段只能 exact match；变化立即 Suspect，不做“兼容推测”。至少验证单机、listen/dedicated 约定场景和受控网络延迟/丢包。[S18]

**Warning signs:**

- 权威上下文写成 `UE5.x` 或 `latest Lyra`。
- 只有 Editor Development 构建证据。
- 测试均在理想本机网络且无服务端拒绝场景。
- Experience/Game Feature 未锁定却复用 Ability Set 关系。

**Recovery strategy:**
停止比较实验；将受影响 assertion 批量标 Suspect；恢复基准版本或建立新的 baseline lock；在新上下文重新运行关系、构建、资产和网络行为验证，不继承旧管线权威。

**Phase to address:** 阶段 0 阻断；阶段 2 证据强制携带上下文；阶段 4 自动触发失效。

---

### Pitfall 5: 遗漏 Blueprint、资产和软引用依赖

**What goes wrong:**
文本 Patch 只包含 C++/配置，却漏掉 Blueprint 默认值、Ability Set/Data Asset、Input Mapping Context、Gameplay Effect、Gameplay Tag 配置、动画/移动配置或软引用。Editor 中因资产已加载而工作，干净启动、Cook 或目标 Experience 下失败。

Epic 官方事实：硬引用会随拥有者加载，软引用通过间接路径解析；Lyra 的 Ability Set 本身是 Data Asset，并可由 Game Feature、Experience 或 Equipment 授予；Asset Registry 异步收集未加载资产信息，属性若未保存/重存也可能尚未反映；Epic 的 Data Validation 可以验证资产及其依赖，UE Diff Tool 仅支持 Blueprint 和相邻部分资产类型，并非所有资产。[S2][S5][S7][S10][S11][S12]

**Why it happens:**
Git 文本 diff 对 `.uasset` 语义不可见，已打开 Editor 的内存状态还会掩盖未保存资产或缺失引用。**风险推断：** 只保存文件名清单会让“Patch 完整”成为错觉。

**How to avoid:**
人工策展明确列出管线必需资产与关系；在 Asset Registry 扫描完成后查询硬/软/管理依赖；对点名资产执行 Data Validation（含 dependencies）、Blueprint/资产差异审查和冷启动验证；记录包级前后摘要、dirty/unsaved 状态和重存结果。首版不承诺通用二进制资产自动编辑。

**Warning signs:**

- 计划只列 `.cpp/.h/.ini`，功能却由 Ability Set/Blueprint 配置。
- Editor 不重启即可通过，干净进程失败。
- Asset Registry 仍在加载就生成“依赖完整”证据。
- `.uasset` 变化只显示二进制 hash，没有 UE 内差异或属性探针。

**Recovery strategy:**
隔离并保留失败现场；关闭 Editor 后从干净工作树重现；补齐丢失/未保存包、软引用与策展关系；修复 Redirector；重新运行依赖验证、冷启动、Cook/约定运行测试，并扩大人工审查到所有受影响资产。

**Phase to address:** 阶段 1 策展资产闭包；阶段 2 实现 UE 内探针；阶段 3 将二进制资产分轨审计。

---

### Pitfall 6: 混淆 Editor-only 与运行时边界

**What goes wrong:**
扫描/验证代码或依赖 Editor 模块的逻辑被放入 Runtime，或 Editor 中可访问的数据/资产在 Game、Client、Server 或 cooked build 中不可用。结果是 Editor Target 编译和 PIE 测试通过，运行时 Target 链接、加载或 Cook 失败。

Epic 官方事实：UE 最常见模块类型 Runtime 与 Editor 分别面向运行时和编辑器类；UBT Target 中 Game 需要 cooked data，Client 不含 server code，Server 不含 client code，Editor 是扩展编辑器的目标。[S8][S13]

**Why it happens:**
MVP 的 Asset Registry、反射和 Data Validation 探针天然运行在 Editor 内，容易让开发者把控制面、权威状态机或运行时冲刺逻辑与 Editor API 混在一起。

**How to avoid:**
外部 core 拥有权威语义与流程；薄 UE 插件只做点名事实探测，并声明 Editor 模块。运行时冲刺实现不得依赖 Editor/DataValidation 模块。验证矩阵至少包含固定 Editor Target 与一个约定 Game/Client/Server Target；若 MVP 不承诺 packaged build，必须把未验证范围明确写入 evidence，不能默认为通过。

**Warning signs:**

- Runtime `.Build.cs` 引入 `UnrealEd`、Editor-only 插件或验证模块。
- 只有 `Development Editor` 构建记录。
- 运行时逻辑读取 Editor-only 数据或依赖未 Cook 内容。
- 探针插件拥有 authority 晋升/写回能力。

**Recovery strategy:**
将被污染的 assertion 标 Suspect；拆分 Runtime/Editor 模块与依赖方向；移出 Editor-only 类型；用目标 Target/Cook 重新构建和运行。无法移除的 Editor 依赖应明确把该能力降为仅编辑器工具，而非运行时功能。

**Phase to address:** 阶段 0 锁定目标矩阵；阶段 2 固化插件边界；阶段 3/4 以非 Editor 构建作晋升门禁。

---

### Pitfall 7: 误读 UHT、UBT 与 Automation Test 的证据

**What goes wrong:**
把 UHT 通过当作 C++ 编译通过，把 UBT 成功当作资产/Blueprint/网络行为正确，把“命令退出 0”当作指定测试全部运行并通过，或把 EditorContext 测试结果外推到 Client/Server。

Epic 官方事实：正常构建先由 UBT 调用 UHT 解析 UObject 元数据并生成代码，再调用 C++ 编译器；Automation Test 有 Editor、Client、Server、Commandlet 等上下文标志，测试可被分组/筛选，命令行可导出 JSON/HTML 报告；Epic 明确要求测试不得假设 Editor/游戏初始状态，并应清理磁盘状态。[S14][S15][S16][S17]

**Why it happens:**
编排器最容易记录进程码和最后一行日志，却没有证明命令、Target、测试发现数量、实际执行集合、跳过项与报告完整性。旧产物或空测试选择也可能制造绿色结果。

**How to avoid:**
把证据拆层：关系探针、UBT（其中记录 UHT 与编译阶段）、Data Validation、Automation 行为测试。保存精确命令、工作树提交/dirty 状态、Engine 身份、Target/Configuration、测试过滤器、发现/运行/通过/失败/跳过数量、结构化报告 hash 和时间。约定测试数量为零、报告缺失、上下文不匹配、日志来自旧 run 均应失败关闭。

**Warning signs:**

- evidence 只有 `exit_code: 0` 或人工写的“测试通过”。
- UHT 单独运行成功后未运行 UBT 编译。
- 报告中实际测试数为 0 或目标测试被跳过。
- EditorContext 测试被标成 dedicated server 证据。
- 重试后只保留最后一次成功日志，失败尝试被覆盖。

**Recovery strategy:**
撤销由该证据支持的晋升；清理/隔离旧报告与中间产物；以固定命令重跑完整门禁；核对结构化报告中的测试身份和上下文；保留所有重试记录并重新绑定 evidence hash。

**Phase to address:** 阶段 2 定义证据 schema 与空测试防护；阶段 4 晋升时验证证据策略。

---

### Pitfall 8: Patch 可预览但回滚不完整

**What goes wrong:**
unified diff 能反向应用 C++，却没有恢复 `.uasset`、Redirector、生成/删除文件、配置、插件描述符、未保存 Editor 状态、图谱写回或外部生成物。回滚后仓库看似干净，但项目语义或 authority 状态已分叉。

Epic 官方事实：资产必须通过 Unreal Editor 管理，直接在磁盘移动/删除可能破坏项目；资产重命名会产生 Redirector；UE 资产差异需要 UE Diff Tool，且并非所有资产类型受支持。[S6][S11][S12]

**Why it happens:**
“Patch”常被缩减为文本 diff，而 UE 事务横跨文本、二进制包、资产注册状态和权威元数据。**风险推断：** 若写回与代码变更不是同一可恢复事务，失败后可能保留虚假权威。

**How to avoid:**
每次 run 使用隔离 worktree/副本与 preimage manifest，列出所有允许路径、已存在/新增/删除文件、包摘要、Redirector、authority 文件摘要和 Editor dirty 状态。文本走 `apply --check`/反向验证；资产写入仅由白名单 mutation plan 执行并保存包前像；验证未通过或人工拒绝时禁止 authority 写回。晋升写回使用 compare-and-swap/原子替换。

**Warning signs:**

- 回滚计划只描述 `git apply -R`。
- `.uasset`、新增文件或 authority manifest 不在变更清单。
- Patch 应用前后没有工作树/包摘要。
- 测试失败后图谱已经标为 Authoritative。

**Recovery strategy:**
立即禁止继续写入；从 preimage 或干净基线恢复整个隔离环境，而非逐文件猜测；通过 Editor 恢复/重存资产并处理 Redirector；将失败 run 产生的 authority/decision 全部撤销或标 invalid；重新扫描确认无越界变化。

**Phase to address:** 阶段 3 核心门禁；阶段 4 保证“验证 + 人审 + 写回”顺序不可颠倒。

---

### Pitfall 9: 权威失效只作用于改动节点，不传播到依赖关系和管线

**What goes wrong:**
Ability、Effect、Input Config、插件、网络模式或测试证据改变后，仅该节点变 Suspect；依赖它的关系、管线、Implementation 和复用计划仍保持 Authoritative，继续被折叠。

**Why it happens:**
失效传播是反向依赖闭包问题，手工维护容易漏边；团队还可能为保持高复用率而只失效直接对象。**风险推断：** 不传播比不设权威更危险，因为 UI 会给出错误的确定性信号。

**How to avoid:**
为 assertion 建立反向依赖：实体 → 关系 → 管线 → Implementation/Decision，以及 context/evidence → assertion。指纹、locator 语义、关键上下文字段、测试策略或证据变化时，确定性计算受影响闭包并全部转 Suspect；允许人工缩小传播范围，但必须给出新证据和审计理由，不能静默覆盖。

**Warning signs:**

- 节点 fingerprint 改变后管线状态仍为绿色。
- 删除/改名资产只产生局部告警。
- 测试被删除或过滤器改变，不影响旧 authority。
- UI 显示高复用率，却存在大量 Suspect 依赖。

**Recovery strategy:**
暂停复用计划；从最近可信快照重建反向依赖索引；对所有受影响 assertion 执行保守闭包失效；按从叶节点、关系到完整管线的顺序重验证，最后才恢复权威。

**Phase to address:** 阶段 1 建依赖模型；阶段 2 产生可靠变更事件；阶段 4 实现传播与重验证队列。

---

### Pitfall 10: 评测基线被学习效应、任务差异或工具暴露污染

**What goes wrong:**
同一 reviewer 先看完整 Diff 再看边界报告、两组任务难度不等、Treatment 隐藏完整 Diff、权威库在实验中途更新，或计时包含/排除不同等待时间。审查时间下降无法归因于 UE-ITPS。

**Why it happens:**
真实 UE/GAS 审查样本昂贵，团队会用少量案例追求漂亮均值。**风险推断：** 在首个 MVP 中，实验设计偏差很可能大于真实产品效应。

**How to avoid:**
冻结任务、代码提交、baseline lock、authority 快照、缺陷金标准和计时规则；使用复杂度匹配的冲刺变体与交叉/配对顺序；Treatment 始终可展开完整 Diff；记录工具等待、主动阅读、决策时间、reviewer 经验和暴露顺序；基线轮与“写回后的第二任务”分开，避免把学习效应伪装成复利。

**Warning signs:**

- 只有一个任务、一个 reviewer、一次顺序。
- Treatment 使用更简单或缺陷更少的 Patch。
- 权威图谱在对照与处理之间改变。
- 只报告平均时间，不报告原始数据、遗漏与错误权威。

**Recovery strategy:**
将受污染运行标记 excluded，但保留原始记录；重新冻结材料并随机/平衡顺序；由未参与实现的资深 UE/GAS 工程师重建金标准；小样本只报告效应量和不确定性，不宣称统计显著。

**Phase to address:** 阶段 5；实验所需锁文件和不可变 run 记录必须在阶段 0/2 预先提供。

---

### Pitfall 11: 审查时间下降，但缺陷遗漏或错误权威上升

**What goes wrong:**
系统成功隐藏大量“已权威”内容，reviewer 更快完成，但新连接、网络语义、资产依赖或失败路径缺陷被漏掉。团队把速度指标当作成功，实际只是减少了审查覆盖。

**Why it happens:**
时间易测且适合展示；遗漏率、边界召回和错误权威需要预置缺陷与专家金标准。**风险推断：** 这是产品目标层面的致命失败，不能用生成速度或复用率补偿。

**How to avoid:**
将缺陷遗漏率和错误权威率设为硬护栏：审查时间只有在遗漏率不高于完整 Diff 基线、关键边界召回达到约定目标、错误权威为 0 时才算收益。按节点/关系/管线、网络/生命周期/资产类别分层报告；Treatment 必须允许查看完整 Diff 和全部证据。

**Warning signs:**

- 仪表盘主指标只有 review minutes saved / reuse rate。
- 边界精确率提高，但召回率下降。
- “被折叠为权威但专家认为应审”的样本被算作普通误报。
- reviewer 为追求速度不展开证据或完整 Diff。

**Recovery strategy:**
判定 MVP 当前版本失败并停止权威折叠；公开错误权威样本，回溯其根因属于模型、上下文、证据还是 UI；扩大默认审查闭包并重跑盲测，直到护栏恢复，再讨论节省时间。

**Phase to address:** 阶段 5 作为发布判定；阶段 1—4 必须持续采集分层错误数据。

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| 用资产路径/符号名作为 ID | 无需 ID 注册表 | 重命名导致权威丢失或错误继承 | 永不接受 |
| 只给节点存 authority | schema 简单 | 新连接与管线缺陷逃逸审查 | 永不接受 |
| 只记录 `exit_code: 0` | 编排快速 | 无法证明运行了什么、在哪个上下文运行 | 永不接受 |
| 仅做 Editor Development 构建 | 迭代快 | Editor-only 依赖与运行时失败被隐藏 | 仅早期本地反馈；不得用于晋升 |
| 不做通用 Blueprint 自动写入 | 显著降低首版风险 | 部分任务需人工资产操作 | MVP 可接受，且应明确限制 |
| 暂不做跨版本迁移 | 保持可复现 | 无法复用到其他 UE/Lyra 版本 | MVP 正确取舍 |
| 用布尔参数合并网络/生命周期不同实现 | 节点数少 | 语义边界模糊，测试矩阵爆炸 | 仅差异纯配置且契约证明等价时 |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Enhanced Input → Input Tag | 只验证 Input Action 存在 | 验证 Mapping Context 已激活、Trigger/Modifier、优先级及实际 tag 路由 |
| Input Tag → Ability Set | 看到相同 tag 就认为 Ability 会激活 | 验证 Ability Set 授予来源、Pawn 初始化时机、Ability 激活策略和目标 Experience |
| Ability → Gameplay Effect | 只验证 Effect 资产引用 | 验证 cost/active effect 的持续类型、modifier、应用/移除、失败与预测语义 |
| Attribute → 网络复制 | 只在服务端或单机观察数值 | 固定 ASC owner/avatar、复制/预测上下文，并测试接受、拒绝、取消和协调 |
| Asset Registry | 扫描未完成就声明依赖闭包完整 | 等待 files loaded，检查保存/重存状态，并对点名依赖运行验证 |
| UE Editor 插件 → 外部 core | 让插件决定权威或写回 | 插件仅返回版本化事实；外部 core 负责边界、审查和原子写回 |

## Performance Traps

首个 MVP 的规模很小，主要风险不是海量图性能，而是为了“全项目扫描”消耗时间并扩大错误面。

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| 每次启动全量加载/扫描全部资产 | Editor 启动与 run 时间主导审查时间 | 只 probe 人工策展节点与必要依赖；复用 Asset Registry 索引 | 首个真实 Lyra 运行即可能拖慢实验 |
| 每个节点单独启动 Editor/UBT | 大量重复启动和相同日志 | 一次批量 probe、按验证层分组执行 | 数十个节点时已不可接受 |
| 对每个节点复制完整 evidence 日志 | authority 文件膨胀、diff 噪声 | 内容寻址 evidence，assertion 只引用 hash/URI | 第二轮写回开始即影响审查 |
| 无界自动重试构建/测试 | 时间不可预测，失败因果被覆盖 | 固定重试预算，每次尝试独立记录 | 首次不稳定测试即可污染证据 |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Agent 对整个 UE 项目有写权限 | 资产、插件、配置和图谱被越界修改 | 目录/文件/行数/轮次预算；隔离 worktree；默认预览 |
| 探针插件可晋升 authority | 事实采集者可批准自身输出 | 插件只读/白名单 mutation；人工 reviewer + 外部原子写回 |
| 接受未校验的 Patch 路径或资产 locator | 路径逃逸、修改非目标包 | 规范化绝对路径并校验工作区/允许目录；locator 白名单 |
| 覆盖失败日志只保留成功重试 | 审计链被美化，隐藏不稳定性 | run append-only；所有尝试、命令、退出码和摘要不可变保留 |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| 用单一绿色“权威”徽章覆盖节点/边/管线 | reviewer 误以为整条路径免审 | 分层显示 subject、context、证据与失效原因 |
| 默认隐藏完整 Diff | 时间下降来自信息缺失 | 默认聚焦边界，但一键展开完整 Diff 和资产差异 |
| 只显示复用率，不显示错误权威/未知项 | 激励团队追求虚假高复用 | 同屏显示未知、Suspect、边界召回和护栏 |
| 失效传播无解释 | reviewer 无法判断为何审查范围扩大 | 展示触发源与 entity → relation → pipeline 传播路径 |
| 把“测试通过”当作最终结论 | 用户不知道 Target、场景和测试数 | 展示命令、上下文、执行/跳过数量和报告链接 |

## "Looks Done But Isn't" Checklist

- [ ] **固定基线：** 不只是 `UE 5.7`；核对 BuildId/Changelist、Lyra 身份、插件、Target、Configuration、Experience 与网络拓扑。
- [ ] **行为契约：** 覆盖输入开始/保持/释放、体力前置与持续消耗、耗尽、取消、Pawn 生命周期、服务端接受/拒绝与协调。
- [ ] **最小图谱：** 节点、关系、完整有序管线分别有 ID、locator、fingerprint、context、evidence 和 authority assertion。
- [ ] **稳定 ID：** 路径/名称/hash 不作为 identity；资产移动有 lineage/decision，Redirector 已检查。
- [ ] **资产闭包：** Asset Registry 已完成扫描；Blueprint/Data Asset/软引用/标签配置已保存并验证依赖。
- [ ] **模块边界：** 探针是 Editor-only；运行时冲刺逻辑无 Editor 模块依赖；约定非 Editor Target 通过。
- [ ] **构建证据：** UBT 构建记录了 UHT 和编译阶段，不用单独 UHT 成功替代完整构建。
- [ ] **测试证据：** 目标测试发现数非零，实际执行集合、上下文、跳过项、结构化报告和 hash 完整。
- [ ] **网络证据：** 不只理想本机 PIE；至少覆盖约定服务端拓扑和受控延迟/丢包/拒绝路径。
- [ ] **Patch 事务：** 文本、二进制包、新增/删除文件、Redirector、authority 写回均在 preimage 与回滚清单内。
- [ ] **失效传播：** 节点/context/evidence 改变会确定性传播到关系和管线，而非只改局部状态。
- [ ] **实验护栏：** 审查时间下降同时满足遗漏率不升、错误权威为 0；Treatment 可查看完整 Diff。

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| 代码相同误判语义相同 | HIGH | 管线降级 → 重建行为契约/边 → 补网络与失败测试 → 重审 |
| 节点权威传递 | HIGH | 停止晋升 → 全量降级推导出的边/管线 → 从可信快照重算 |
| 稳定 ID 漂移 | MEDIUM/HIGH | 冻结写回 → 人工确认身份迁移 → 合并重复节点 → 重算引用 |
| 版本/网络上下文失配 | HIGH | 实验作废 → 恢复或新建 baseline → 全链重验证，不继承权威 |
| 资产依赖遗漏 | MEDIUM/HIGH | 干净进程复现 → 补资产/软引用 → Data Validation/Cook/运行验证 |
| Editor/runtime 混淆 | MEDIUM | 拆模块与依赖 → 非 Editor Target/Cook → 重发 evidence |
| 证据误读 | MEDIUM | 撤销晋升 → 清理旧产物 → 固定命令重跑 → 校验报告集合 |
| Patch/回滚不完整 | HIGH | 禁止写入 → 恢复整个隔离环境 → Editor 修复资产 → 撤销写回 |
| 权威失效不传播 | HIGH | 重建反向依赖 → 保守闭包失效 → 自底向上重验证 |
| 评测污染 | MEDIUM | 标记排除 → 重新冻结/配对/平衡顺序 → 只报告有效运行 |
| 时间下降但缺陷上升 | CRITICAL | 判定 MVP 失败 → 停止折叠 → 根因回溯 → 扩边界并重跑盲测 |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 代码相同误判语义相同 | 阶段 0 / 1 / 2 | 代码不变但网络/生命周期变化的夹具必须进入待审范围 |
| 节点权威传递 | 阶段 1 | 新增任一边时，管线不得自动 Authoritative |
| 稳定 ID 漂移 | 阶段 1 / 2 | 资产重命名夹具保持同 ID、更新 locator，并产生审计 decision |
| 版本/网络上下文失配 | 阶段 0 / 2 / 4 | 任一关键 lock 字段变化使依赖 assertion 变 Suspect |
| Blueprint/资产依赖遗漏 | 阶段 1 / 2 / 3 | 冷启动、依赖验证和约定 Cook/运行场景均成功 |
| Editor-only/runtime 边界 | 阶段 0 / 2 / 3 | Runtime 无 Editor 依赖；固定非 Editor Target 构建通过 |
| UHT/UBT/Test 证据误读 | 阶段 2 / 4 | 空测试、错 Context、缺报告、仅 UHT 均阻止晋升 |
| Patch/回滚不完整 | 阶段 3 / 4 | 失败注入后工作树、包摘要与 authority 摘要恢复 preimage |
| 权威失效不传播 | 阶段 1 / 4 | 修改叶节点/上下文/测试策略后反向闭包全部 Suspect |
| 评测基线污染 | 阶段 5 | 任务、顺序、快照、计时和排除规则在实验前冻结 |
| 时间下降但缺陷上升 | 阶段 5 | 遗漏率不高于基线、错误权威为 0，否则发布失败 |

## Sources

所有 UE 技术事实仅使用 Epic Games 一手资料；访问日期均为 2026-07-12。

- **[S1] Epic Games — [Enhanced Input](https://dev.epicgames.com/documentation/unreal-engine/enhanced-input-in-unreal-engine)**：Input Action、Mapping Context、Trigger、Modifier 与运行时上下文切换。
- **[S2] Epic Games — [Abilities in Lyra](https://dev.epicgames.com/documentation/unreal-engine/abilities-in-lyra-in-unreal-engine?lang=en-US)**：Ability Set、授予来源、Input Tag、Activation Policy/Group、Ability 生命周期。
- **[S3] Epic Games — [Gameplay Ability](https://dev.epicgames.com/documentation/unreal-engine/using-gameplay-abilities-in-unreal-engine?lang=en-US)**：Ability 成本、异步执行、复制与 Gameplay Net Execution Policy。
- **[S4] Epic Games — [Gameplay Ability System Overview](https://dev.epicgames.com/documentation/unreal-engine/understanding-the-unreal-engine-gameplay-ability-system)**：ASC、Ability、Attribute、Effect、复制、预测与服务端拒绝协调。
- **[S5] Epic Games — [Asset Registry](https://dev.epicgames.com/documentation/en-us/unreal-engine/asset-registry-in-unreal-engine)**：未加载资产信息、异步扫描、重命名事件与可搜索标签限制。
- **[S6] Epic Games — [Asset Redirectors](https://dev.epicgames.com/documentation/unreal-engine/asset-redirectors-in-unreal-engine)**：资产移动/重命名产生 Redirector 及 Fixup。
- **[S7] Epic Games — [Working with Assets](https://dev.epicgames.com/documentation/en-us/unreal-engine/working-with-assets-in-unreal-engine)**：对象/包路径、Blueprint 生成类对象和资产引用管理。
- **[S8] Epic Games — [UBT Targets](https://dev.epicgames.com/documentation/unreal-engine/unreal-engine-build-tool-target-reference?lang=en-US)**：Game、Client、Server、Editor 等 Target 的不同边界。
- **[S9] Epic Games — [Testing and Debugging Networked Games](https://dev.epicgames.com/documentation/en-us/unreal-engine/testing-and-debugging-networked-games-in-unreal-engine)**：PIE、多实例、独立进程与网络测试限制。
- **[S10] Epic Games — [Referencing Assets](https://dev.epicgames.com/documentation/unreal-engine/referencing-assets-in-unreal-engine)**：硬引用、软引用及其加载差异。
- **[S11] Epic Games — [Data Validation](https://dev.epicgames.com/documentation/unreal-engine/data-validation-in-unreal-engine)**：资产/依赖验证、命令行运行和验证器边界。
- **[S12] Epic Games — [UE Diff Tool](https://dev.epicgames.com/documentation/unreal-engine/ue-diff-tool-in-unreal-engine)**：Blueprint/相邻资产差异及支持范围。
- **[S13] Epic Games — [Unreal Engine Modules](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-modules)**：Runtime 与 Editor 模块的职责边界。
- **[S14] Epic Games — [Unreal Header Tool](https://dev.epicgames.com/documentation/unreal-engine/unreal-header-tool-for-unreal-engine?lang=en-US)**：UHT 解析/代码生成，以及 UBT 随后调用编译器的两阶段构建。
- **[S15] Epic Games — [Unreal Build Tool](https://dev.epicgames.com/documentation/unreal-engine/unreal-build-tool-in-unreal-engine?lang=en-US)**：UBT、模块 `.Build.cs` 与多配置构建。
- **[S16] Epic Games — [Automation Test Framework](https://dev.epicgames.com/documentation/unreal-engine/automation-test-framework-in-unreal-engine)**：测试类型、状态隔离原则与适用边界。
- **[S17] Epic Games — [Run Automation Tests](https://dev.epicgames.com/documentation/unreal-engine/run-automation-tests-in-unreal-engine)**：命令行过滤、Editor/Client 实例与结构化报告导出。
- **[S18] Epic Games — [Network Emulation](https://dev.epicgames.com/documentation/unreal-engine/using-network-emulation-in-unreal-engine?lang=en-US)**：延迟、丢包模拟及理想本地网络无法暴露的问题。
- **[S19] Epic Games — [Lyra Sample Game](https://dev.epicgames.com/documentation/unreal-engine/lyra-sample-game-in-unreal-engine?lang=en-US)**：Lyra 是随 UE5 更新的模块化学习样本，Experience 加载 Game Feature 插件。

---
*Pitfalls research for: UE-ITPS 首个体力冲刺 MVP*  
*Researched: 2026-07-12*
