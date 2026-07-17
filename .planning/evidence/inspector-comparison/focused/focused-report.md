# UE 项目聚焦检查报告（B 组）

## 范围与证据

- 项目：`E:/UE_ITPS/LyraStarterGame/LyraStarterGame.uproject`
- 固定 Plugin 上下文：`operation=scan`、`platform=Win64`、`target-type=Editor`
- `configuration` 未传入：聚焦 `ue_resolve_plugins.py` 不接受、也不评估 configuration；configuration 只属于完整快照上下文。
- 本报告的 UE 项目事实仅来自 `raw/` 中七份聚焦 CLI 原始标准输出。
- 未运行或导入 `inspect_uproject.py`、`ue_project_tools.snapshot`、`ue_project_tools.report`。

## 执行记录

| # | CLI | 退出码 | 执行时间（ms） | stdout 大小（bytes） |
|---:|---|---:|---:|---:|
| 1 | `ue_find_projects.py` | 0 | 223.910 | 572 |
| 2 | `ue_read_project_descriptor.py` | 0 | 44.805 | 4,950 |
| 3 | `ue_resolve_engine.py` | 0 | 43.108 | 1,433 |
| 4 | `ue_inspect_modules.py` | 0 | 98.418 | 2,391 |
| 5 | `ue_inspect_targets.py` | 0 | 47.381 | 3,299 |
| 6 | `ue_resolve_plugins.py` | 0 | 738.224 | 18,925 |
| 7 | `ue_classify_project_paths.py` | 0 | 45.311 | 3,408 |

七个 CLI 总执行时间：**1,293.729 ms**。所有命令 stderr 均为空。完整命令行记录见 `execution-metrics.json`。

## Validation 总览

| 模块 | schema | 状态 | 问题数 |
|---|---|---|---:|
| 项目发现 | `ue-itps.project-discovery.v2` | `ok` | 0 |
| 描述符 | `ue-itps.project-descriptor.v4` | `ok` | 0 |
| Engine | `ue-itps.engine-resolution.v2` | `ok` | 0 |
| Module | `ue-itps.project-modules.v4` | `ok` | 0 |
| Target | `ue-itps.project-targets.v2` | `ok` | 0 |
| Plugin | `ue-itps.project-plugin-references.v4` | `warning` | 2 |
| 路径分类 | `ue-itps.project-paths.v3` | `ok` | 0 |

全部诊断如下；七份结果中没有其他 validation 问题：

1. `warning / plugin-not-found / /Plugins/5`：`Plugin D3DExternalGPUStatistics is enabled for Win64/Editor but was not resolved`
2. `warning / plugin-not-found / /Plugins/41`：`Plugin EOSReservedHooks is enabled for Win64/Editor but was not resolved`

`warning` 表示扫描已完成但存在非阻塞问题，不等同于 `ok`，也不代表进程失败。

## 1. 项目发现

- 搜索根：`E:/UE_ITPS`
- 状态：`selected`
- 候选数：1
- 唯一候选：`E:/UE_ITPS/LyraStarterGame/LyraStarterGame.uproject`
- Validation：`ok`，0 个问题。

Limits：

- Responsibility: `Discover .uproject files under one search root.`
- `The tool does not choose between multiple candidates.`
- `Discovery does not parse, validate, build, or run a project.`

## 2. 项目描述符

- 项目名：`LyraStarterGame`
- 项目根：`E:/UE_ITPS/LyraStarterGame`
- 描述符：`E:/UE_ITPS/LyraStarterGame/LyraStarterGame.uproject`
- 描述符 SHA-256：`a42824b8d829dc00b290ada29ba94cb5f5cbdfe517cdace2b84714cf5cde27ff`
- FileVersion：3
- EngineAssociation：`{6D46E408-487A-23A8-6BF7-4F8E40277C23}`
- Category：`Samples`
- Description：空字符串
- 声明 Module：`LyraGame`、`LyraEditor`
- AdditionalRootDirectories：空
- AdditionalPluginDirectories：空
- Descriptor option：`EpicSampleNameHash=451731683`
- 顶层字段：`Category`、`Description`、`EngineAssociation`、`EpicSampleNameHash`、`FileVersion`、`Modules`、`Plugins`
- 未建模顶层字段：无

Plugin 声明投影：

