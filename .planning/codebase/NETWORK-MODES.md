---
mapped_at: 2026-07-15
baseline: UE-5.6.1 / Lyra frozen fingerprint
scope: Standalone, Listen Server, Dedicated Server, Client, Hard Travel, Seamless Travel, loading and failure recovery
status: static-source-and-config-evidence; mode-specific-runtime-evidence-not-yet-captured
---

# Lyra 网络模式、旅行存续与失败边界

## 结论先行

Lyra 的 Target、运行时 `NetMode`、Session 模式和 Travel 模式是四个独立维度，不能互相替代：

```text
Build Target
  LyraGame / LyraClient / LyraServer / LyraEditor
        ×
Runtime NetMode
  Standalone / Listen Server / Dedicated Server / Client
        ×
Session Mode
  Offline / LAN / Online
        ×
Travel Mode
  Hard / Seamless
```

最重要的静态结论有五个：

1. `LyraGame` 是 Game Target，不等于固定的 Standalone；它可因 URL 和 NetDriver 成为 Standalone、Listen Server 或 Client。
2. Offline Host 不添加 `?listen`，目标 World 为 Standalone；LAN/Online Host 添加 `?listen`，Game Target 进入 Listen Server。Dedicated Server 即使没有本地玩家，也会先在默认前端图完成服务登录，再 Host 并旅行。
3. Client Join 成功只表示 Session 层完成；之后仍要经历绝对 `ClientTravel`、`Browse`、`PendingNetGame`、目标 Map Load、Experience 复制与客户端自行加载。
4. Lyra 的 Seamless Travel 不代表最终目标 World 原样保留 PlayerState、ASC 或 Pawn。UE 5.6.1 默认 GameMode 会在目标 World 创建新的 PlayerController 和 PlayerState，再调用 `CopyProperties`；Lyra 当前只调用基类复制并留有 `Copy stats` TODO。
5. Loading Screen 是“就绪屏障”，不是错误处理系统。连接/旅行失败通常会回到默认前端图，但 CommonSession 的旅行失败回调不会再次广播 Join 失败；`B_LyraGameInstance` 是否在 Blueprint 中补充错误 UI 尚未取得资产级可读证据。

本文是配置与源码静态归档，不是四种模式的运行权威。所有对象身份、回调顺序和失败恢复仍需分别运行捕获。

## 证据口径

| 标记 | 含义 |
|---|---|
| 配置事实 | Target.cs、INI 与插件配置的直接内容 |
| 源码事实 | 当前 UE 5.6.1、Lyra 与 CommonUser 源码中的明确分支和调用 |
| 静态推论 | 由多个源码事实组合得出的结果，尚未由本基线运行日志证明 |
| 资产级待验证 | 行为可能位于 Blueprint/资产序列化内容，当前没有安全可读的结构化导出 |
| 待运行验证 | 必须通过指定 Target、NetMode、Session 和 Travel 上下文采集证据 |

## 1. Target 只定义构建能力

项目提供的主要 Target 为：

| Target | `TargetType` | 构建能力与边界 |
|---|---|---|
| `LyraGame` | `Game` | 常规游戏进程；可按 URL/NetDriver 运行 Standalone、Listen Server 或 Client |
| `LyraClient` | `Client` | Client-only；因 `WITH_SERVER_CODE=0`，Host 校验直接返回不能托管，不应承担主机职责 |
| `LyraServer` | `Server` | Dedicated Server；`IsRunningDedicatedServer()` 为真，无本地玩家和游戏视口 |
| `LyraEditor` | `Editor` | 支持 PIE 的 Standalone、Listen、Dedicated 与 Client 组合 |

Engine 的 `UWorld::GetNetMode` 优先检查 Dedicated Server，然后看当前 NetDriver；NetDriver 尚未建立时，还会从 `NextURL` 或 `PendingNetGame.URL` 推导：

- URL 有 `?listen`：`NM_ListenServer`；
- URL 有远程 Host：`NM_Client`；
- 两者都没有：`NM_Standalone`。

因此未来的 Authority Context 不能只记录 `Target=LyraGame`，还必须记录真实 `NetMode` 和 Travel URL。

