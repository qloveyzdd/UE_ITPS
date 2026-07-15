---
mapped_at: 2026-07-15
scope: UE-5.6.1-and-LyraStarterGame-startup-runtime
status: static-main-chain-mapped-runtime-l0-observation-not-fully-retained
---

# Lyra 启动、Experience 与玩家初始化管线

## 证据口径

本文只描述 UE 5.6.1 当前基线，使用以下标记：

| 标记 | 含义 |
|---|---|
| 配置事实 | INI、Target、Plugin Descriptor 的直接内容 |
| 源码事实 | 当前 Engine/Lyra 修订中明确存在的调用和条件 |
| Registry 事实 | UE 5.6.1 实时 Asset Registry 或对象反射结果 |
| 历史运行观察 | 2026-07-14 L0 运行时曾从完整日志中观察，但原始日志已被轮转清理 |
| 待运行验证 | 源码允许或预期发生，但当前没有可审计运行证据 |

“源码中存在调用链”只能证明静态机制；只有指定 Map、Experience、网络模式和构建上下文中的日志或测试，才能证明该次管线真正执行。

## 总时间线：PIE Standalone/Server 侧

```text
Engine Init
→ 创建 ULyraAssetManager
→ Primary Asset 扫描 + Gameplay Cue + LyraGameData
→ 按配置创建 B_LyraGameInstance_C
→ CommonGame/Lyra GameInstance Init
→ 复制 Editor World 为 PIE World
→ 按配置/WorldSettings 创建 B_LyraGameMode_C
→ InitializeActorsForPlay
   → ALyraGameMode::InitGame（预约下一 Tick 选择 Experience）
   → GameMode PreInitializeComponents 创建 ALyraGameState
   → InitGameState 注册 GameMode 的 Experience 回调
→ LocalPlayer::SpawnPlayActor
   → Login 创建 PlayerController
   → PlayerController 创建 PlayerState
   → PlayerState 注册 Experience 回调
   → PostLogin 因 Experience 未加载而暂不生成 Pawn
→ UWorld::BeginPlay
→ 下一 Tick 选择 Experience
→ 加载 Experience/ActionSet Bundle
→ 激活声明的 Game Feature Plugin
→ 执行 Experience/ActionSet Action
→ 广播 Experience Loaded
   → 高优先级回调
   → 普通回调：PlayerState 先执行，GameMode 后执行
   → 低优先级回调
→ PlayerState 设置 PawnData 并授予 AbilitySet
→ GameMode RestartPlayer
→ 延迟生成 Pawn，先写 PawnData，再 FinishSpawning
→ Possess 设置 Controller/PlayerState
→ 本地 PawnClientRestart 创建 InputComponent
→ PawnExtension/Hero 协同推进 InitState
→ PlayerState ASC: Owner=PlayerState, Avatar=Pawn
→ Enhanced Input 绑定完成
→ 每帧 PostProcessInput 处理 Ability 输入
```

这是“已有玩家早于 Experience”的首登路径。若玩家在 Experience 已加载后加入，`CallOrRegister` 会立即执行 PlayerState 回调，`HandleStartingNewPlayer` 也会直接进入父类生成流程；不能把两种路径合并成完全相同的事件序列。

## P0：Engine 与全局资源启动

### 配置入口

配置事实来自：

- `LyraStarterGame/Config/DefaultEngine.ini`
- `LyraStarterGame/Config/DefaultGame.ini`

关键绑定：

```text
GameEngine                 → ULyraGameEngine
AssetManagerClassName      → ULyraAssetManager
GameInstanceClass          → B_LyraGameInstance_C
GlobalDefaultGameMode      → B_LyraGameMode_C
LocalPlayerClassName       → ULyraLocalPlayer
GameFeaturesManagerClass   → ULyraGameFeaturePolicy
```

Registry 事实确认两个 Blueprint 启动类均直接继承对应的 Lyra 原生类，结果见 `.planning/evidence/lyra-5.6.1/asset-registry-slice.json`。

### AssetManager

源码事实：`UEngine::InitializeObjectReferences` 创建配置的 AssetManager 后调用 `StartInitialLoading`。Lyra 覆盖执行：

1. `Super::StartInitialLoading` 完成 Primary Asset 初始扫描。
2. `InitializeGameplayCueManager` 加载 Always Loaded Gameplay Cues。
3. `GetGameData` 加载 `/Game/DefaultGameData.DefaultGameData`。
4. `DoAllStartupJobs` 按权重执行并报告进度。

