---
mapped_at: 2026-07-15
scope: LyraStarterGame
status: static-inventory-verified
---

# Lyra 工程栈与依赖全景

## 工程栈

| 层 | 当前基线 | 主要职责 |
|---|---|---|
| Engine | UE `5.6.1-0+UE5`，源码提交 `cdda65ce` | UObject、World、Gameplay Framework、渲染、网络、资产与 Editor |
| 构建 | UBT/UHT，Build Settings V5 | Target、Module、反射代码和链接 |
| C++ 工具链 | VS 2022 Build Tools、MSVC `14.38.33145` | Win64 原生编译 |
| 平台 SDK | Windows SDK `10.0.22621.0` | Win64 编译与资源工具 |
| 托管工具 | Engine Bundled .NET SDK `8.0.300` | UBT、AutomationTool 与构建脚本 |
| 项目核心 | `LyraGame`、`LyraEditor` | 稳定项目壳、跨 Experience 框架与 Editor 扩展 |
| 通用项目插件 | 12 个项目本地插件 | UI、用户、设置、消息、加载、模块化 Actor 等基础设施 |
| Game Feature | 5 个显式加载插件 | Shooter、地图、测试和 TopDown 可选玩法 |
| 数据/资产 | `.uasset`、`.umap`、Primary Data Asset、INI | Experience、PawnData、AbilitySet、输入、UI、地图和配置 |

## Target 全景

`Source/` 下有 10 个 Target：

| Target | 类型 | 特殊配置 |
|---|---|---|
| `LyraGame` | Game | 所有 Game Target 的共享基类 |
| `LyraClient` | Client | 只包含 `LyraGame` |
| `LyraEditor` | Editor | 包含 `LyraGame`、`LyraEditor`，额外启用 `RemoteSession` |
| `LyraServer` | Server | Dedicated Server，Shipping 仍启用 checks |
| `LyraGameEOS` | Game | `CustomConfig = EOS` |
| `LyraGameSteam` | Game | `CustomConfig = Steam` |
| `LyraGameSteamEOS` | Game | `CustomConfig = SteamEOS` |
| `LyraServerEOS` | Server | `CustomConfig = EOS` |
| `LyraServerSteam` | Server | `CustomConfig = Steam` |
| `LyraServerSteamEOS` | Server | `CustomConfig = SteamEOS` |

`LyraGameTarget.ApplySharedLyraTargetSettings` 统一 Build Settings、Include Order、Shipping/Test 限制和 Game Feature 编译选择。Game Feature 的“是否编进 Target”和“运行时是否 Active”是两个不同问题。

## Module 全景

### 项目模块

| Module | 类型 | 边界 |
|---|---|---|
| `LyraGame` | Runtime | 跨 Experience 的项目运行时框架与通用游戏系统 |
| `LyraEditor` | Editor | 数据校验、命令、Editor 工具和开发工作流 |

`LyraGame` 的公共依赖锚点包括 `GameplayAbilities`、`GameplayTags`、`GameplayTasks`、`GameFeatures`、`ModularGameplay`、`ModularGameplayActors`、`DataRegistry`、`ReplicationGraph`、`Niagara` 和 `PhysicsCore`。它在私有边界集成 `CommonGame`、`CommonUI`、`CommonUser`、`EnhancedInput`、`GameplayMessageRuntime`、`GameSettings`、`GameSubtitles`、`UIExtension`、网络、音频和 Gauntlet。

这说明 `LyraGame` 不是单一玩法模块，而是项目壳和多套 Engine/项目插件之间的整合层。

### 项目本地插件模块

17 个 `.uplugin` 共声明 16 个本地 C++ Module；另有 3 个纯内容插件没有 Module。

| 类别 | 插件/Module |
|---|---|
| 异步与启动 | `AsyncMixin`、`CommonLoadingScreen`、`CommonStartupLoadingScreen` |
| 用户与 UI | `CommonGame`、`CommonUser`、`GameSettings`、`GameSubtitles`、`UIExtension` |
| 消息与模块化 | `GameplayMessageRuntime`、`GameplayMessageNodes`、`ModularGameplayActors` |
| 独立工具/世界 | `PocketWorlds`、`LyraExtTool` |
| Game Feature 代码 | `ShooterCoreRuntime`、`ShooterTestsRuntime`、`TopDownArenaRuntime` |
| 纯内容 | `LyraExampleContent`、`ShooterExplorer`、`ShooterMaps` |

`ShooterCoreRuntime` 的公共依赖只有 `Core`、`LyraGame`、`CommonGame`、`ModularGameplay`，具体 Ability、UI、输入、消息、字幕等作为私有实现依赖。这是“项目壳提供稳定扩展面、玩法插件消费扩展面”的直接 Build.cs 证据。