## 2. Session 模式如何决定目标 NetMode

`UCommonSession_HostSessionRequest::ConstructTravelURL` 的规则是：

```text
Offline → Map + ExtraArgs
LAN     → Map + ?bIsLanMatch + ?listen + ExtraArgs
Online  → Map + ?listen + ExtraArgs
```

Lyra 的 `ULyraUserFacingExperienceDefinition::CreateHostingRequest` 再把选中的 Experience 加入 `?Experience=<name>`。

这使前端选择最终同时决定：

- 目标 Map；
- 目标 Experience；
- 是否创建监听 NetDriver；
- Session 广告信息；
- 后续 World 中加载 Client/Server 哪些资源 Bundle。

## 3. 四种运行模式总表

| 运行模式 | 常见入口 | 本地玩家 | 权威 GameMode | NetDriver | Experience Bundle | Loading Screen |
|---|---|---:|---:|---|---|---|
| Standalone | `LyraGame` / PIE，Offline Host | 有 | 有 | 无 GameNetDriver | Client + Server | 有视口时创建 |
| Listen Server | `LyraGame` / PIE，LAN/Online Host | 有 | 有 | Listen GameNetDriver | Client + Server | 有视口时创建 |
| Dedicated Server | `LyraServer` / Dedicated PIE | 无 | 有 | Server GameNetDriver | Server only | 不创建 |
| Client | `LyraGame`、`LyraClient` 或 PIE Client，Join/地址连接 | 有 | 无 | Pending → Client GameNetDriver | Client only | 有视口时创建 |

`ULyraExperienceManagerComponent::StartExperienceLoad` 的实际 Bundle 选择为：

```text
bLoadClient = Editor 或 NetMode != DedicatedServer
bLoadServer = Editor 或 NetMode != Client
```

Editor 会同时加载两侧 Bundle 是开发环境便利行为，不能直接证明独立 Client/Server 构建的资源边界。

## 4. Standalone：同进程中的本地权威

Offline Host 的源码顺序为：

```text
Frontend / UI 选择 UserFacingExperience
→ HostSession(OnlineMode=Offline)
→ 校验 HostRequest
→ ServerTravel(Map?Experience=...)
→ URL 不含 ?listen
→ Hard 或 Seamless 分叉
→ 目标 World 没有 GameNetDriver
→ NetMode = Standalone
→ 新 GameMode 选择并加载 Experience
→ 本地 PlayerController / PlayerState / Pawn 建立
```

Standalone 同时执行权威逻辑和本地表现逻辑，但这不等于“Server 与 Client 网络链已经验证”。它没有连接握手、远端复制、网络失败、远端 ClientTravel 或 ServerNotifyLoadedWorld 等语义。

对最小项目研究的直接含义是：Standalone 最小运行链可以暂时排除在线 Session 服务和网络复制验证，但不能用它替代网络版最小链。

## 5. Listen Server：本地玩家与服务器共用进程

LAN/Online Host 成功后，CommonSession 调用：

```text
NotifyCreateSessionComplete(success)
→ ServerTravel(Map?listen?Experience=...)
→ AGameModeBase::ProcessServerTravel
→ 遍历 PlayerController
   ├─ 远端连接：ClientTravel(relative, bSeamless)
   └─ 本地玩家：PreClientTravel，不向自己发送远端 RPC
→ 目标 World 建立 Listen GameNetDriver
```

`ProcessClientTravel` 会从发给远端客户端的 URL 中移除 `listen`，避免客户端在旅行期间把自己推导为 Listen Server。

Listen Server 的同一进程同时加载 Client 和 Server Bundle；本地玩家绕过远端连接路径，远端玩家则必须经过客户端旅行和加载确认。因此“Host 本机可玩”与“远端 Client 可玩”是两个独立验收点。

## 6. Dedicated Server：前端图是服务启动跳板

Dedicated Server 不是直接跳过 Lyra 前端架构。`ALyraGameMode::HandleMatchAssignmentIfNotExpectingOne` 在没有 URL、命令行或 WorldSettings Experience 时会调用 `TryDedicatedServerLogin`。只有同时满足以下条件才进入专用流程：

