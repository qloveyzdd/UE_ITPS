---
mapped_at: 2026-07-15
baseline: UE-5.6.1 / Lyra frozen fingerprint
scope: Frontend, session, map travel, world replacement, return-to-frontend
status: static-source-and-asset-evidence; runtime-travel-not-yet-captured
---

# Lyra 前端、会话与地图旅行管线

## 结论先行

Lyra 的前端选择不是“打开一个带固定玩法的地图”，而是先选择一个 `ULyraUserFacingExperienceDefinition`。该 Data Asset 同时描述：

```text
用户可见玩法
├─ MapID：去哪个 World
├─ ExperienceID：该 World 加载哪个 Lyra Experience
├─ ExtraArgs：附加 URL 参数
├─ OnlineMode / Session 参数
└─ UI 展示信息
```

`CreateHostingRequest` 把 `ExperienceID` 写成 URL 选项 `?Experience=<PrimaryAssetName>`。目标 World 创建新的 `ALyraGameMode` 后，GameMode 优先从这个 URL 选项选择 Experience。因此 Map Travel 是连接“前端语义选择”和“目标 World 运行架构”的关键权威边。

当前只完成配置、C++、Engine 源码、Asset Registry 和资产符号级静态验证。尚未受控重跑“前端选择 → Session → Travel → 目标 Experience Loaded”，所以本文不会把整条链标成运行权威。

## 证据口径

| 标记 | 含义 |
|---|---|
| 配置/源码事实 | 可由当前 UE 5.6.1 与 Lyra 文件直接复核 |
| Registry 事实 | 来自已归档的 UE 5.6.1 Asset Registry/对象反射输出 |
| 资产符号证据 | 二进制资产包含相关类型/函数/属性名，但不等于完整 Blueprint 图反编译 |
| 待运行验证 | 机制存在，但当前没有不可变日志证明本次确实执行 |

## 1. 默认 Game 启动前端不是 DA_Frontend 驱动

对于没有显式指定 Map 的 Game/Standalone 启动，`LyraStarterGame/Config/DefaultEngine.ini` 的 `GameDefaultMap` 直接指向：

```text
/Game/System/FrontEnd/Maps/L_LyraFrontEnd
```

资产符号显示 `L_LyraFrontEnd.umap` 的 `ALyraWorldSettings::DefaultGameplayExperience` 指向 `B_LyraFrontEnd_Experience`；现有 Registry 还证明该 Map 对前端 Experience 有直接软依赖。PIE 默认使用当前 Editor World，不能把 `GameDefaultMap` 路径直接套到所有 PIE 启动。

`DA_Frontend` 也保存了相同的 Map/Experience 对：

```text
MapID        = /Game/System/FrontEnd/Maps/L_LyraFrontEnd
ExperienceID = B_LyraFrontEnd_Experience
```

但它是一个 `UserFacingExperience` 数据对象，不是 Engine 启动时选择默认地图的原因。必须区分两条边：

```text
配置 GameDefaultMap → 前端 Map
前端 Map WorldSettings → 前端 Experience
```

不能把它们错误合并成 `DA_Frontend → 启动前端`。

## 2. Frontend Experience 如何建立前端状态机

Registry 证明 `B_LyraFrontEnd_Experience` 没有默认 PawnData，并包含四类 Action：

- `GameFeatureAction_SplitscreenConfig`
- `GameFeatureAction_AddComponents`
- `ApplyFrontendPerfSettingsAction`
- `GameFeatureAction_AddWidgets`

资产符号进一步显示 `GameFeatureAction_AddComponents` 把 `B_LyraFrontendStateComponent` 与 `LyraGameState` 连接起来。该 Blueprint Component 的原生父类是 `ULyraFrontendStateComponent`，其 `MainScreenClass` 指向 `W_LyraFrontEnd`。

Experience 进入 Loaded 后，Frontend State 以高优先级回调启动以下 Control Flow：

```text
Wait For User Initialization
→ Try Show Press Start Screen
→ Try Join Requested Session
→ Try Show Main Screen
```

该组件同时实现 `ILoadingProcessInterface`。前端流程尚未准备好时，`bShouldShowLoadingScreen=true`；Press Start 或 Main Screen 真正加入 UI Layer 后才解除加载屏。

这说明前端可见并不等于 Experience 刚刚 Loaded：前端还存在用户初始化、外部邀请 Session 和异步 Widget 创建三道门。

## 3. UserFacingExperience 是旅行请求模型

`ULyraUserFacingExperienceDefinition::CreateHostingRequest` 执行以下确定性映射：