## Plugin 全景

### `.uproject` 引用

`LyraStarterGame.uproject` 共引用 81 个插件：69 个启用，12 个显式禁用。重要分组如下：

| 能力域 | 代表插件 |
|---|---|
| Gameplay/模块化 | `GameplayAbilities`、`GameFeatures`、`ModularGameplay`、`EnhancedInput`、`DataRegistry` |
| UI/用户流程 | `CommonUI`、`CommonGame`、`CommonUser`、`GameSettings`、`UIExtension` |
| 网络/在线 | `ReplicationGraph`、`OnlineFramework`、EOS、Steam、Null、OSS Adapter |
| AI/交互 | `GameplayInteractions`、`SmartObjects`、`GameplayStateTree`、`GameplayBehaviors` |
| 内容表现 | `Niagara`、音频插件、Water、Animation Warping、Locomotion Library |
| 测试/诊断 | `Gauntlet`、`RuntimeTests`、`AutomatedPerfTesting`、`GameplayInsights` |
| 项目玩法 | `ShooterCore`、`ShooterMaps`、`ShooterExplorer`、`ShooterTests`、`TopDownArena` |

`MovieRenderPipeline` 和 `MoviePipelineMaskRenderPass` 只允许 Editor Target；`PlayFabParty` 只允许 XB1/XSX/WinGDK；`D3DExternalGPUStatistics` 与 `EOSReservedHooks` 标记为 Optional。插件被写为 Enabled 不等于它在每个 Target、平台和运行阶段都实际加载。

### 项目本地通用插件

| 插件 | 主要职责 |
|---|---|
| `AsyncMixin` | UObject 异步操作辅助 |
| `CommonGame` | CommonUI 与项目游戏层的公共连接 |
| `CommonLoadingScreen` | 加载屏与 PreLoadingScreen |
| `CommonUser` | 本地用户、登录和在线服务抽象 |
| `GameplayMessageRouter` | 基于 Gameplay Tag 的消息总线与 Blueprint 节点 |
| `GameSettings` | 设置注册、数据源与设置 UI 模型 |
| `GameSubtitles` | 字幕数据与显示支持 |
| `LyraExampleContent` | 多玩法共享的纯内容样例资产 |
| `LyraExtTool` | Editor 扩展工具 |
| `ModularGameplayActors` | Modular Gameplay 的 Actor 基类封装 |
| `PocketWorlds` | Pocket World/Level Instance 与捕获 |
| `UIExtension` | 基于 Tag/Extension Point 的 UI 注入 |

### Game Feature 插件

5 个 Game Feature 全部满足：

```text
EnabledByDefault = false
ExplicitlyLoaded = true
BuiltInInitialFeatureState = Registered
```

| 插件 | 代码 | 内容 | 直接插件依赖重点 |
|---|---|---|---|
| `ShooterCore` | `ShooterCoreRuntime` | 260 个资产/地图 | GAS、ModularGameplay、消息、CommonUI/CommonGame、输入、字幕 |
| `ShooterExplorer` | 无 | 51 个资产 | `ShooterCore`、`LyraExampleContent` |
| `ShooterMaps` | 无 | 5,330 个资产/外部 Actor | `ShooterCore`、`LyraExampleContent` |
| `ShooterTests` | `ShooterTestsRuntime` | 35 个资产 | ShooterCore、CQTest、输入与测试插件；Shipping 禁止该 Module |
| `TopDownArena` | `TopDownArenaRuntime` | 87 个资产 | GAS、`LyraExampleContent`、Niagara |

这里的 `Registered` 只表示可被 Game Features Subsystem 发现。Experience 决定需要激活哪些插件；是否已经进入 `Active` 必须由运行日志或测试证明。

## 依赖方向

静态工程层面的主要方向是：

```text
Engine Plugins
    ↑
Project-local infrastructure plugins
    ↑
LyraGame stable project shell
    ↑
Game Feature runtime modules
    ↑
Feature-owned assets and Experiences
```

这不是严格的单向分层：例如 `LyraGame` 私有依赖多个项目本地插件，而 `ShooterCoreRuntime` 又依赖 `LyraGame`。研究和未来图谱中必须记录真实 Module 边，不能只按目录层级推断依赖。

## 当前边界

本文件只说明“工程由什么组成”和 Build/Plugin 描述文件声明了什么，不证明启动顺序、对象生命周期、网络执行端或运行时功能可用性。后者分别归档到 `ARCHITECTURE.md`、后续 `PIPELINES.md` 和 `TESTING.md`。