```text
NetMode == NM_DedicatedServer
且 Current Map == GameDefaultMap
```

随后执行：

```text
默认前端图
→ CommonUser 尝试 Dedicated Server 在线登录
→ 登录成功或失败都继续
→ 选择命令行 UserExperience / Playlist
→ 找不到时使用 bIsDefaultExperience 的 UserFacingExperience
→ CreateHostingRequest
→ HostSession(nullptr, Request)
→ 创建 Session
→ ServerTravel 到玩法 Map
→ 目标 GameMode 从 ?Experience= 选择 Experience
```

关键边界：

- Dedicated Server 没有 `ULocalPlayer`；CommonSession 只因 `bIsDedicatedServer` 才允许空 HostingPlayer。
- Dedicated Server 不创建 `ULoadingScreenManager`，因为没有游戏视口，也不需要面向玩家遮挡画面。
- Experience 只加载 Server Bundle；任何依赖纯 Client 资源才能完成的服务器初始化都属于错误架构。
- Dedicated 登录当前是“可尝试但不阻塞开服”：失败也会继续 `HostDedicatedServerMatch`。

## 7. Client Join：Session 成功后才开始连接旅行

OSSv1 Join 成功且不使用 Reservation Beacon 时：

```text
FinishJoinSession(success)
→ NotifyJoinSessionComplete(success)
→ InternalTravelToSession
→ GetResolvedConnectString
→ OnPreClientTravelEvent(URL&)
→ PlayerController::ClientTravel(URL, TRAVEL_Absolute)
→ UEngine::SetClientTravel
→ TickWorldTravel
→ Browse(remote URL)
→ 创建 PendingNetGame + PendingNetDriver
→ 连接、握手并取得目标 Map
→ LoadMap(Context, PendingNetGame.URL, PendingNetGame)
→ PendingNetGame::TravelCompleted
```

连接期间旧 World 仍可能存在，`PendingNetGame` 表示“正在连接”，不是新 World 已经 Ready。目标 World 建立后，Client 没有 Auth GameMode；服务器复制 `CurrentExperience`，客户端 `OnRep_CurrentExperience` 再独立加载 Client Bundle、激活本地 Game Feature Action，并等待自己的 Experience 进入 `Loaded`。

因此 Client 的最小可用证据至少分为：

```text
Join accepted
→ resolved connect string
→ PendingNetGame connected
→ target map loaded
→ CurrentExperience replicated
→ client Experience loaded
→ local Pawn InitState GameplayReady
```

## 8. Hard Travel：整个 World 身份更换

Hard Travel 使用 `UEngine::Browse/LoadMap` 替换 World。对 Lyra 的最终结果为：

| 对象 | Hard Travel 后 | 说明 |
|---|---|---|
| GameInstance | 保留 | 跨 World 的根对象 |
| GameInstanceSubsystem | 保留 | User、Session、LoadingScreen、UI Policy 等继续存在 |
| LocalPlayer | 保留 | 新 PlayerController 重新关联 |
| RootLayout 记录 | 保留 | UI Policy 以 LocalPlayer 为键复用；内部 Widget 栈待运行验证 |
| World / GameMode / GameState | 重建 | 目标 Map 形成新运行上下文 |
| ExperienceManagerComponent | 重建 | 随新 GameState 重新选择/复制并加载 Experience |
| PlayerController / PlayerState | 重建 | 新 PlayerState 持有新 ASC |
| Pawn | 重建 | 等目标 Experience Loaded 后才允许 RestartPlayer |
| PlayerState ASC / GameState ASC | 重建 | 不能继承旧 World 的对象权威 |

Hard Travel 的权威边界很清晰：跨 World 保留的是 GameInstance 级上下文，不是玩法对象。

## 9. Seamless Travel 的两阶段 World 切换

`AGameModeBase::ProcessServerTravel` 只有在以下任一条件成立时才走 Seamless：

- `bUseSeamlessTravel` 为真；
- URL 含 `SeamlessTravel`；

URL 中 `NoSeamlessTravel` 可强制关闭。PIE 还需 `net.AllowPIESeamlessTravel=1`；当前 Lyra 配置已允许 PIE，但“允许”不等于普通 Host 自动启用。

