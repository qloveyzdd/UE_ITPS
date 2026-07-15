---
mapped_at: 2026-07-15
scope: LyraStarterGame
status: startup-ownership-and-lifecycle-statically-mapped
---

# Lyra 顶层架构与启动主链

## 架构总览

Lyra 不是单一 Gameplay Module，而是“稳定项目壳 + Experience 配置 + 按需 Game Feature + 模块化 Pawn 初始化”的组合架构。

```text
UEngine / AssetManager / GameInstance
        ↓
UserFacingExperience / Default Map / URL / World Settings
        ├─ UserFacingExperience 绑定 MapID 与 ExperienceID
        └─ URL 通过 Experience 参数覆盖默认选择
        ↓
ALyraGameMode 选择 Experience
        ↓
ULyraExperienceManagerComponent
        ├─ 加载 Experience 与 ActionSet 资源包
        ├─ 激活 Experience 声明的 Game Feature Plugins
        └─ 执行 Experience / ActionSet 的 GameFeatureAction
        ↓
Experience Loaded
        ├─ 允许 GameMode 生成玩家 Pawn
        ├─ PlayerState 接收 PawnData 并授予 AbilitySet
        └─ PawnExtension / Hero 推进 InitState
                  ↓
            GAS + Input + Camera + UI Ready
```

## 1. 配置入口与实际启动类型

`DefaultEngine.ini` 明确配置了以下启动对象：

| 配置项 | 实际类型 |
|---|---|
| `GameEngine` | `/Script/LyraGame.LyraGameEngine` |
| `AssetManagerClassName` | `/Script/LyraGame.LyraAssetManager` |
| `LocalPlayerClassName` | `/Script/LyraGame.LyraLocalPlayer` |
| `GlobalDefaultGameMode` | `/Game/B_LyraGameMode.B_LyraGameMode_C` |
| `GameInstanceClass` | `/Game/B_LyraGameInstance.B_LyraGameInstance_C` |
| `GameDefaultMap` | `/Game/System/FrontEnd/Maps/L_LyraFrontEnd` |
| `EditorStartupMap` | `/Game/System/DefaultEditorMap/L_DefaultEditorOverview` |

实时 Asset Registry 已确认：

- `B_LyraGameInstance_C` 的直接父类和原生父类都是 `/Script/LyraGame.LyraGameInstance`。
- `B_LyraGameMode_C` 的直接父类和原生父类都是 `/Script/LyraGame.LyraGameMode`。

因此，“Lyra 使用 `ULyraGameInstance`/`ALyraGameMode`”只是原生职责层的简称；运行时真正按配置实例化的是它们的 Blueprint 子类。后续计算实现身份或权威上下文时，不能丢掉这一层 Blueprint 类型。

`ULyraGameEngine::Init` 当前只调用父类，是一个已命名但尚无额外行为的扩展点。真正的 Lyra 启动工作首先发生在 `ULyraAssetManager::StartInitialLoading`：执行父类 Primary Asset 扫描、初始化 Gameplay Cue Manager、加载基础 `LyraGameData`，再执行全部启动任务；基础 GameData 加载失败会触发 Fatal，而不是静默回退。

PIE 与 Standalone 使用同一 `GameInstanceClass` 配置，但 Engine 路径不同：Standalone 由 `UGameEngine::Init` 创建 GameInstance 和临时 World；PIE 由 `UEditorEngine::CreateInnerProcessPIEGameInstance` 创建 GameInstance、复制或加载 PIE World，再调用 `InitializeForPlayInEditor`。两条路径都会在 World 绑定后调用 `UGameInstance::Init`，从而创建 GameInstance Subsystem。

## 2. 项目壳

- `LyraGame` 是主运行时模块，入口见 `LyraStarterGame/Source/LyraGame/LyraGameModule.cpp`。
- `LyraEditor` 只在 Editor Target 中加载，入口见 `LyraStarterGame/Source/LyraEditor/LyraEditor.cpp`。
- 项目级稳定能力位于 `LyraStarterGame/Source/LyraGame/`：Experience、Pawn、GAS、输入、UI、团队、装备、库存、设置与在线会话。
- 可替换玩法位于 `LyraStarterGame/Plugins/GameFeatures/`：`ShooterCore`、`ShooterMaps`、`TopDownArena`、`ShooterExplorer`、`ShooterTests`。
- Game Feature 插件均使用 `ExplicitlyLoaded: true`，且初始状态为 `Registered`；是否激活由 Experience 决定，而不是仅由 `.uproject` 中的 Enabled 决定。