- 简单 enabled（63）：`ActorPalette`, `AESGCMHandlerComponent`, `DTLSHandlerComponent`, `GameplayAbilities`, `Gauntlet`, `CommonLoadingScreen`, `CommonConversation`, `GameFeatures`, `ModularGameplay`, `ModularGameplayActors`, `EnhancedInput`, `Volumetrics`, `DataRegistry`, `ReplicationGraph`, `SignificanceManager`, `Niagara`, `Water`, `CommonUI`, `ControlFlows`, `GameSettings`, `CommonUser`, `CommonGame`, `GameSubtitles`, `PocketWorlds`, `UIExtension`, `AsyncMixin`, `Metasound`, `OnlineFramework`, `OnlineSubsystemEOS`, `OnlineServicesEOS`, `OnlineServicesNull`, `OnlineServicesOSSAdapter`, `OnlineSubsystemSteam`, `SocketSubsystemSteamIP`, `GameplayMessageRouter`, `SteamSockets`, `AssetReferenceRestrictions`, `ModelingToolsEditorMode`, `GeometryScripting`, `AnimationLocomotionLibrary`, `AudioModulation`, `AudioGameplayVolume`, `AudioGameplay`, `SoundUtilities`, `AnimationWarping`, `AssetSearch`, `GameplayInsights`, `Spatialization`, `ShooterCore`, `ShooterMaps`, `TopDownArena`, `FunctionalTestingEditor`, `ShooterExplorer`, `ShooterTests`, `GameplayInteractions`, `SmartObjects`, `ContextualAnimation`, `GameplayBehaviorSmartObjects`, `GameplayStateTree`, `GameplayBehaviors`, `RuntimeTests`, `AutomatedPerfTesting`, `Reflex`。
- 简单 disabled（11）：`MagicLeap`, `MagicLeapMedia`, `MagicLeapPassableWorld`, `OpenXREyeTracker`, `OpenXRHandTracking`, `OpenXRHMD`, `SteamVR`, `GearVR`, `MLSDK`, `ResonanceAudio`, `RuntimePhysXCooking`。
- Extended（7）：

| 名称 | declared_enabled | pointer | 额外字段 |
|---|---:|---|---|
| `D3DExternalGPUStatistics` | true | `/Plugins/5` | `Optional`, `SupportedTargetPlatforms` |
| `WinDualShock` | true | `/Plugins/12` | `SupportedTargetPlatforms` |
| `LuminPlatformFeatures` | false | `/Plugins/37` | `SupportedTargetPlatforms` |
| `PlayFabParty` | true | `/Plugins/40` | `PlatformAllowList`, `SupportedTargetPlatforms` |
| `EOSReservedHooks` | true | `/Plugins/41` | `Optional` |
| `MovieRenderPipeline` | true | `/Plugins/59` | `TargetAllowList` |
| `MoviePipelineMaskRenderPass` | true | `/Plugins/60` | `TargetAllowList` |

Validation：`ok`，0 个问题。

Limits：

- Responsibility: `Read explicit facts declared by one .uproject file.`
- `The result does not locate Engine, Module, Target, or Plugin files.`
- `Extended Plugin declarations are indexed, not fully interpreted.`
- `Unmodeled top-level fields are preserved without being judged invalid.`

## 3. Engine 解析

- 原始关联键：`{6D46E408-487A-23A8-6BF7-4F8E40277C23}`
- 状态：`resolved`
- 解析方法：`windows-registry:Software\Epic Games\Unreal Engine\Builds:{6D46E408-487A-23A8-6BF7-4F8E40277C23}`
- 唯一解析候选：`D:/UnrealEngine_5.6`（同一注册表来源）
- Engine root：`D:/UnrealEngine_5.6`
- Build.version：`D:/UnrealEngine_5.6/Engine/Build/Build.version`
- Build.version SHA-256：`0b835329767015bfd93fc7222c02c1c5c83c830b33caf35ecd824d7b848af333`
- 实际版本：`5.6.1`
- Build：Major 5、Minor 6、Patch 1、Changelist 0、CompatibleChangelist 43139311、IsLicenseeVersion 0、IsPromotedBuild 0、BranchName `UE5`
- Validation：`ok`，0 个问题。

Limits：