`ULyraSystemStatics::PlayNextGame` 明确给 LastURL 添加 `SeamlessTravel`，这是当前源码中已确认的显式使用点。普通 Frontend HostRequest 不添加该选项；`B_LyraGameMode_C.bUseSeamlessTravel` 的资产默认值仍待结构化反射验证。

当前 `TransitionMap` 未在项目配置中启用，UE 会使用临时过渡 World。整体顺序为：

```text
Old World
→ 选择要带入过渡阶段的 Actor
→ 临时 Transition World
→ 再次选择要带入最终 World 的 Actor
→ Final World 初始化
→ 新 GameMode::PostSeamlessTravel
→ Final World BeginPlay
```

## 10. Seamless Travel 的真实对象存续

“被带过 World 边界”和“最终仍是同一个业务对象”不是同一件事。

### Server / Listen Server 权威侧

UE 默认 `GetSeamlessTravelActorList` 会把 PlayerState 加入保留集合，World 也会保留参与 Seamless Travel 的 Controller。到最终 World 后，默认 `HandleSeamlessTravelPlayer` 仍会：

```text
创建新的 PlayerController
→ 新 PlayerController 初始化新的 PlayerState
→ OldPC::SeamlessTravelTo(NewPC)
→ NewPC::SeamlessTravelFrom(OldPC)
→ OldPlayerState.Reset()
→ OldPlayerState.SeamlessTravelTo(NewPlayerState)
→ CopyProperties(NewPlayerState)
→ 销毁 OldPlayerState
→ 交换 Player / NetConnection 到 NewPC
```

Lyra 没有覆盖 `HandleSeamlessTravelPlayer`。`ALyraPlayerState::CopyProperties` 只调用 `Super::CopyProperties`，随后是 `//@TODO: Copy stats`。所以静态源码不能证明以下数据自动跨 Seamless Travel 保留：

- `PawnData`；
- PlayerState ASC 对象、已授予 Ability、Attribute 与 Gameplay Effect；
- TeamID / SquadID；
- Lyra 自定义 StatTags；
- 当前 Pawn 和 ASC Avatar。

新 PlayerState 会在新 ExperienceManager 上重新注册 `OnExperienceLoaded`，由目标 Experience 重新设置 PawnData、授予 AbilitySet；新 Pawn 再把新 ASC 的 Avatar 设为自己。这是“重建并重新初始化”，不是“旧 ASC 原样延续”。

### Client 侧

Client 的本地 PlayerController 会被 Seamless Handler 标记保留；其他动态复制 Actor 可能在切换期间被临时带入新 World。但服务器最终创建了新的权威 PlayerState/Pawn，客户端仍需接受销毁/重复制和重新初始化。不能因客户端本地 PC 暂时存活，就把 PlayerState/ASC/Pawn 标成身份稳定。

### GameState 与 Experience

旧 GameMode、GameState 只在进入 Transition World 时由默认列表保留；进入最终 World 时会创建新的 GameMode/GameState。旧 `ULyraExperienceManagerComponent::EndPlay` 停用 Actions 和 Game Feature，请求计数仅在 Editor 多 World 场景做保护；新 GameState 上的 ExperienceManager 重新选择或复制 Experience 并执行加载。

因此 Seamless 的稳定部分主要是网络连接与必要的过渡 Actor，不是完整 Experience 管线和玩法状态。

## 11. Loading Screen 的判定边界

`ULoadingScreenManager` 是 GameInstance Subsystem，只在非 Dedicated Server 创建。它每帧检查：

```text
WorldContext / World 是否存在
→ GameState 是否存在
→ 是否位于 LoadMap
→ 是否有 TravelURL
→ 是否有 PendingNetGame
→ World 是否 BeginPlay
→ 是否正在 Seamless Travel
→ GameState 及其组件是否要求继续显示
→ 外部 Loading Processor 是否要求继续显示
→ LocalPlayer 是否已有 PlayerController
```

Lyra 的两个重要参与者是：

- `ULyraExperienceManagerComponent`：未进入 `Loaded` 时以 `Experience still loading` 保持加载屏；
- `ULyraFrontendStateComponent`：Press Start 或 Main Screen 成功压栈前保持加载屏。