## 3. World、GameMode 与 Experience 选择

`ALyraGameMode::InitGame` 在下一帧调用匹配分配逻辑，见 `LyraStarterGame/Source/LyraGame/GameModes/LyraGameMode.cpp`。

源码注释把“Matchmaking assignment”列为最高优先级，但当前 `HandleMatchAssignmentIfNotExpectingOne` 中没有读取匹配分配结果的实现。当前可直接证明的选择顺序是：URL `Experience` 参数、PIE Developer Settings、命令行、World Settings、Dedicated Server 流程、默认 Experience。匹配分配应视为预留设计意图，不应标成当前已实现输入。确定后，`OnMatchAssignmentGiven` 调用 `ULyraExperienceManagerComponent::SetCurrentExperience`。

PIE 的关键 Engine 顺序是：创建 GameMode → `InitializeActorsForPlay` → `ALyraGameMode::InitGame` → GameMode `PreInitializeComponents` 创建 GameState 并执行 `InitGameState` → 创建本地 PlayerController/PlayerState → `UWorld::BeginPlay`。Experience 选择被安排到下一 Tick，因此初始玩家通常先登录并等待 Experience，而不是先有 Experience 再登录。

若 Experience 尚未加载，`HandleStartingNewPlayer` 不启动玩家；Experience 完成后，`OnExperienceLoaded` 才为尚无 Pawn 的控制器执行 `RestartPlayer`。因此 Experience 是玩家生成前的硬门槛。

## 4. Experience 组成

`ULyraExperienceDefinition` 是 `UPrimaryDataAsset`，定义见 `LyraStarterGame/Source/LyraGame/GameModes/LyraExperienceDefinition.h`。它包含：

- `GameFeaturesToEnable`：需要激活的 Game Feature 插件名。
- `DefaultPawnData`：默认 Pawn 组合配置。
- `Actions`：Experience 自身执行的 GameFeatureAction。
- `ActionSets`：复用的额外动作集合。

已存在的关键资产包括：

- `LyraStarterGame/Content/System/FrontEnd/B_LyraFrontEnd_Experience.uasset`
- `LyraStarterGame/Content/System/Experiences/B_LyraDefaultExperience.uasset`
- `LyraStarterGame/Plugins/GameFeatures/ShooterCore/Content/Experiences/B_ShooterGame_Elimination.uasset`
- `LyraStarterGame/Plugins/GameFeatures/ShooterCore/Content/Experiences/B_LyraShooterGame_ControlPoints.uasset`
- `LyraStarterGame/Plugins/GameFeatures/TopDownArena/Content/System/Experiences/B_TopDownArenaExperience.uasset`

这些资产已通过 UE 5.6.1 的实时 Asset Registry 与对象反射完成定向查询，结果保存在 `.planning/evidence/lyra-5.6.1/asset-registry-slice.json`。

### 已确认的 Experience 组合

`B_LyraDefaultExperience`：

- 不激活额外 Game Feature。
- 使用 `/Game/Characters/Heroes/SimplePawnData/SimplePawnData`。
- 执行一个 `GameFeatureAction_AddWidgets`。
- 直接软依赖 `/Game/UI/Hud/W_DefaultHUDLayout`。

`B_LyraFrontEnd_Experience`：

- 不激活额外 Game Feature，也不指定 PawnData。
- 执行 SplitscreenConfig、AddComponents、FrontendPerfSettings 和 AddWidgets。
- 直接软依赖前端音乐组件、前端状态组件与前端性能统计 Widget。

`B_ShooterGame_Elimination` 与 `B_LyraShooterGame_ControlPoints`：