- Responsibility: `Resolve EngineAssociation to one Engine root and read Build.version.`
- `EngineAssociation is an association key, not authoritative version evidence.`
- `The result does not prove that the project builds or runs with the Engine.`
- `Registry and ancestor lookup are static resolution mechanisms only.`

## 4. Module 检查

协调后的 Module 数：2。

| Module | Type | LoadingPhase | AdditionalDependencies | Build.cs（SHA-256） | Entrypoint |
|---|---|---|---|---|---|
| `LyraGame` | `Runtime` | `Default` | `DeveloperSettings`, `Engine` | `E:/UE_ITPS/LyraStarterGame/Source/LyraGame/LyraGame.Build.cs` (`7ca8c09fc1ff65e744c08d025715850a236b40827ef3d5b6dda45b5ef70500ca`, conventional=true) | `LyraGameModule.cpp`: `IMPLEMENT_PRIMARY_GAME_MODULE`, `FLyraGameModule`, `LyraGame` |
| `LyraEditor` | `Editor` | `Default` | 无 | `E:/UE_ITPS/LyraStarterGame/Source/LyraEditor/LyraEditor.Build.cs` (`d4fbc5c74a3b2f198b2360912fd9b4c725bc6a7dec699b0784b742b72b37e0dc`, conventional=true) | `LyraEditor.cpp`: `IMPLEMENT_MODULE`, `FLyraEditorModule`, `LyraEditor` |

两项 Build rules 状态均为 `resolved`，描述符指针分别为 `/Modules/0`、`/Modules/1`。Validation：`ok`，0 个问题。

Limits：

- Responsibility: `Reconcile declared project Modules with Build.cs and entrypoint evidence.`
- `Build.cs location is discovered by basename; Source/<Name>/<Name>.Build.cs is only conventional.`
- `AdditionalDependencies does not replace Build.cs dependency analysis.`
- `The result does not evaluate UBT rules, compile Modules, or prove runtime loading.`

## 5. Target 检查

分类：`native-project`。发现 10 个 Target，均为 root target：

| Target | 文件 | SHA-256 |
|---|---|---|
| `LyraClient` | `E:/UE_ITPS/LyraStarterGame/Source/LyraClient.Target.cs` | `c03c1292e97656715d59b39489b3e2a2f068fa30395cda98020af4a02c1f234e` |
| `LyraEditor` | `E:/UE_ITPS/LyraStarterGame/Source/LyraEditor.Target.cs` | `ea5883e6701ef8c8e4ac41f562fc851bd80349e826e750c0419ffe4e731e5206` |
| `LyraGame` | `E:/UE_ITPS/LyraStarterGame/Source/LyraGame.Target.cs` | `2ad574553cd0290f875a572ae6eb48b4e33c1468767837ccc33b6d15bc821ef1` |
| `LyraGameEOS` | `E:/UE_ITPS/LyraStarterGame/Source/LyraGameEOS.Target.cs` | `02b60faced294e29fcc2b487efea21f7c79ba7210a742033bc3579b7ef0e3b6a` |
| `LyraGameSteam` | `E:/UE_ITPS/LyraStarterGame/Source/LyraGameSteam.Target.cs` | `67cc373dd543e32dd3547b3a31fbc2b7491299859db65f411ba2a45c1d6ffad3` |
| `LyraGameSteamEOS` | `E:/UE_ITPS/LyraStarterGame/Source/LyraGameSteamEOS.Target.cs` | `a3e3288d0b54c08bc21e25d02f6c084183b0b609d904a9ee8d13957e67b485db` |
| `LyraServer` | `E:/UE_ITPS/LyraStarterGame/Source/LyraServer.Target.cs` | `c2ceb2e9ab2e91efc119be39f019e3919d27b6e33b3aed0cdfadb20bd1b58115` |
| `LyraServerEOS` | `E:/UE_ITPS/LyraStarterGame/Source/LyraServerEOS.Target.cs` | `7098c368de549da4ee8433ae46965f5c020bdcb59f649e2109f16584ca1abf10` |
| `LyraServerSteam` | `E:/UE_ITPS/LyraStarterGame/Source/LyraServerSteam.Target.cs` | `acf25fb199a5e152c855069b9f64c320cbffc06704f7bfa4a9f650242d6481b5` |
| `LyraServerSteamEOS` | `E:/UE_ITPS/LyraStarterGame/Source/LyraServerSteamEOS.Target.cs` | `92ae2cf2d01ef42f1e0c52863618dec8f14689801b45eba64257a468e18da4a0` |