`LoadGameDataOfClass` 对缺失 GameData 使用 Fatal。对最小项目而言，AssetManager、GameData 配置和 Primary Asset 扫描是一条不可拆开的启动连接，而不是三个独立可选节点。

### GameInstance

`B_LyraGameInstance_C` 的原生链是：

```text
UGameInstance
→ UCommonGameInstance
→ ULyraGameInstance
→ B_LyraGameInstance_C
```

`UCommonGameInstance::Init` 在 GameInstance Subsystem 已创建后连接 CommonUser、CommonSession 与平台 Trait；`ULyraGameInstance::Init` 再注册四级 InitState，并连接 Session Travel 事件。

```text
InitState.Spawned
→ InitState.DataAvailable
→ InitState.DataInitialized
→ InitState.GameplayReady
```

这四个状态由 GameInstance 级 `UGameFrameworkComponentManager` 管理。它们不是 Pawn 类的私有状态，因此 GameInstance 初始化失败会让整个模块化 Pawn 初始化机制失去注册表。

## P1：PIE World、GameMode 与 GameState

### PIE 与 Standalone 的分叉

| 路径 | GameInstance 创建者 | 初始 World |
|---|---|---|
| Standalone | `UGameEngine::Init` | 临时 Game World，随后 LoadMap |
| PIE | `UEditorEngine::CreateInnerProcessPIEGameInstance` | 复制 Editor World，或按 Override URL 加载 |

两条路径都读取 `UGameMapsSettings::GameInstanceClass`。当前历史 L0 观察走的是 PIE 路径，不能自动证明 Standalone、Client PIE 或 Dedicated Server 的完全等价行为。

### PIE 的 Engine 顺序

源码事实：`UGameInstance::StartPlayInEditorGameInstance` 在非纯 Client PIE 中按以下顺序运行：

1. `PlayWorld->SetGameMode(URL)`。
2. 刷新 Always Loaded Level。
3. 创建 AI System。
4. `PlayWorld->InitializeActorsForPlay`。
5. `LocalPlayer->SpawnPlayActor`。
6. `PlayWorld->BeginPlay`。

`UWorld::SetGameMode` 只在非 Client 且尚无 AuthorityGameMode 时创建 GameMode。`UGameInstance::CreateGameModeForURL` 的实现顺序是：WorldSettings 默认类 → URL `GAME=` → Map Prefix → Global Default → 原始 `AGameModeBase` 回退，然后生成 transient GameMode。

`B_LyraGameMode_C` 的原生构造函数把核心类型固定为：

```text
GameState      → ALyraGameState
PlayerController → ALyraPlayerController
PlayerState    → ALyraPlayerState
DefaultPawn    → ALyraCharacter（可被 PawnData 覆盖）
HUD            → ALyraHUD
GameSession    → ALyraGameSession
```

GameMode `PreInitializeComponents` 创建 GameState。`ALyraGameState` 构造 ExperienceManager 和独立的全局 ASC；PostInitializeComponents 把该 ASC 的 Owner/Avatar 都设为 GameState。

## P2：Experience 选择与加载

### 选择

`ALyraGameMode::InitGame` 不立即决定 Experience，而是 `SetTimerForNextTick`。当前实际实现的优先级是：

```text
URL ?Experience=
→ PIE DeveloperSettings override
→ Command Line Experience=
→ ALyraWorldSettings DefaultGameplayExperience
→ Dedicated Server 登录/托管流程
→ B_LyraDefaultExperience
```

源码注释中的 Matchmaking assignment 没有对应读取逻辑，只能视为扩展意图。

### 加载状态

`SetCurrentExperience` 先把 Primary Asset 路径同步解析为 Experience Blueprint Class，再使用 Class Default Object 作为当前定义；随后开始 Bundle 与插件加载。

```text
Unloaded
→ Loading
→ LoadingGameFeatures（可选）
→ LoadingChaosTestingDelay（测试专用，可选）
→ ExecutingActions
→ Loaded
```

加载集合包括 Experience 本身和所有 ActionSet。Bundle 至少包含 `Equipped`，并根据 NetMode 加载 Client/Server Bundle；Editor 同时加载两侧 Bundle。

资源完成后，Experience 与 ActionSet 声明的插件名被解析为 URL 并去重。插件全部回调后，系统按“Experience Actions → 每个 ActionSet Actions”执行：

```text
OnGameFeatureRegistering
→ OnGameFeatureLoading
→ OnGameFeatureActivating(WorldContext)
```