- 都激活 `ShooterCore`。
- 都使用 `/ShooterCore/Game/HeroData_ShooterGame`。
- 都组合 `LAS_ShooterGame_SharedInput`、`LAS_ShooterGame_StandardComponents`、`LAS_ShooterGame_StandardHUD` 与 `EAS_BasicShooterAcolades`。
- 都直接执行 AddAbilities、AddComponents 和 AddWidgets；差异主要位于各自的计分、AbilitySet、Bot、音乐与玩法 UI 软依赖。

### UserFacingExperience 层

`ULyraUserFacingExperienceDefinition` 把前端展示项转成 `MapID + ExperienceID + URL 参数`，定义见 `LyraStarterGame/Source/LyraGame/GameModes/LyraUserFacingExperienceDefinition.*`。

已确认的关键映射：

| UserFacingExperience | Map | Experience | 前端可见 |
|---|---|---|---|
| `DA_ExamplePlaylist` | `/Game/System/DefaultEditorMap/L_DefaultEditorOverview` | `B_LyraDefaultExperience` | 否 |
| `DA_Frontend` | `/Game/System/FrontEnd/Maps/L_LyraFrontEnd` | `B_LyraFrontEnd_Experience` | 否 |
| `DA_ShooterGame_ShooterGym` | `/ShooterCore/Maps/L_ShooterGym` | `B_LyraShooterGame_ControlPoints` | 否 |
| `DA_Convolution_ControlPoint` | `/ShooterMaps/Maps/L_Convolution_Blockout` | `B_LyraShooterGame_ControlPoints` | 是 |
| `DA_Expanse_TDM` | `/ShooterMaps/Maps/L_Expanse` | `B_ShooterGame_Elimination` | 是 |

因此前端选择不是“直接打开某张地图”，而是先选择 UserFacingExperience，再由它创建包含 Map 与 Experience 参数的 Hosting Request。

## 5. Experience 加载、Game Feature 激活与加载屏

`ULyraExperienceManagerComponent::StartExperienceLoad` 位于 `LyraStarterGame/Source/LyraGame/GameModes/LyraExperienceManagerComponent.cpp`：

1. 将 Experience 与 ActionSet 加入 Primary Asset Bundle 加载。
2. 根据客户端、服务器或 Editor 上下文选择对应 Bundle。
3. 资源加载完成后，把 `GameFeaturesToEnable` 转换成插件 URL。
4. 通过 `UGameFeaturesSubsystem::LoadAndActivateGameFeaturePlugin` 激活插件。
5. 插件全部完成后，依次执行 Experience 和 ActionSet 中的 GameFeatureAction。
6. 最终广播高、普通、低三个优先级的 Experience Loaded 回调。

内部状态机是：

```text
Unloaded
→ Loading
→ LoadingGameFeatures（存在插件时）
→ LoadingChaosTestingDelay（仅测试延迟）
→ ExecutingActions
→ Loaded
→ Deactivating
→ Unloaded
```

`CurrentExperience` 由 GameState Component 复制；客户端在 `OnRep_CurrentExperience` 后自行执行资源加载、插件激活和 Action。它不是服务器把“已加载结果”直接复制给客户端。

`ULyraExperienceManagerComponent` 实现 `ILoadingProcessInterface`。CommonLoadingScreen 会遍历 GameState 及其组件；只要 Experience 尚未进入 `Loaded`，该组件就以 `Experience still loading` 为理由保持加载屏。Experience 因此同时是玩家生成门槛和 UI 加载屏门槛。

GameFeatureAction 在 Experience Loaded 广播前执行。这一点对模块化 Pawn 很重要：`UGameFeatureAction_AddComponents` 会先向 `UGameFrameworkComponentManager` 注册组件请求，已有接收者立即补组件，之后生成的 `AModularCharacter` 会在 `PreInitializeComponents` 注册为接收者并获得对应组件。

`ULyraGameFeaturePolicy` 位于 `LyraStarterGame/Source/LyraGame/GameFeatures/LyraGameFeaturePolicy.*`，负责项目级 Game Feature 管理、客户端/服务器加载模式和 Gameplay Cue 路径处理。