Validation：`ok`，0 个问题。

Limits：

- Responsibility: `Discover project Target.cs files, validate their placement, and classify native Target evidence.`
- `native-project means at least one Source/*.Target.cs file was discovered.`
- `No root Target produces undetermined-no-native-target; it does not prove the project is Blueprint-only.`
- `A Target in a Source subdirectory is supported by UBT and is not invalid by itself; nested-only placement is a warning.`
- `Root and nested Targets together produce a distinct placement warning.`
- `Target files are discovered but TargetRules are not evaluated.`
- `Temporary or hybrid Target reasons require UBT-level analysis.`

## 6. Plugin 解析

### Profile 与一致性

- Profile：`operation=scan`、`platform=Win64`、`target_type=Editor`
- Project root：`E:/UE_ITPS/LyraStarterGame`
- Engine root：`D:/UnrealEngine_5.6`
- Project descriptor：`LyraStarterGame.uproject`
- Plugin 结果中的描述符 SHA-256：`a42824b8d829dc00b290ada29ba94cb5f5cbdfe517cdace2b84714cf5cde27ff`
- 与 descriptor 结果 SHA-256 比较：**一致**；因此不需要丢弃结果或重读。
- AdditionalPluginDirectories：空。
- `configuration`：未提供，因为聚焦 Plugin CLI 不接受该参数；其 applicability 仅评估 platform 与 target filters，configuration 与更深层 UBT policy 不在范围内。

### 计数与解析结果

- 直接引用总数：81
- declared enabled：69；declared disabled：12
- resolved：69；not-found：12
- 对当前上下文 declared-enabled 且 applicable：68
- 对当前上下文 declared-enabled、applicable 且 resolved：66
- Project-origin descriptor：15；Engine-origin descriptor：54

已解析的 project-origin Plugin（15）：`CommonLoadingScreen`, `ModularGameplayActors`, `GameSettings`, `CommonUser`, `CommonGame`, `GameSubtitles`, `PocketWorlds`, `UIExtension`, `AsyncMixin`, `GameplayMessageRouter`, `ShooterCore`, `ShooterMaps`, `TopDownArena`, `ShooterExplorer`, `ShooterTests`。

已解析的 engine-origin Plugin（54）：`ActorPalette`, `AESGCMHandlerComponent`, `DTLSHandlerComponent`, `GameplayAbilities`, `Gauntlet`, `CommonConversation`, `GameFeatures`, `ModularGameplay`, `EnhancedInput`, `WinDualShock`, `Volumetrics`, `DataRegistry`, `ReplicationGraph`, `SignificanceManager`, `Niagara`, `Water`, `CommonUI`, `ControlFlows`, `Metasound`, `OpenXREyeTracker`, `OpenXRHandTracking`, `OnlineFramework`, `OnlineSubsystemEOS`, `OnlineServicesEOS`, `OnlineServicesNull`, `OnlineServicesOSSAdapter`, `OnlineSubsystemSteam`, `SocketSubsystemSteamIP`, `SteamSockets`, `AssetReferenceRestrictions`, `ModelingToolsEditorMode`, `GeometryScripting`, `AnimationLocomotionLibrary`, `AudioModulation`, `AudioGameplayVolume`, `AudioGameplay`, `SoundUtilities`, `AnimationWarping`, `MovieRenderPipeline`, `MoviePipelineMaskRenderPass`, `AssetSearch`, `GameplayInsights`, `ResonanceAudio`, `Spatialization`, `FunctionalTestingEditor`, `GameplayInteractions`, `SmartObjects`, `ContextualAnimation`, `GameplayBehaviorSmartObjects`, `GameplayStateTree`, `GameplayBehaviors`, `RuntimeTests`, `AutomatedPerfTesting`, `Reflex`。

未找到的 12 项：

