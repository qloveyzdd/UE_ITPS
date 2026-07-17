# `.uproject` 入口扫描报告

> 生成时间：`2026-07-17T16:26:31+00:00`；Schema：`ue-itps.uproject-structure.v5`

## 项目与引擎身份

| 字段 | 结果 |
|---|---|
| 项目 | `LyraStarterGame` |
| `.uproject` | `E:/UE_ITPS/LyraStarterGame/LyraStarterGame.uproject` |
| FileVersion | `3` |
| EngineAssociation | `{6D46E408-487A-23A8-6BF7-4F8E40277C23}` |
| Engine 解析状态 | `resolved` |
| Engine 解析方法 | `windows-registry:Software\Epic Games\Unreal Engine\Builds:{6D46E408-487A-23A8-6BF7-4F8E40277C23}` |
| Engine 根目录 | `D:/UnrealEngine_5.6` |
| Engine 真实版本 | `5.6.1` |
| 版本证据 | `D:/UnrealEngine_5.6/Engine/Build/Build.version` |

`EngineAssociation` 是关联键，不一定是版本号。真实版本来自所解析 Engine 的 `Build.version`。

本报告的必要性上下文为 `scan / Editor / Win64 / Development`。`scan` 只陈述声明与定位证据，不证明运行或打包必需性。

## `.uproject` 声明对账

- 成功对账的项目模块：2 个
- 扫描到 Target：10 个（Target 不由 `.uproject` 声明）
- 原生项目证据分类：`native-project`
- 插件引用：81 个；声明启用 69；声明禁用 12；已定位 69
- 当前 Win64/Editor 上启用且适用：68 个；已定位 66 个

### 成功对账的项目模块

| Module | Type | LoadingPhase | Build.cs | 入口候选 | 状态 |
|---|---|---|---|---:|---|
| `LyraGame` | `Runtime` | `Default` | `E:/UE_ITPS/LyraStarterGame/Source/LyraGame/LyraGame.Build.cs` | 1 | `resolved` |
| `LyraEditor` | `Editor` | `Default` | `E:/UE_ITPS/LyraStarterGame/Source/LyraEditor/LyraEditor.Build.cs` | 1 | `resolved` |

### Target 文件（扫描发现）

- `LyraClient` → `E:/UE_ITPS/LyraStarterGame/Source/LyraClient.Target.cs`
- `LyraEditor` → `E:/UE_ITPS/LyraStarterGame/Source/LyraEditor.Target.cs`
- `LyraGame` → `E:/UE_ITPS/LyraStarterGame/Source/LyraGame.Target.cs`
- `LyraGameEOS` → `E:/UE_ITPS/LyraStarterGame/Source/LyraGameEOS.Target.cs`
- `LyraGameSteam` → `E:/UE_ITPS/LyraStarterGame/Source/LyraGameSteam.Target.cs`
- `LyraGameSteamEOS` → `E:/UE_ITPS/LyraStarterGame/Source/LyraGameSteamEOS.Target.cs`
- `LyraServer` → `E:/UE_ITPS/LyraStarterGame/Source/LyraServer.Target.cs`
- `LyraServerEOS` → `E:/UE_ITPS/LyraStarterGame/Source/LyraServerEOS.Target.cs`
- `LyraServerSteam` → `E:/UE_ITPS/LyraStarterGame/Source/LyraServerSteam.Target.cs`
- `LyraServerSteamEOS` → `E:/UE_ITPS/LyraStarterGame/Source/LyraServerSteamEOS.Target.cs`

### `.uproject` 直接引用的项目本地插件描述符

- `CommonLoadingScreen` → `Plugins/CommonLoadingScreen/CommonLoadingScreen.uplugin`
- `ModularGameplayActors` → `Plugins/ModularGameplayActors/ModularGameplayActors.uplugin`
- `GameSettings` → `Plugins/GameSettings/GameSettings.uplugin`
- `CommonUser` → `Plugins/CommonUser/CommonUser.uplugin`
- `CommonGame` → `Plugins/CommonGame/CommonGame.uplugin`
- `GameSubtitles` → `Plugins/GameSubtitles/GameSubtitles.uplugin`
- `PocketWorlds` → `Plugins/PocketWorlds/PocketWorlds.uplugin`
- `UIExtension` → `Plugins/UIExtension/UIExtension.uplugin`
- `AsyncMixin` → `Plugins/AsyncMixin/AsyncMixin.uplugin`
- `GameplayMessageRouter` → `Plugins/GameplayMessageRouter/GameplayMessageRouter.uplugin`
- `ShooterCore` → `Plugins/GameFeatures/ShooterCore/ShooterCore.uplugin`
- `ShooterMaps` → `Plugins/GameFeatures/ShooterMaps/ShooterMaps.uplugin`
- `TopDownArena` → `Plugins/GameFeatures/TopDownArena/TopDownArena.uplugin`
- `ShooterExplorer` → `Plugins/GameFeatures/ShooterExplorer/ShooterExplorer.uplugin`
- `ShooterTests` → `Plugins/GameFeatures/ShooterTests/ShooterTests.uplugin`