2026-07-14 的历史运行观察中，五个项目 Game Feature 插件均进入 `Registered`；默认 Experience 与前端 Experience 随后进入 StartExperienceLoad 和 OnExperienceLoadComplete。原始日志现已被轮转，且当时没有 `ExecutingActions → Loaded` 的显式日志点；因此不能仅凭该记录把完整 Experience 管线或 `ShooterCore Active` 标成运行权威，这些证据必须在后续受控运行中补齐。

## 6. 玩家等待、回调顺序与 Pawn 生成

本地玩家在 PIE 的 Experience 选择前已经走过 `SpawnPlayActor → GameMode::Login → PlayerController → PlayerState → PostLogin`。`ALyraGameMode::HandleStartingNewPlayer` 在 Experience 未加载时不调用父类，因此该 PlayerController 暂时没有 Pawn。

GameMode 在 `InitGameState` 注册普通优先级 Experience 回调；每个 PlayerState 在稍后的 `PostInitializeComponents` 注册同一普通优先级回调。UE 5.6 的多播委托按调用列表反向执行，所以正常首登路径是：

```text
后注册的 PlayerState::OnExperienceLoaded
→ 设置 PlayerState PawnData
→ 权威端授予 AbilitySet
→ 较早注册的 GameMode::OnExperienceLoaded
→ RestartPlayer
→ 生成 Pawn
```

这不是由“普通优先级”名称保证的，而是当前注册时机与 UE 5.6 委托实现共同形成的顺序。未来修改注册位置、委托实现或把回调移到其他优先级，都应使这条连接失效并重新验证。

`ULyraPawnData` 定义见 `LyraStarterGame/Source/LyraGame/Character/LyraPawnData.h`，聚合：

- `PawnClass`
- `AbilitySets`
- `TagRelationshipMapping`
- `InputConfig`
- `DefaultCameraMode`

`ALyraGameMode::GetPawnDataForController` 优先使用 PlayerState 上的 PawnData，其次使用当前 Experience 的 `DefaultPawnData`，最后回退到 Asset Manager 默认 PawnData。

`SpawnDefaultPawnAtTransform` 先延迟构造 Pawn，把 PawnData 写入 `ULyraPawnExtensionComponent`，再完成 Spawn。这保证组件初始化看到的是正确 PawnData。

## 7. PlayerState、ASC 与 Pawn Avatar

- `ALyraPlayerState` 持有长期存在的 `ULyraAbilitySystemComponent` 和 Attribute Sets，见 `LyraStarterGame/Source/LyraGame/Player/LyraPlayerState.*`。
- 服务端在 Experience Loaded 后设置 PlayerState 的 PawnData。
- `ALyraPlayerState::SetPawnData` 遍历 `PawnData->AbilitySets` 并调用 `GiveToAbilitySystem`。
- `ULyraAbilitySet::GiveToAbilitySystem` 只允许权威端授予 Attribute Sets、Gameplay Abilities 与 Gameplay Effects，见 `LyraStarterGame/Source/LyraGame/AbilitySystem/LyraAbilitySet.cpp`。
- `ULyraPawnExtensionComponent::InitializeAbilitySystem` 把 PlayerState 作为 Owner、当前 Pawn 作为 Avatar；死亡换 Pawn 时 ASC 可以持续存在。

此外，`ALyraGameState` 还持有一个独立的全局 ASC，其 Owner 和 Avatar 都是 GameState。它与 PlayerState ASC 是两个不同作用域，不能在图谱中合并成一个“项目 ASC”。

## 8. 模块化 Pawn 初始化

`ULyraPawnExtensionComponent` 与 `ULyraHeroComponent` 都实现 `IGameFrameworkInitStateInterface`，沿以下状态链推进：

```text
Spawned → DataAvailable → DataInitialized → GameplayReady
```

- PawnExtension 要求 PawnData 可用；本地或权威 Pawn 还要求 Controller 已配对。
- 进入 DataInitialized 前，PawnExtension 等待 Pawn 上所有模块化 Feature 达到 DataAvailable。
- Hero 等待 PlayerState、Controller、本地 InputComponent 与 PawnExtension。
- Hero 进入 DataInitialized 时初始化 ASC、玩家输入和 Camera Mode。