| UserFacing 字段 | HostRequest 字段/用途 |
|---|---|
| `MapID` | 解析为目标 Map package |
| 自身 PrimaryAssetName | `ModeNameForAdvertisement` |
| `ExtraArgs` | 原样复制为 URL options |
| `ExperienceID.PrimaryAssetName` | 新增 `Experience=<name>` |
| `MaxPlayerCount` | Session 最大人数 |
| `bRecordReplay` | 支持时新增 `DemoRec` |

例如 `DA_Expanse_TDM` 的静态结果是：

```text
MapID        = /ShooterMaps/Maps/L_Expanse
ExperienceID = B_ShooterGame_Elimination
```

在线 HostRequest 的典型 URL 语义是：

```text
/ShooterMaps/Maps/L_Expanse?listen?Experience=B_ShooterGame_Elimination
```

`ExtraArgs` 是 `TMap`，选项文本顺序不应成为证据身份；应比较解析后的 Map 与键值集合。

当前 UserFacing 列表还证明：

| 资产 | Map | Experience | 前端可见 |
|---|---|---|---|
| `DA_Expanse_TDM` | `L_Expanse` | `B_ShooterGame_Elimination` | 是 |
| `DA_Convolution_ControlPoint` | `L_Convolution_Blockout` | `B_LyraShooterGame_ControlPoints` | 是 |
| `DA_ShooterGame_ShooterGym` | `L_ShooterGym` | `B_LyraShooterGame_ControlPoints` | 否 |

## 4. Blueprint UI 边界

前端 UI 资产包含以下函数符号：

- `W_ExperienceSelectionScreen`：`CreateHostingRequest`、`HostSession`、`QuickPlaySession`
- `W_HostSessionScreen`：`CreateHostingRequest`、`HostSession`
- `W_ExperienceList`、`W_ExperienceTile`：`LyraUserFacingExperienceDefinition`

这足以证明 Blueprint 使用了这些暴露面，但不足以证明每个节点的分支、参数和错误处理。未来 Blueprint Inspector 必须输出节点、Pin、连接和默认值；当前不能根据字符串出现就创建“完整 UI 调用管线权威”。

## 5. Host Session 到 ServerTravel

当前 `CommonUser.Build.cs` 固定 `COMMONUSER_OSSV1=1`，因此本基线实际编译的是 OSSv1 分支。

### Offline

`HostSession` 验证请求与 HostingPlayer 后，Offline 模式直接执行：

```text
GetWorld()->ServerTravel(Request->ConstructTravelURL())
```

Offline URL 不包含 `listen`。

### LAN / Online

LAN/Online 模式先把 URL 保存到 `PendingTravelURL`，再创建 Online Session。创建成功后的顺序是：

```text
NotifyCreateSessionComplete(success)
→ ServerTravel(PendingTravelURL)
```

因此 `OnCreateSessionComplete(success)` 不是 Map Load Complete，也不是目标 Experience Loaded。二者之间仍可能发生 URL、ServerTravel、LoadMap、Experience 或 Game Feature 失败。

## 6. Quick Play

`QuickPlaySession` 先按 UserFacingExperience 的模式信息搜索：

```text
找到可加入 Session → JoinSession
没有结果            → HostSession
```

所以 Quick Play 不是独立旅行协议，只是 Host 与 Join 之前的一层决策。未来图谱应把它建成决策节点，而不是第三种 Map Travel 实现。

## 7. Join Session 到 ClientTravel

OSSv1 Join 成功后的顺序是：

```text
NotifyJoinSessionComplete(success)
→ Resolve Connect String
→ OnPreClientTravelEvent(URL&)
→ PlayerController.ClientTravel(URL, TRAVEL_Absolute)
```

`ULyraGameInstance` 订阅 `OnPreClientTravelEvent`，测试加密开启时会在这里追加 `EncryptionToken`。

Frontend State 在处理外部邀请 Session 时，收到 Join 成功就取消前端 Flow。源码自身留下 TODO：需要确保 Join 完成后 Server Travel/连接旅行也真正完成。这个 TODO 精确说明了当前权威边界：

```text
JoinSession success ≠ ClientTravel success ≠ Target World ready
```

## 8. Engine 如何替换 World

Host 侧 `UWorld::ServerTravel` 把 URL 交给 `AGameModeBase::ProcessServerTravel`。是否 Seamless 由以下条件共同决定：

- GameMode 的 `bUseSeamlessTravel`
- URL 中的 `SeamlessTravel` / `NoSeamlessTravel`
- PIE 是否允许 Seamless Travel
- Server 已运行时间是否超过 Engine 限制

普通 HostRequest 不主动添加 `SeamlessTravel`。`ALyraGameMode` C++ 构造函数也没有设置 `bUseSeamlessTravel`；当前尚未用反射保存 `B_LyraGameMode_C` 的该默认值，因此本文不把普通前端 Host 的 Hard/Seamless 模式写成已验证事实。

若走 Hard Travel，UE 5.6.1 的 `LoadMap` 主链是：