| Plugin | pointer | enabled | optional | 当前上下文适用 | filters / 说明 |
|---|---|---:|---:|---:|---|
| `D3DExternalGPUStatistics` | `/Plugins/5` | true | true | true | `SupportedTargetPlatforms=[Win64]`；产生 warning |
| `MagicLeap` | `/Plugins/29` | false | false | true | 无 |
| `MagicLeapMedia` | `/Plugins/30` | false | false | true | 无 |
| `MagicLeapPassableWorld` | `/Plugins/31` | false | false | true | 无 |
| `OpenXRHMD` | `/Plugins/34` | false | false | true | 无 |
| `SteamVR` | `/Plugins/35` | false | false | true | 无 |
| `GearVR` | `/Plugins/36` | false | false | true | 无 |
| `LuminPlatformFeatures` | `/Plugins/37` | false | false | false | `SupportedTargetPlatforms=[Lumin]` |
| `MLSDK` | `/Plugins/38` | false | false | true | 无 |
| `PlayFabParty` | `/Plugins/40` | true | false | false | `PlatformAllowList=[XB1,XSX,WinGDK]`; `SupportedTargetPlatforms=[XB1,XSX,WinGDK]` |
| `EOSReservedHooks` | `/Plugins/41` | true | true | true | 无；产生 warning |
| `RuntimePhysXCooking` | `/Plugins/64` | false | false | true | 无 |

稀疏 item 的默认值为：`declared_enabled=true`、`optional=false`、`applicable_for_context=true`、`status=resolved`、`additional_fields=[]`、`alternate_descriptors=[]`、`filters={}`；省略字段继承这些默认值。

Validation：`warning`，2 个问题；完整诊断已列于“Validation 总览”。

Limits：

- Responsibility: `Resolve direct .uproject Plugin references for one explicit profile.`
- `Only direct .uproject plugin references are resolved.`
- `Effective defaults and transitive .uplugin dependency closure are not computed.`
- `Applicability evaluates platform and target filters; configuration and deeper UBT policy remain out of scope.`
- `Plugin descriptor contents and hashes are not read.`
- `Sparse items inherit omitted fields from item_defaults; problem items retain all modeled fields.`
- `Descriptor paths are relative to path_roots according to origin.`

## 7. 路径分类

- Project root：`E:/UE_ITPS/LyraStarterGame`
- 描述符：`LyraStarterGame.uproject`，角色 `project-descriptor`，预期 `file`，实际 `file`

项目目录：

| 路径 | 角色 | 预期 | 实际 |
|---|---|---|---|
| `Source` | `source` | directory | directory |
| `Config` | `configuration` | directory | directory |
| `Content` | `content` | directory | directory |
| `Plugins` | `plugins` | directory | directory |
| `Build` | `build` | directory | directory |
| `Platforms` | `platform-extensions` | directory | directory |

构建与 IDE 路径：

| 路径 | 角色 | 预期 | 实际 |
|---|---|---|---|
| `Binaries` | `binaries` | directory | directory |
| `Intermediate` | `build-intermediate` | directory | directory |
| `LyraStarterGame.sln` | `ide-workspace` | file | file |

缓存与本地状态路径：

| 路径 | 角色 | 预期 | 实际 |
|---|---|---|---|
| `DerivedDataCache` | `derived-data-cache` | directory | directory |
| `Saved` | `saved-state` | directory | directory |
| `.vs` | `visual-studio-state` | directory | directory |
| `.idea` | `jetbrains-state` | directory | directory |

未分类根目录：无。Validation：`ok`，0 个问题。

Limits：

- Responsibility: `Classify project-root path names, locations, and filesystem states.`
- `The tool reads only explicit .uproject fields needed to diagnose directory presence.`
- `The tool does not read directory contents or locate Module, Target, Plugin, or asset files.`
- `The tool does not determine source authority, deletion safety, self-containment, or rebuildability.`
- `A missing Source directory is an error only when Modules are declared and no AdditionalRootDirectories may contain them.`
- `Binaries is reported by conventional role without deciding whether it is generated or required.`
- `Only unclassified root directories are reported; unclassified root files are outside this schema.`

## 总体工具边界

本报告只说明静态项目入口事实。`validation: ok` 不证明项目可编译、可启动或运行正确；EngineAssociation 不是实际版本证据，实际版本来自解析后的 `Build.version`。Module 工具不执行 UBT 或编译，Target 工具不评估 TargetRules，Plugin 工具只解析 `.uproject` 的直接引用而不计算 `.uplugin` 传递依赖闭包，路径工具不读取目录内容，也不判断删除安全性、自包含性或可重建性。