其余已定位引用中，54 个来自 Engine；完整逐项结果保存在机器可读 JSON 中。

## 项目根目录事实

项目根：`E:/UE_ITPS/LyraStarterGame`

| 项目相对路径 | 约定角色 | 实际类型 | 含义 |
|---|---|---|---|
| `LyraStarterGame.uproject` | `project-descriptor` | `file` | 所选项目描述符 |
| `Source` | `source` | `directory` | UE 项目 C++ Target 与 Module 的约定目录 |
| `Config` | `configuration` | `directory` | UE 项目配置的约定目录 |
| `Content` | `content` | `directory` | UE 项目资产与地图的约定目录 |
| `Plugins` | `plugins` | `directory` | UE 项目本地插件的约定目录 |
| `Build` | `build` | `directory` | UE 项目构建、自动化与平台输入的约定目录 |
| `Platforms` | `platform-extensions` | `directory` | UE 项目级平台扩展的约定目录 |
| `Binaries` | `binaries` | `directory` | 项目二进制目录；本报告不判断来源、必要性或删除安全性 |
| `Intermediate` | `build-intermediate` | `directory` | UBT/UHT 与构建中间状态的约定目录 |
| `LyraStarterGame.sln` | `ide-workspace` | `file` | IDE 工作区文件的约定位置 |
| `DerivedDataCache` | `derived-data-cache` | `directory` | 资产派生缓存的约定目录 |
| `Saved` | `saved-state` | `directory` | 日志、自动保存与本地运行状态目录 |
| `.vs` | `visual-studio-state` | `directory` | Visual Studio 本地状态目录 |
| `.idea` | `jetbrains-state` | `directory` | JetBrains 本地状态目录 |

## 当前结构树

```text
LyraStarterGame/
├─ LyraStarterGame.uproject        # 唯一项目入口描述符
├─ Source/                    # UE 约定的 C++ 代码目录
│  ├─ LyraGame/LyraGame.Build.cs
│  └─ LyraEditor/LyraEditor.Build.cs
├─ Plugins/                   # UE 约定的项目插件目录
├─ Config/                    # UE 约定的项目配置目录
├─ Content/                   # UE 约定的项目资产目录
├─ Build/                     # UE 约定的项目构建目录
├─ Platforms/                 # UE 约定的平台扩展目录
├─ Binaries/                  # 项目二进制目录（本层不判断来源）
├─ Intermediate/              # 构建中间状态目录
├─ DerivedDataCache/          # 缓存
└─ Saved/                     # 日志与本地运行状态
```

## 解释边界

职责：Compose the focused UE project inspection results into one versioned entry snapshot.

- `.uproject` 不声明 Target.cs；Target 来自对 Source 的扫描发现。
- `.uproject` 不给出 Build.cs 模块依赖图，也不展开 `.uplugin` 的传递依赖。
- 目录存在不能证明它在运行时被使用、资产可达，或属于最小项目必需项。
- Module 下的 Public/Private 是 UE 约定，不是 `.uproject` 强制路径。
- 当前只解析 `.uproject` 的显式 Plugin 引用；传递依赖闭包属于下一层扫描。
- 项目外 Additional* 目录默认只报告 skipped_external，不越界遍历。
- Binaries 对源码 Lyra 是生成物；对纯预编译项目可能是条件输入。

验证状态：`warning`；错误 0；警告 2。

### 诊断

- `warning` / `plugin-not-found`：Plugin D3DExternalGPUStatistics is enabled for Win64/Editor but was not resolved
- `warning` / `plugin-not-found`：Plugin EOSReservedHooks is enabled for Win64/Editor but was not resolved