Pawn 在已 BeginPlay 的 World 中延迟生成时，会先拿到 PawnData、完成 Spawn 并开始组件初始化，然后才由 PlayerController `Possess`。因此 PawnExtension/Hero 可以先到 `Spawned`，但会因缺少 Controller、PlayerState 或本地 InputComponent 停在门槛处。Possess 设置 Controller 和 PlayerState；本地 `PawnClientRestart` 创建 InputComponent 并调用 `SetupPlayerInputComponent`；这些事件都会重新触发默认初始化检查，最终推进状态链。

该状态是“同一 Pawn 上各 Feature 的协同屏障”，不是单个组件自己的枚举字段。PawnExtension 进入 `DataInitialized` 前会检查所有已注册 Feature 是否至少到 `DataAvailable`；Hero 又反向等待 PawnExtension 到 `DataInitialized`。

核心证据位于：

- `LyraStarterGame/Source/LyraGame/Character/LyraPawnExtensionComponent.cpp`
- `LyraStarterGame/Source/LyraGame/Character/LyraHeroComponent.cpp`

## 9. Enhanced Input 到 Gameplay Ability

`ULyraHeroComponent::InitializePlayerInput`：

1. 获取 `UEnhancedInputLocalPlayerSubsystem`。
2. 加载 PawnData 的 `InputConfig` 与默认 Mapping Context。
3. 通过 `ULyraInputComponent::BindAbilityActions` 把 Input Action 映射为 Gameplay Tag。
4. Press/Release 转发给 `ULyraAbilitySystemComponent::AbilityInputTagPressed/Released`。
5. ASC 依据 Ability Spec 的动态 Input Tag 和 Activation Policy，在 `ProcessAbilityInput` 中激活 Ability。

`ULyraAbilitySet` 在授予 Ability 时把 `InputTag` 写入 Ability Spec 的动态源标签，因此输入绑定与能力授予通过 Gameplay Tag 解耦。

按键回调只把 Spec Handle 记入 Pressed/Held/Released 缓存；真正的激活发生在 `ALyraPlayerController::PostProcessInput` 每帧调用 PlayerState ASC 的 `ProcessAbilityInput` 时。若 ASC 带有 `Gameplay.AbilityInputBlocked`，本帧输入缓存会被清空。

## 10. UI 注入

UI 由 CommonUI、CommonGame 和 UIExtension 共同提供基础设施；具体布局可由 Game Feature Action 注入。

`UGameFeatureAction_AddWidgets` 位于 `LyraStarterGame/Source/LyraGame/GameFeatures/GameFeatureAction_AddWidget.*`，通过 CommonUI Layer 与 `UUIExtensionSubsystem` 添加布局和扩展 Widget。它监听 HUD Actor 扩展事件，因此 UI 也是 Experience/Game Feature 激活结果的一部分，而不是固定写死在 GameMode 中。

前端 Experience 还通过 `GameFeatureAction_AddComponents` 向 `LyraGameState` 添加 `B_LyraFrontendStateComponent`。该组件在 Experience Loaded 后依次处理用户初始化、Press Start、外部 Session 邀请与 Main Screen，并在流程完成前参与 Loading Screen 判定。

## 11. Frontend、Session 与 Map Travel

`ULyraUserFacingExperienceDefinition` 把一个面向用户的玩法选择拆成 `MapID + ExperienceID + Session/URL 参数`。`CreateHostingRequest` 将 Experience 名写入 `?Experience=`；新 World 的 GameMode 再优先从 URL 选中目标 Experience。

Host/Join 的 Session 成功回调都早于实际 Travel 完成：Host 在通知创建成功后调用 `ServerTravel`，OSSv1 Join 在通知加入成功后解析连接地址并调用 `ClientTravel`。因此 Session 成功、Travel 成功、目标 World Ready 和目标 Experience Loaded 是四个独立证据点。

Hard Travel 保留 GameInstance、GameInstanceSubsystem 和 LocalPlayer，但销毁并重建 World、GameMode、GameState、PlayerController、PlayerState、Pawn 与 Experience。UI Policy 按 LocalPlayer 保留 RootLayout 记录，并在新 PlayerController 建立时重新加入 viewport；栈内具体 Widget 的清理仍取决于 Blueprint/运行行为。