最后才设置 `Loaded` 并广播高、普通、低优先级回调。

### 客户端语义

`CurrentExperience` 是 GameState Component 的复制属性。客户端收到 OnRep 后从 `Unloaded` 开始执行自己的资源、插件和 Action 加载。服务端的 Loaded 状态没有复制给客户端，所以“服务端 Experience 已完成”与“客户端 Experience 已完成”必须建成两个上下文相关的管线事实。

### 加载屏

CommonLoadingScreen 每帧检查 World、GameState、GameState Components、外部 Processor、Local PlayerController 及其组件。ExperienceManager 只要尚未 `Loaded` 就返回 `Experience still loading`。因此下列连接是显式的：

```text
Experience LoadState
→ ILoadingProcessInterface
→ CommonLoadingScreen
→ 是否移除加载屏
```

## P3：玩家登录、等待与 Experience 回调顺序

### Experience 之前的玩家对象

`UWorld::SpawnPlayActor` 调用 GameMode Login；Login 生成 PlayerController。PlayerController `PostInitializeComponents` 在非 Client 创建 PlayerState；PlayerState 立即创建玩家 ASC、HealthSet、CombatSet，并把初始 ASC ActorInfo 设为 Owner=PlayerState、Avatar=当前 Pawn（此时通常为空）。

PostLogin 会执行 HUD、Mute、Streaming 等通用初始化，但 Lyra 覆盖 `HandleStartingNewPlayer`：Experience 未加载时直接返回。因此首登玩家的稳定等待形态是：

```text
PlayerController ✓
PlayerState ✓
PlayerState ASC ✓（Avatar 暂空）
Pawn ✗
```

### 为什么 PlayerState 先于 GameMode 回调

1. GameMode 在 `InitGameState` 较早注册普通优先级回调。
2. PlayerState 在登录阶段较晚注册同一个普通优先级回调。
3. UE 5.6 `TMulticastDelegateBase::Broadcast` 从调用列表末尾向前执行。

所以首登正常路径中，后注册的 PlayerState 先执行：

```text
PlayerState::OnExperienceLoaded
→ GameMode::GetPawnDataForController
→ PlayerState::SetPawnData
→ Authority GiveToAbilitySystem
→ LyraAbilitiesReady 扩展事件
→ GameMode::OnExperienceLoaded
→ RestartPlayer
```

该顺序依赖“注册时机 + 当前委托实现”，不是 API 明文承诺的业务排序。它应该被记录为一条可失效的连接权威。

## P4：Pawn 生成、Possess 与 ASC Avatar

### PawnData 选择

`GetPawnDataForController` 的优先级：

```text
PlayerState.PawnData
→ CurrentExperience.DefaultPawnData
→ ULyraAssetManager.DefaultPawnData
```

最后一层只在 Experience 已加载但未指定 DefaultPawnData 时使用；Experience 未加载会返回空。

### 延迟生成

`ALyraGameMode::SpawnDefaultPawnAtTransform` 使用 deferred spawn：

1. 依据 PawnData 的 PawnClass 生成未完成构造的 Pawn。
2. 把 PawnData 写入 `ULyraPawnExtensionComponent`。
3. `FinishSpawning`。

这保证 Pawn 组件开始注册、BeginPlay 和 InitState 检查前已经能看到 PawnData。

World 此时通常已经 BeginPlay，所以 FinishSpawning 会让 Pawn/组件开始运行；但 Controller 尚未 Possess，PawnExtension/Hero 会停在前置条件处。随后 `FinishRestartPlayer` 调用 Possess：

```text
APawn::PossessedBy
→ 设置 Owner、Controller、PlayerState
→ ALyraCharacter 通知 PawnExtension Controller 已变化
→ PlayerController::SetPawn
→ ClientRestart / PawnClientRestart
→ 本地创建 InputComponent
→ ALyraCharacter::SetupPlayerInputComponent
→ PawnExtension 再次检查 InitState
```

### ASC 所有权

| ASC | Owner | Avatar | 生命周期 |
|---|---|---|---|
| GameState ASC | GameState | GameState | World/GameState |
| PlayerState ASC（生成前） | PlayerState | 空或旧 Pawn | PlayerState |
| PlayerState ASC（Pawn Ready） | PlayerState | 当前 Pawn | 跨死亡保留 Owner，Avatar 可替换 |

PawnExtension 不创建玩家 ASC，只保存并协调 PlayerState ASC 的引用。切换 Avatar 时会清除旧 Pawn 的能力输入、Gameplay Cue，并取消除 `SurvivesDeath` 外的 Ability。

