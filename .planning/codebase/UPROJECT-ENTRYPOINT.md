# `.uproject` 入口扫描报告

> 生成时间：`2026-07-15T12:54:12+00:00`；Schema：`ue-itps.uproject-structure.v1`

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

- 项目模块：2 个
- 扫描到 Target：10 个（Target 不由 `.uproject` 声明）
- 原生项目证据：根 `Source/*.Target.cs` 为 10 个；分类 `native-project`
- 插件引用：81 个；启用 69；禁用 12；已定位 69
- 当前 Win64/Editor 上启用且适用：68 个；已定位 66 个

### 项目模块

| Module | Type | LoadingPhase | Build.cs | 入口候选 | 状态 |
|---|---|---|---|---:|---|
| `LyraGame` | `Runtime` | `Default` | `E:/UE_ITPS/LyraStarterGame/Source/LyraGame/LyraGame.Build.cs` | 1 | `complete` |
| `LyraEditor` | `Editor` | `Default` | `E:/UE_ITPS/LyraStarterGame/Source/LyraEditor/LyraEditor.Build.cs` | 1 | `complete` |

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

- `CommonLoadingScreen` → `E:/UE_ITPS/LyraStarterGame/Plugins/CommonLoadingScreen/CommonLoadingScreen.uplugin`
- `ModularGameplayActors` → `E:/UE_ITPS/LyraStarterGame/Plugins/ModularGameplayActors/ModularGameplayActors.uplugin`
- `GameSettings` → `E:/UE_ITPS/LyraStarterGame/Plugins/GameSettings/GameSettings.uplugin`
- `CommonUser` → `E:/UE_ITPS/LyraStarterGame/Plugins/CommonUser/CommonUser.uplugin`
- `CommonGame` → `E:/UE_ITPS/LyraStarterGame/Plugins/CommonGame/CommonGame.uplugin`
- `GameSubtitles` → `E:/UE_ITPS/LyraStarterGame/Plugins/GameSubtitles/GameSubtitles.uplugin`
- `PocketWorlds` → `E:/UE_ITPS/LyraStarterGame/Plugins/PocketWorlds/PocketWorlds.uplugin`
- `UIExtension` → `E:/UE_ITPS/LyraStarterGame/Plugins/UIExtension/UIExtension.uplugin`
- `AsyncMixin` → `E:/UE_ITPS/LyraStarterGame/Plugins/AsyncMixin/AsyncMixin.uplugin`
- `GameplayMessageRouter` → `E:/UE_ITPS/LyraStarterGame/Plugins/GameplayMessageRouter/GameplayMessageRouter.uplugin`
- `ShooterCore` → `E:/UE_ITPS/LyraStarterGame/Plugins/GameFeatures/ShooterCore/ShooterCore.uplugin`
- `ShooterMaps` → `E:/UE_ITPS/LyraStarterGame/Plugins/GameFeatures/ShooterMaps/ShooterMaps.uplugin`
- `TopDownArena` → `E:/UE_ITPS/LyraStarterGame/Plugins/GameFeatures/TopDownArena/TopDownArena.uplugin`
- `ShooterExplorer` → `E:/UE_ITPS/LyraStarterGame/Plugins/GameFeatures/ShooterExplorer/ShooterExplorer.uplugin`
- `ShooterTests` → `E:/UE_ITPS/LyraStarterGame/Plugins/GameFeatures/ShooterTests/ShooterTests.uplugin`

其余已定位引用中，54 个来自 Engine；完整逐项结果保存在机器可读 JSON 中。

## 项目根结构分类

| 相对路径 | 分类 | 存在 | 含义 |
|---|---|---|---|
| `LyraStarterGame.uproject` | `descriptor-mandated` | 是 | 项目身份，以及顶层 Module/Plugin 声明 |
| `Source` | `conditional` | 是 | 项目拥有 C++ Target 或 Module 时需要 |
| `Config` | `conditional` | 是 | 项目配置层级与运行默认值 |
| `Content` | `conditional` | 是 | 项目自有资产与地图 |
| `Plugins` | `conditional` | 是 | 项目本地插件的描述符、代码、配置与资产 |
| `Build` | `conditional` | 是 | BuildGraph、自动化、打包、平台与测试输入 |
| `Platforms` | `conditional` | 是 | 项目级平台扩展与覆盖 |
| `Binaries` | `generated/conditional` | 是 | 源码项目中通常可重建；纯预编译分发中可能是条件输入 |
| `Intermediate` | `generated` | 是 | UBT/UHT 与构建中间状态 |
| `DerivedDataCache` | `cache` | 是 | 资产派生缓存 |
| `Saved` | `runtime-state` | 是 | 日志、自动保存、Cook 数据与本地运行输出 |
| `LyraStarterGame.sln` | `generated` | 是 | 由项目规则生成的 IDE 工作区 |
| `.vs` | `local-state` | 是 | Visual Studio 本地状态 |
| `.idea` | `local-state` | 是 | JetBrains 本地状态 |

## 当前结构树

```text
LyraStarterGame/
├─ LyraStarterGame.uproject        # 唯一项目入口描述符
├─ Source/                    # Target 与项目 C++ Module（条件必需）
│  ├─ LyraGame/LyraGame.Build.cs
│  └─ LyraEditor/LyraEditor.Build.cs
├─ Plugins/                   # 项目本地插件（存在引用时需要）
├─ Config/                    # 项目配置输入
├─ Content/                   # 项目资产输入
├─ Build/                     # 自动化/测试/打包输入
├─ Platforms/                 # 平台扩展输入
├─ Binaries/                  # 通常为生成物；纯预编译项目例外
├─ Intermediate/              # 生成物
├─ DerivedDataCache/          # 缓存
└─ Saved/                     # 日志与本地运行状态
```

## 解释边界

- `.uproject` 不声明 Target.cs；Target 来自对 Source 的扫描发现。
- `.uproject` 不给出 Build.cs 模块依赖图，也不展开 `.uplugin` 的传递依赖。
- 目录存在不能证明它在运行时被使用、资产可达，或属于最小项目必需项。
- Module 下的 Public/Private 是 UE 约定，不是 `.uproject` 强制路径。
- 当前只解析 `.uproject` 的显式 Plugin 引用；传递依赖闭包属于下一层扫描。
- 项目外 Additional* 目录默认只报告 skipped_external，不越界遍历。
- Binaries 对源码 Lyra 是生成物；对纯预编译项目可能是条件输入。

验证状态：`ok`；错误 0；警告 2。

### 诊断

- `warning` / `plugin-not-found`：Plugin D3DExternalGPUStatistics is enabled for Win64/Editor but was not resolved
- `warning` / `plugin-not-found`：Plugin EOSReservedHooks is enabled for Win64/Editor but was not resolved