完整链路、Hard/Seamless 分叉与返回前端语义见 `.planning/codebase/TRAVEL.md`。

## 12. 运行时所有权摘要

| 对象 | 主要所有者/生命周期 | 网络与职责 |
|---|---|---|
| GameInstance | 每个 WorldContext/PIE 实例 | 本地对象；初始化用户、会话、UI 与 InitState 注册表 |
| GameInstanceSubsystem | 跨同一 GameInstance 的 World Travel | Session、User、LoadingScreen、UI Policy 状态可能跨 World 保留 |
| LocalPlayer / RootLayout | 跨 Hard Travel 保留并复用 | 新 PlayerController 建立时重新加入 viewport；Widget 栈清理待验证 |
| GameMode | World，权威端 | 不复制；选择 Experience、控制登录与 Pawn 生成 |
| GameState | World | 复制；承载 ExperienceManager 和全局 ASC |
| ExperienceManager | GameState Component | `CurrentExperience` 复制；各端自行加载资源与 Action |
| PlayerController | 服务器与所属客户端 | 连接和输入处理；其他客户端通常不可见 |
| PlayerState | PlayerController 创建，跨 Pawn 生命周期 | 复制；持有玩家 ASC、AttributeSet、PawnData 与 AbilitySet |
| Pawn | GameMode 生成，Controller Possess | 复制；是玩家 ASC 的临时 Avatar |
| PawnExtension | Pawn Component | 复制 PawnData；借用 PlayerState ASC 并维护 Owner/Avatar 绑定 |
| Hero Component | Pawn Feature | 本地端绑定输入；各角色按条件参与 InitState |

## 13. 已知失败语义与边界

- `OnGameFeaturePluginLoadComplete` 当前忽略 `Result`，只递减计数；“回调全部返回”不等于“插件全部成功激活”。
- Experience 资源加载的取消回调仍进入 `OnExperienceLoadComplete`；后续依靠对象检查暴露错误，而不是显式取消状态。
- EndPlay 先请求插件停用，再处理 Action 停用；源码明确标有非 FILO TODO。
- 异步 Action deactivation 被记录为尚未完整支持；部分加载状态的 EndPlay 也有 TODO。
- `OnRep_PawnData` 在 PlayerState 中为空；客户端 AbilitySet 依赖 ASC 复制，而不是客户端重新执行 `GiveToAbilitySystem`。
- Session create/join 成功回调发生在 Travel 完成之前；前端源码也明确留下“需确认旅行完成”的 TODO。
- Frontend State 的 EndPlay 没有显式取消 Control Flow 或清空 Main Screen；RootLayout 又跨 Hard Travel 复用，具体清理边界必须运行验证。

这些不是当前要修复的 Bug 清单，而是未来“管线权威”必须覆盖的失败路径；只验证成功主链不足以把整个 Experience 生命周期标成权威。

## 14. 当前未知

- `ShooterGym + ControlPoints` 运行时是否完整达到 Pawn `GameplayReady`。
- 输入是否实际经 Gameplay Tag 激活至少一个 Ability。
- Shooter HUD 是否在该切片中完成注入。
- Game Feature 从 Registered 到 Active 的完整运行日志证据。
- 哪些插件可在不破坏可玩 Experience 的情况下删除。
- 客户端、Listen Server、Dedicated Server 三种网络模式下的完整回调与 InitState 时序差异。
- Game Feature 激活失败时，当前加载屏、玩家门槛和错误恢复的实际运行结果。
- 普通 Frontend Host 的实际 Hard/Seamless 模式，以及 `B_LyraGameMode_C.bUseSeamlessTravel` 默认值。
- Session success、Travel、目标 World 和目标 Experience Ready 的真实时间线。
- Hard Travel 后 RootLayout 内前端 Widget 栈的清理行为。

Asset Registry 已解决指定资产的直接依赖和反射属性问题，但它不等于完整传递依赖图。剩余问题需要在 UE 5.6.1 中通过单一 L1 运行、详细日志和受控删减实验验证。