### InitState 屏障

| Feature | 转换 | 条件 |
|---|---|---|
| PawnExtension | 无 → Spawned | 有效 Pawn，BeginPlay |
| PawnExtension | Spawned → DataAvailable | PawnData；Authority/Local 还需 Controller |
| PawnExtension | DataAvailable → DataInitialized | 同 Pawn 的全部注册 Feature 至少 DataAvailable |
| PawnExtension | DataInitialized → GameplayReady | 无额外条件 |
| Hero | 无 → Spawned | 有效 Pawn，BeginPlay |
| Hero | Spawned → DataAvailable | PlayerState；非 SimulatedProxy 需 Controller 与其 PlayerState 正确配对；本地非 Bot 还需 InputComponent 和 LocalPlayer |
| Hero | DataAvailable → DataInitialized | PawnExtension 已到 DataInitialized |
| Hero | DataInitialized → GameplayReady | 当前无额外条件 |

Hero 在进入 DataInitialized 时完成三件核心工作：

1. 把 PlayerState ASC 初始化为 Owner=PlayerState、Avatar=Pawn。
2. 对本地玩家初始化 Enhanced Input。
3. 把 Camera Mode 选择委托连接到 PawnData。

PawnExtension 监听所有 Feature 的状态变化，Hero 监听 PawnExtension；双方通过重新执行 `ContinueInitStateChain` 消除初始化事件先后不确定性。

## P5：输入到 Ability

```text
PawnData.InputConfig
→ ULyraHeroComponent::InitializePlayerInput
→ Enhanced Input Mapping Context
→ ULyraInputComponent::BindAbilityActions
→ Input Action Triggered/Completed
→ Input Gameplay Tag
→ ASC AbilityInputTagPressed/Released
→ Pressed/Held/Released Spec Handle 缓存
→ PlayerController::PostProcessInput
→ ASC::ProcessAbilityInput
→ ActivationPolicy 筛选
→ TryActivateAbility / InputPressed / InputReleased
```

AbilitySet 在 Authority 授予 Ability 时，把配置的 InputTag 写入 AbilitySpec 动态源标签。输入侧按相同 Tag 查找 Spec，因此 Input Action 与 Ability Class 不直接耦合。

当前 L0 没有足够日志证明某个真实 Input Action 已沿这条链激活 Ability；这是 L1 的必验连接。

## P6：失败与卸载路径

| 路径 | 当前源码行为 | 权威风险 |
|---|---|---|
| GameData 缺失 | Fatal | 明确失败，可作为启动硬门槛 |
| Experience ID 无效 | 回退默认；最终仍无效则加载屏永久保持 | 需验证错误可观测性 |
| Experience Bundle 取消 | 仍调用完成处理 | 取消与成功未显式区分 |
| Game Feature 激活失败 | 回调 `Result` 被忽略，只递减计数 | 可能继续进入 Loaded |
| 部分加载时 EndPlay | 源码标记 TODO | 清理语义未闭合 |
| Action 异步停用 | 记录“不完整支持”错误 | 不能把卸载管线标为完整权威 |
| 卸载顺序 | 非 FILO，源码标记 TODO | 依赖反向清理未被保证 |
| PlayerState `OnRep_PawnData` | 空实现 | 客户端依靠 ASC/PawnData 复制与其他事件推进 |

## P7：Frontend → Session → Travel → 新 Experience

前端 UI 选择的是 `ULyraUserFacingExperienceDefinition`，不是单一 Map。该 Data Asset 把 `MapID` 和 `ExperienceID` 写入 HostRequest；其中 Experience 被编码为 URL 的 `?Experience=`。

```text
Frontend Experience Loaded
→ Frontend Control Flow / W_LyraFrontEnd
→ 选择 UserFacingExperience
→ CreateHostingRequest
→ HostSession / QuickPlay / JoinSession
→ ServerTravel / ClientTravel
→ OldWorld EndPlay
→ NewWorld + 同一 GameInstance
→ SetGameMode(URL)
→ SpawnPlayActor
→ New GameMode 下一 Tick 从 URL 选择 Experience
→ 新 Experience 加载
```

Session success 回调早于 Travel 完成，因此这条管线至少需要分别验证 Session、Travel、World 和 Experience 四个阶段。Hard Travel 下 GameInstance、Subsystem、LocalPlayer 与 UI Policy 跨 World 保留，PlayerController、PlayerState、Pawn 和 ASC 则重建。