```text
销毁旧 Pawn 与 PlayerController
→ OldWorld.EndPlay(LevelTransition)
→ OldWorld.CleanupWorld
→ 加载 NewWorld
→ NewWorld.SetGameInstance(原 GameInstance)
→ NewWorld.SetGameMode(URL)
→ InitializeActorsForPlay(URL)
→ 为 LocalPlayer SpawnPlayActor(URL)
→ NewWorld.BeginPlay
→ PostLoadMap
```

随后新 `ALyraGameMode::InitGame` 在下一 Tick 选择 Experience。由于 URL 中存在 `Experience`，它优先于目标 Map 的 WorldSettings。

## 9. Hard Travel 的对象所有权边界

| 对象 | Hard Travel 结果 | 原因/后果 |
|---|---|---|
| Engine / WorldContext | 保留 | 驱动 Browse/LoadMap |
| GameInstance | 保留 | NewWorld 重新绑定同一实例 |
| GameInstanceSubsystem | 保留 | Session、User、LoadingScreen、UI Manager 状态跨 World |
| LocalPlayer | 保留 | 新 World 再次 SpawnPlayActor |
| UI Policy / RootLayout 记录 | 保留并复用 | Policy 以 LocalPlayer 为键，Controller 重建时移除再加入 viewport |
| World / GameMode / GameState | 销毁后新建 | 目标 Map 有全新 ExperienceManager |
| PlayerController / Pawn | 销毁后新建 | 本地 Player 在目标 World 重新登录/生成 |
| PlayerState | Hard Travel 不保留 | 新 PlayerController 创建新的 PlayerState/ASC |
| Experience Actions | 旧 World EndPlay 时停用 | 新 World 按目标 Experience 重新激活 |

RootLayout 对象可复用不代表前端栈内的每个 Widget 都已正确清空。Frontend State 的 `EndPlay` 没有显式取消 Flow 或弹出 Main Screen；这可能由具体 Blueprint Widget 的退出逻辑处理，当前需要运行和 Blueprint 图证据，不能静态假设。

## 10. Seamless Travel 是另一条管线

`ULyraSystemStatics::PlayNextGame` 显式向 LastURL 添加 `SeamlessTravel`，使用 Relative ServerTravel 保持客户端连接。Engine 会先把 PlayerState、参与旅行的 Controller 等 Actor 带入过渡阶段，再走 `FSeamlessTravelHandler`，不能复用上面的 Hard Travel 对象表。

但“进入保留集合”不等于“最终目标 World 仍是同一业务对象”。UE 5.6.1 默认 `HandleSeamlessTravelPlayer` 会创建新的 PlayerController 和 PlayerState，调用旧 PlayerState 的 `SeamlessTravelTo → CopyProperties` 后销毁旧 PlayerState。Lyra 没有覆盖该流程，`ALyraPlayerState::CopyProperties` 仅调用基类，随后保留 `Copy stats` TODO。

因此最终目标 World 中：

- Server/Listen 权威侧 PC、PS、ASC 与 Pawn 仍按新 World 重建；
- PawnData、AbilitySet、Team/Squad、Attribute 与 Effect 不能假定自动保留；
- 新 PlayerState 重新等待目标 Experience，再设置 PawnData 和授予 AbilitySet；
- Client 本地 PC 可被过渡保留，但不能据此推导权威 PlayerState/ASC/Pawn 身份稳定。

`DefaultEngine.ini` 设置 `net.AllowPIESeamlessTravel=1` 只表示 PIE 允许该机制，不表示每次前端 Host 都使用它。

完整两阶段 World 切换、四模式差异与字段级存续边界见 `.planning/codebase/NETWORK-MODES.md`。

未来必须把以下两条管线分别验证：

```text
Frontend Host/Join → 目标玩法
PlayNextGame → 下一局
```

## 11. 返回前端与 `?closed`

`UCommonGameInstance::ReturnToMainMenu` 先清理 User/Session 状态，再调用 Engine Disconnect。Engine 设置绝对 ClientTravel `?closed`；`Browse` 看到 `closed` 后加载 `GameDefaultMap`，即 `L_LyraFrontEnd`。

新前端 World 的 `ULyraFrontendStateComponent` 检查 GameMode OptionsString 中的 `closed`：

- Hard disconnect：重置 User 状态；
- 每次进入前端：总是调用 `CleanUpSessions`；
- 然后重新执行前端 Control Flow。

这解释了“返回前端”为什么不是简单 `OpenLevel`：它同时承担网络断开、Session 清理、用户状态恢复和前端 Experience 重建。