所以 Loading Screen 的语义是“当前客户端尚未达到可交互条件”。它不会自动生成错误消息，也不会证明所有 Game Feature 正确工作。

## 12. Travel / Network 失败恢复

### Engine 恢复

Travel Failure 会通知 GameInstance Blueprint Event、取消 PendingNetGame，并尝试断开。Network Failure 对 Client/Pending 连接通常也会走断开。`HandleDisconnect` 设置绝对 ClientTravel `?closed`；`Browse` 看到 `failed/closed` 后加载 `GameDefaultMap`，即 Lyra 前端图。

前端重新建立后，`ULyraFrontendStateComponent` 检查 `closed`：

- Hard disconnect 时重置 User 状态；
- 无论是否 Hard disconnect，都清理 Session；
- 然后重新走用户初始化、邀请 Join 和 Main Screen Flow。

### 用户可见错误仍有缺口

`UCommonSessionSubsystem::TravelLocalSessionFailure` 当前只记录日志并把 SessionInformation 改为 OutOfGame。源码明确注释：因为之前已广播 Join 成功，暂不再次广播 Join 失败，避免成功后又失败造成混乱。

此外：

- `ULyraGameInstance` C++ 没有实现 Network/Travel Error 处理；
- Engine 只提供 `B_LyraGameInstance` 可实现的 Blueprint Event；
- 当前没有结构化资产导出证明该 Blueprint 是否弹出错误 UI；
- `ULyraFrontendStateComponent` 的 Join 成功分支立即取消前端 Flow，源码也留下“需确认旅行真正完成”的 TODO。

因此当前只能确认“引擎有回到稳定前端图的恢复路径”，不能确认“玩家一定得到准确错误解释”。

## 13. 失败时 Loading Screen 何时能退出

正常网络失败的预期静态路径是：

```text
PendingNetGame / TravelURL 使加载屏保持
→ 失败触发 ?closed
→ 加载默认前端图
→ 新 Frontend Experience 加载
→ Frontend Flow 建立 Press Start 或 Main Screen
→ bShouldShowLoadingScreen=false
→ Loading Screen 退出
```

但以下情况可能不退出或错误退出：

- GameMode 无法确定有效 Experience：Lyra 明确记录“loading screen will stay up forever”；
- Frontend Flow 没有成功压入 Press Start/Main Screen；
- PendingNetGame 或 TravelURL 没有被正确清理；
- Game Feature 激活失败结果被忽略，Experience 仍可能进入 Loaded，导致加载屏退出但功能不完整；
- Blueprint 错误 UI/Widget 栈与跨 World RootLayout 的清理不符合预期。

这些都必须作为失败场景单独验证，不能从成功路径推导。

## 14. 对增量信任模型的约束

网络模式研究说明，权威上下文至少必须包含：

```yaml
target: LyraGame | LyraClient | LyraServer | LyraEditor
net_mode: standalone | listen-server | dedicated-server | client
session_mode: offline | lan | online
travel_mode: hard | seamless
world_role: authority | autonomous-proxy | simulated-proxy
experience_side: client | server | both
transition_map: explicit | temporary-empty
```

还必须区分三种“存续”：

1. **对象身份存续**：同一 UObject/Actor 被带到目标 World；
2. **数据复制存续**：创建新对象，只复制部分字段；
3. **语义重建存续**：由目标 Experience 重新授予能力、设置 PawnData 或建立连接。

Lyra Seamless PlayerState/ASC 主要属于后两类，而不是第一类。未来审查边界不能只显示“使用了 Seamless Travel”，必须列出每个字段和能力的来源。

## 15. 对“最小运行项目”的直接启示

“最小 Lyra 项目”不是单一答案，至少应先分成两个合同：

### 最小 Standalone 合同

- GameInstance / AssetManager；
- 默认 Map 与 GameMode；
- Experience 选择与加载；
- Client + Server Bundle；
- PlayerState/Pawn/ASC/InitState；
- 本地输入与 UI；
- Offline Travel，如需要前端与玩法切换。

### 最小网络合同