详细证据、Host/Join 分叉、Hard/Seamless 对象表和返回前端链见 `.planning/codebase/TRAVEL.md`。

## 当前证据矩阵

### 已由配置、源码或 Registry 证明

- 启动配置使用 `B_LyraGameInstance_C` 与 `B_LyraGameMode_C`，且两者直接继承 Lyra 原生类。
- AssetManager、GameData、GameInstance、World、GameMode、GameState 的静态启动调用关系。
- Experience 选择、加载状态、Game Feature Action 和高/普通/低回调实现。
- 首登 PlayerController/PlayerState 早于 Experience、Pawn 受 Experience 门控的源码路径。
- PlayerState 回调先于 GameMode 回调的当前 UE 5.6 委托顺序。
- PawnData、AbilitySet、PawnExtension、Hero、ASC Owner/Avatar 与输入处理的静态连接。
- 加载屏与 Experience LoadState 的连接。
- UserFacingExperience 的 MapID/ExperienceID 到 HostRequest/URL 的静态映射。
- OSSv1 Host/Join success 回调到 ServerTravel/ClientTravel 的调用顺序。
- Hard Travel 中 GameInstance/LocalPlayer 保留以及 World/Player 对象重建的 Engine 调用顺序。

### 2026-07-14 历史运行中曾观察

- Engine 报告 5.6.1。
- PIE 复制 `L_DefaultEditorOverview`。
- 运行 GameMode 为 `B_LyraGameMode_C`。
- CommonGame 添加 `W_OverallUILayout`。
- `B_LyraDefaultExperience` 被识别并进入 Start/OnExperienceLoadComplete。
- 随后以 URL `?Experience=B_LyraFrontEnd_Experience` 进入前端 Map，并加载前端 Experience。
- 五个项目 Game Feature 在 Editor 启动期进入 Registered；该日志没有证明 `ShooterCore` Active。

原始日志 `LyraStarterGame-backup-2026.07.14-10.50.15.log` 已于 2026-07-15 被 UE Commandlet 日志轮转清理，未提前复制到受控证据目录。上述内容仍是已提交文档中的历史观察，但不能从当前仓库独立复核，因此按未来权威模型应降级为 `Observed/Suspect`，直到重跑并保存原始日志及摘要哈希。

### 尚未运行证明

- Experience `ExecutingActions → Loaded` 的显式日志点。
- PlayerState 先授予 AbilitySet、GameMode 后生成 Pawn 的真实时序。
- PawnExtension/Hero 在任一 Shooter Experience 中到达 GameplayReady。
- Client、Listen Server、Dedicated Server 各自的 Experience 和 InitState 时序。
- 一个真实 InputTag 激活一个 Ability。
- Shooter HUD 注入。
- Game Feature 激活失败、Experience 部分加载、异步停用等失败路径。
- Frontend Host 的实际 Hard/Seamless 模式与完整旅行时序。
- RootLayout 复用时前端 Widget 栈是否正确清理。

## 对 UE-ITPS 数据模型的直接启示

该管线至少需要区分以下权威对象：

```text
节点权威：B_LyraGameInstance_C、ALyraGameMode、PawnData、AbilitySet、ASC
连接权威：配置→类、Experience→Plugin、PlayerState→ASC、ASC→Pawn Avatar
管线权威：登录等待→Experience→AbilitySet→Pawn→InitState→Input→Ability
上下文：UE 修订、Lyra 指纹、PIE/Standalone、NetMode、Map、Experience、插件状态
证据：源码位置、Registry 结果、原始日志、测试结果、证据文件哈希
```

特别需要记录两类非显式依赖：

- “后注册先执行”的委托顺序依赖。
- “Feature 全部到达 DataAvailable”形成的集合屏障依赖。

它们都不是普通函数调用图能够完整表达的关系，也是未来权威边界计算必须覆盖的重点。

## 下一轮研究问题

1. 按 `.planning/codebase/RUNTIME-EVIDENCE.md` 重跑并留存 L0，恢复原始运行证据。
2. 为 L1 设计最小临时日志或 Trace 点，覆盖 Travel、Experience Loaded、回调先后、PawnData、ASC Owner/Avatar、InitState、InputTag 和 HUD 注入。
3. 分别建立 Standalone、Listen Server、Dedicated Server、Client 的时序差异表，避免用单机 PIE 推断网络权威。
4. 研究 Experience/Game Feature 失败与卸载路径是否需要在未来参考实现中加固，而不是直接把 Lyra 样例行为定义为标准答案。
