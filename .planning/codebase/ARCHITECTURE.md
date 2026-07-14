---
mapped_at: 2026-07-14
scope: LyraStarterGame
status: static-and-ue-5.6.1-evidence-map
---

# Lyra 顶层架构与启动主链

## 架构总览

Lyra 不是单一 Gameplay Module，而是“稳定项目壳 + Experience 配置 + 按需 Game Feature + 模块化 Pawn 初始化”的组合架构。

```text
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

## 1. 项目壳

- `LyraGame` 是主运行时模块，入口见 `LyraStarterGame/Source/LyraGame/LyraGameModule.cpp`。
- `LyraEditor` 只在 Editor Target 中加载，入口见 `LyraStarterGame/Source/LyraEditor/LyraEditor.cpp`。
- 项目级稳定能力位于 `LyraStarterGame/Source/LyraGame/`：Experience、Pawn、GAS、输入、UI、团队、装备、库存、设置与在线会话。
- 可替换玩法位于 `LyraStarterGame/Plugins/GameFeatures/`：`ShooterCore`、`ShooterMaps`、`TopDownArena`、`ShooterExplorer`、`ShooterTests`。
- Game Feature 插件均使用 `ExplicitlyLoaded: true`，且初始状态为 `Registered`；是否激活由 Experience 决定，而不是仅由 `.uproject` 中的 Enabled 决定。

## 2. Experience 选择

`ALyraGameMode::InitGame` 在下一帧调用匹配分配逻辑，见 `LyraStarterGame/Source/LyraGame/GameModes/LyraGameMode.cpp`。

Experience 来源具有优先级：匹配分配、URL `Experience` 参数、PIE Developer Settings、命令行、World Settings、Dedicated Server、默认 Experience。确定后，`OnMatchAssignmentGiven` 调用 `ULyraExperienceManagerComponent::SetCurrentExperience`。

若 Experience 尚未加载，`HandleStartingNewPlayer` 不启动玩家；Experience 完成后，`OnExperienceLoaded` 才为尚无 Pawn 的控制器执行 `RestartPlayer`。因此 Experience 是玩家生成前的硬门槛。

## 3. Experience 组成

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

## 4. Experience 加载与 Game Feature 激活

`ULyraExperienceManagerComponent::StartExperienceLoad` 位于 `LyraStarterGame/Source/LyraGame/GameModes/LyraExperienceManagerComponent.cpp`：

1. 将 Experience 与 ActionSet 加入 Primary Asset Bundle 加载。
2. 根据客户端、服务器或 Editor 上下文选择对应 Bundle。
3. 资源加载完成后，把 `GameFeaturesToEnable` 转换成插件 URL。
4. 通过 `UGameFeaturesSubsystem::LoadAndActivateGameFeaturePlugin` 激活插件。
5. 插件全部完成后，依次执行 Experience 和 ActionSet 中的 GameFeatureAction。
6. 最终广播高、普通、低三个优先级的 Experience Loaded 回调。

`ULyraGameFeaturePolicy` 位于 `LyraStarterGame/Source/LyraGame/GameFeatures/LyraGameFeaturePolicy.*`，负责项目级 Game Feature 管理、客户端/服务器加载模式和 Gameplay Cue 路径处理。

本次 UE 5.6.1 运行中，五个项目 Game Feature 插件均成功进入 `Registered`；默认 Experience 与前端 Experience 随后完成加载。由于这两个 Experience 都不声明额外 Game Feature，本次日志不能证明 `ShooterCore` 已进入 `Active`，该证据必须由 L1 Shooter 切片补齐。

## 5. PawnData 与生成

`ULyraPawnData` 定义见 `LyraStarterGame/Source/LyraGame/Character/LyraPawnData.h`，聚合：

- `PawnClass`
- `AbilitySets`
- `TagRelationshipMapping`
- `InputConfig`
- `DefaultCameraMode`

`ALyraGameMode::GetPawnDataForController` 优先使用 PlayerState 上的 PawnData，其次使用当前 Experience 的 `DefaultPawnData`，最后回退到 Asset Manager 默认 PawnData。

`SpawnDefaultPawnAtTransform` 先延迟构造 Pawn，把 PawnData 写入 `ULyraPawnExtensionComponent`，再完成 Spawn。这保证组件初始化看到的是正确 PawnData。

## 6. PlayerState、ASC 与 Pawn Avatar

- `ALyraPlayerState` 持有长期存在的 `ULyraAbilitySystemComponent` 和 Attribute Sets，见 `LyraStarterGame/Source/LyraGame/Player/LyraPlayerState.*`。
- 服务端在 Experience Loaded 后设置 PlayerState 的 PawnData。
- `ALyraPlayerState::SetPawnData` 遍历 `PawnData->AbilitySets` 并调用 `GiveToAbilitySystem`。
- `ULyraAbilitySet::GiveToAbilitySystem` 只允许权威端授予 Attribute Sets、Gameplay Abilities 与 Gameplay Effects，见 `LyraStarterGame/Source/LyraGame/AbilitySystem/LyraAbilitySet.cpp`。
- `ULyraPawnExtensionComponent::InitializeAbilitySystem` 把 PlayerState 作为 Owner、当前 Pawn 作为 Avatar；死亡换 Pawn 时 ASC 可以持续存在。

## 7. 模块化 Pawn 初始化

`ULyraPawnExtensionComponent` 与 `ULyraHeroComponent` 都实现 `IGameFrameworkInitStateInterface`，沿以下状态链推进：

```text
Spawned → DataAvailable → DataInitialized → GameplayReady
```

- PawnExtension 要求 PawnData 可用；本地或权威 Pawn 还要求 Controller 已配对。
- 进入 DataInitialized 前，PawnExtension 等待 Pawn 上所有模块化 Feature 达到 DataAvailable。
- Hero 等待 PlayerState、Controller、本地 InputComponent 与 PawnExtension。
- Hero 进入 DataInitialized 时初始化 ASC、玩家输入和 Camera Mode。

核心证据位于：

- `LyraStarterGame/Source/LyraGame/Character/LyraPawnExtensionComponent.cpp`
- `LyraStarterGame/Source/LyraGame/Character/LyraHeroComponent.cpp`

## 8. Enhanced Input 到 Gameplay Ability

`ULyraHeroComponent::InitializePlayerInput`：

1. 获取 `UEnhancedInputLocalPlayerSubsystem`。
2. 加载 PawnData 的 `InputConfig` 与默认 Mapping Context。
3. 通过 `ULyraInputComponent::BindAbilityActions` 把 Input Action 映射为 Gameplay Tag。
4. Press/Release 转发给 `ULyraAbilitySystemComponent::AbilityInputTagPressed/Released`。
5. ASC 依据 Ability Spec 的动态 Input Tag 和 Activation Policy，在 `ProcessAbilityInput` 中激活 Ability。

`ULyraAbilitySet` 在授予 Ability 时把 `InputTag` 写入 Ability Spec 的动态源标签，因此输入绑定与能力授予通过 Gameplay Tag 解耦。

## 9. UI 注入

UI 由 CommonUI、CommonGame 和 UIExtension 共同提供基础设施；具体布局可由 Game Feature Action 注入。

`UGameFeatureAction_AddWidgets` 位于 `LyraStarterGame/Source/LyraGame/GameFeatures/GameFeatureAction_AddWidget.*`，通过 CommonUI Layer 与 `UUIExtensionSubsystem` 添加布局和扩展 Widget。它监听 HUD Actor 扩展事件，因此 UI 也是 Experience/Game Feature 激活结果的一部分，而不是固定写死在 GameMode 中。

## 10. 当前未知

- `ShooterGym + ControlPoints` 运行时是否完整达到 Pawn `GameplayReady`。
- 输入是否实际经 Gameplay Tag 激活至少一个 Ability。
- Shooter HUD 是否在该切片中完成注入。
- Game Feature 从 Registered 到 Active 的完整运行日志证据。
- 哪些插件可在不破坏可玩 Experience 的情况下删除。

Asset Registry 已解决指定资产的直接依赖和反射属性问题，但它不等于完整传递依赖图。剩余问题需要在 UE 5.6.1 中通过单一 L1 运行、详细日志和受控删减实验验证。