Travel/Network Failure 通常也会触发这一稳定化路径，但用户可见错误并未由 C++ 主链闭合：CommonSession 的 Travel Failure 只写日志并切换 OutOfGame，不会在此前 Join 已成功后再次广播 Join 失败；`B_LyraGameInstance` 是否通过 Blueprint Event 补充错误 UI 仍待资产验证。Loading Screen 会覆盖 PendingNetGame、TravelURL、LoadMap、Seamless 和 Experience/Frontend 未就绪阶段，但它本身不是错误消息系统。

## 12. 对增量信任模型的直接约束

本管线至少包含四种不能互相继承的权威对象：

```text
节点：UserFacingExperience、Map、Experience、SessionSubsystem
连接：UserFacing.MapID → Map
连接：UserFacing.ExperienceID → URL Experience option
管线：Session success → Travel → New World → Experience Loaded
上下文：Offline/LAN/Online、Host/Join、Hard/Seamless、PIE/Standalone/Client/Server
```

以下变化必须扩大审查边界：

- Map 不变但 ExperienceID 改变；
- Experience 不变但 Map/WorldSettings 改变；
- Offline 改为 Online，新增 Session 与 `listen` 语义；
- Hard Travel 改为 Seamless Travel，改变连接、过渡 Actor 和字段复制方式，但不自动保留 PlayerState/ASC 业务身份；
- Join 成功回调时机改变；
- GameInstanceSubsystem 或 RootLayout 的跨 World 状态改变。

## 13. 可复核源码与证据锚点

行号只用于人工定位，不作为长期身份；长期证据应绑定文件内容指纹。

- 启动 Map 与 PIE 设置：`LyraStarterGame/Config/DefaultEngine.ini`
- Frontend Flow：`LyraStarterGame/Source/LyraGame/UI/Frontend/LyraFrontendStateComponent.cpp`
- UserFacing → HostRequest：`LyraStarterGame/Source/LyraGame/GameModes/LyraUserFacingExperienceDefinition.cpp`
- Experience 选择与 Dedicated Host：`LyraStarterGame/Source/LyraGame/GameModes/LyraGameMode.cpp`
- Host/QuickPlay/Join/Travel：`LyraStarterGame/Plugins/CommonUser/Source/CommonUser/Private/CommonSessionSubsystem.cpp`
- OSSv1 编译选择：`LyraStarterGame/Plugins/CommonUser/Source/CommonUser/CommonUser.Build.cs`
- Session 邀请与返回菜单：`LyraStarterGame/Plugins/CommonGame/Source/Private/CommonGameInstance.cpp`
- UI Policy 与 RootLayout：`LyraStarterGame/Plugins/CommonGame/Source/Private/GameUIPolicy.cpp`
- 下一局 Seamless Travel：`LyraStarterGame/Source/LyraGame/System/LyraSystemStatics.cpp`
- ServerTravel：`D:/UnrealEngine_5.6/Engine/Source/Runtime/Engine/Private/World.cpp`
- ProcessServerTravel：`D:/UnrealEngine_5.6/Engine/Source/Runtime/Engine/Private/GameModeBase.cpp`
- Browse/LoadMap/TickWorldTravel：`D:/UnrealEngine_5.6/Engine/Source/Runtime/Engine/Private/UnrealEngine.cpp`
- ClientTravel：`D:/UnrealEngine_5.6/Engine/Source/Runtime/Engine/Private/PlayerController.cpp`
- PlayerState CopyProperties：`D:/UnrealEngine_5.6/Engine/Source/Runtime/Engine/Private/PlayerState.cpp`
- Loading Screen：`LyraStarterGame/Plugins/CommonLoadingScreen/Source/CommonLoadingScreen/Private/LoadingScreenManager.cpp`
- UserFacing、Map、Experience 静态值：`.planning/evidence/lyra-5.6.1/asset-registry-slice.json`

## 14. 待运行验证

1. `B_LyraGameMode_C.bUseSeamlessTravel` 的实际默认值。
2. 前端点击 `DA_Expanse_TDM` 后实际生成的 URL、Session 模式与选项集合。
3. `OnCreateSessionComplete`、`ProcessServerTravel`、OldWorld EndPlay、NewWorld BeginPlay 的真实顺序。
4. 目标 GameMode 是否从 URL 选择 `B_ShooterGame_Elimination`。
5. Hard Travel 后 PlayerState、ASC、Pawn 和 HUD 的实际重建。
6. RootLayout 复用时前端 Widget 栈是否被正确清理。
7. Join、ClientTravel 和连接失败时 Loading Screen 与前端 Flow 的恢复行为。
8. Seamless 前后 PC、PS、ASC、Pawn、GameState、ExperienceManager 的对象身份及 PawnData/AbilitySet/Team/Attribute 结果。
9. `B_LyraGameInstance` 的 NetworkError/TravelError Blueprint 行为。

以上应在受控重跑 L0 后，再作为 L1 的单一纵向旅行切片验证。