在 Standalone 合同之外增加：

- Listen 或 Dedicated 的明确选择；
- Session/连接地址；
- ServerTravel 与远端 ClientTravel；
- PendingNetGame 与失败恢复；
- CurrentExperience 复制和两侧独立加载；
- PlayerState/Pawn/ASC 的复制与旅行重建验证；
- 至少一个远端 Client 的 GameplayReady 验收。

后续最小化应先证明 Standalone 合同，再单独证明网络合同；不能通过删除网络组件后仍能单机运行，就宣称得到“Lyra 的最小运行架构”。

## 16. 可复核源码与配置锚点

项目侧：

- Target：`LyraStarterGame/Source/LyraGame.Target.cs`、`LyraClient.Target.cs`、`LyraServer.Target.cs`
- 默认 Map、OnlineServices、PIE Seamless：`LyraStarterGame/Config/DefaultEngine.ini`
- Host URL：`LyraStarterGame/Plugins/CommonUser/Source/CommonUser/Private/CommonSessionSubsystem.cpp`
- UserFacingExperience：`LyraStarterGame/Source/LyraGame/GameModes/LyraUserFacingExperienceDefinition.cpp`
- Dedicated 启动：`LyraStarterGame/Source/LyraGame/GameModes/LyraGameMode.cpp`
- Experience 两侧 Bundle：`LyraStarterGame/Source/LyraGame/GameModes/LyraExperienceManagerComponent.cpp`
- Seamless 下一局：`LyraStarterGame/Source/LyraGame/System/LyraSystemStatics.cpp`
- PlayerState Copy：`LyraStarterGame/Source/LyraGame/Player/LyraPlayerState.cpp`
- Pawn/ASC 重建：`LyraStarterGame/Source/LyraGame/Character/LyraPawnExtensionComponent.cpp`
- Frontend 恢复：`LyraStarterGame/Source/LyraGame/UI/Frontend/LyraFrontendStateComponent.cpp`
- Loading Screen：`LyraStarterGame/Plugins/CommonLoadingScreen/Source/CommonLoadingScreen/Private/LoadingScreenManager.cpp`

Engine 侧：

- NetMode 推导与 Seamless Handler：`D:/UnrealEngine_5.6/Engine/Source/Runtime/Engine/Private/World.cpp`
- NetMode API：`D:/UnrealEngine_5.6/Engine/Source/Runtime/Engine/Classes/Engine/World.h`
- ServerTravel/Seamless Player：`D:/UnrealEngine_5.6/Engine/Source/Runtime/Engine/Private/GameModeBase.cpp`
- PlayerController Seamless Copy：`D:/UnrealEngine_5.6/Engine/Source/Runtime/Engine/Private/PlayerController.cpp`
- PlayerState CopyProperties：`D:/UnrealEngine_5.6/Engine/Source/Runtime/Engine/Private/PlayerState.cpp`
- Browse/PendingNetGame/LoadMap/Failure：`D:/UnrealEngine_5.6/Engine/Source/Runtime/Engine/Private/UnrealEngine.cpp`

## 17. 待运行与资产验证

1. 分别捕获 Game Target 的 Standalone Offline、Listen LAN/Online 与 Client Join。
2. 捕获独立 `LyraServer` + `LyraClient`，验证 Dedicated 登录、Host、Server Bundle 与 Client Bundle。
3. 用对象唯一标识验证 Hard 与 Seamless 前后 PC、PS、ASC、Pawn、GameState、ExperienceManager 的真实身份。
4. 验证 Seamless 后 PawnData、AbilitySet、Team/Squad、Attribute、Effect 的来源和保留结果。
5. 结构化导出 `B_LyraGameMode_C.bUseSeamlessTravel`。
6. 结构化检查 `B_LyraGameInstance` 是否实现 NetworkError/TravelError，以及错误 UI 行为。
7. 注入 Join 后连接失败、目标 Map 缺失和 Experience 无效，确认 Loading Screen、Session、User 与前端 Flow 的恢复。
8. 验证 Listen Host 本地玩家与远端 Client 的回调顺序不同，但最终都达到目标 Experience/Pawn GameplayReady。
