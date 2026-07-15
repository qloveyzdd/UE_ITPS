---
mapped_at: 2026-07-15
scope: LyraStarterGame
status: ue-5.6.1-project-fingerprint-verified-l0-observed-raw-log-missing
---

# Lyra 5.6.1 可复现基线

## 结论

当前基线可以准确表述为：

> **使用报告版本为 UE 5.6.1 的本地源码 Engine，运行一份可追溯到 Epic UnrealEngine 仓库历史、并已冻结完整文件指纹的 Lyra 样例快照。**

该组合已经完成 `LyraEditor Win64 Development` 编译和实时 Asset Registry 查询；Editor、PIE、默认/前端 Experience 与正常退出曾在 2026-07-14 本机运行中观察到。由于该次原始日志后来被轮转清理，当前可把它作为后续架构研究的历史 L0 观察基线，但不能作为证据完整的运行权威。

但它不是“`5.6.1-release` 标签的逐字节镜像”：本地 Engine 位于 `5.6` 分支的后续提交，本地 Lyra 工程壳对应标签之前的一个官方历史快照；Marketplace 内容又不在 Engine Git 中。完整文件指纹已经解决“以后是否还是同一份本地样例”的问题，但不能替代 Epic 发布包清单证明。

## 证据等级

后续文档统一使用以下证据口径：

| 等级 | 含义 | 可证明什么 |
|---|---|---|
| 源码/配置事实 | Git、描述文件、`Build.cs`、`Target.cs`、INI 的直接内容 | 静态声明和版本来源 |
| Registry/反射事实 | UE 5.6.1 实时 Asset Registry 与对象反射结果 | 资产类型、字段和直接依赖 |
| 运行事实 | Editor、PIE、Game Feature、Experience 日志 | 某条路径在该次运行中真实发生 |
| 测试证明 | UBT、UHT、Automation、Gauntlet 或人工验收通过 | 指定上下文中的行为已验证 |
| 未验证推断 | 基于命名、静态关系或局部证据的解释 | 研究假设，不能晋升为权威结论 |

“两个文件相同”只证明文件内容一致；“两个节点都通过测试”也不自动证明它们的新组合已经验证。

## Engine 身份

| 项目 | 已验证事实 |
|---|---|
| Engine 根目录 | `D:/UnrealEngine_5.6` |
| `Build.version` | `5.6.1-0+UE5`，Compatible Changelist `43139311` |
| Engine 类型 | 源码构建，`Installed Engine Build: 0` |
| 当前分支 | `5.6` |
| 当前提交 | `cdda65cecacd9a1278020925c357bf4cc0b17e8c` |
| 当前提交时间 | `2025-08-27T08:50:22-04:00` |
| 远端 | `https://github.com/EpicGames/UnrealEngine.git` |
| `5.6.1-release` 标签 | `6978b63c8951e57d97048d8424a0bebd637dde1d` |
| Editor | `D:/UnrealEngine_5.6/Engine/Binaries/Win64/UnrealEditor.exe` |

当前 Engine 的已跟踪工作树无本地修改。它不是停在 `5.6.1-release` 标签：当前提交与该标签的整树比较有 10 个文件不同，主要涉及 GitDependencies、Apple SDK、AutomationTool、Horde、UBA 和 StateStream；`Engine/Build/Build.version` 在两者中相同。因此版本口径必须同时记录：

```text
运行报告版本：5.6.1-0+UE5
源码修订版本：cdda65cecacd9a1278020925c357bf4cc0b17e8c
```

`LyraStarterGame.uproject` 当前 `EngineAssociation` 为 `{6D46E408-487A-23A8-6BF7-4F8E40277C23}`。该 GUID 在本机注册表中映射到 `D:/UnrealEngine_5.6`，不是语义版本号。

## 构建工具链

首次完整构建日志明确记录了实际被选择的工具链：

| 工具 | 版本/位置 |
|---|---|
| Visual Studio | VS 2022 Build Tools `17.14.37216.2` |
| MSVC | `14.38.33145`，目录 `14.38.33130` |
| Windows SDK | `10.0.22621.0` |
| Bundled .NET SDK | `8.0.300` |
| Target | `LyraEditor` |
| Platform / Configuration | `Win64 / Development` |

完整构建日志：

`D:/UnrealEngine_5.6/Engine/Programs/UnrealBuildTool/Log-backup-2026.07.14-10.38.36.txt`

日志记录 455 个动作，成功编译并链接 `LyraGame`、`LyraEditor`、`ShooterCoreRuntime`、`ShooterTestsRuntime`、`TopDownArenaRuntime` 等模块，最终 `Result: Succeeded`，总耗时 88.62 秒。

复验命令：

```powershell
D:\UnrealEngine_5.6\Engine\Build\BatchFiles\Build.bat LyraEditor Win64 Development -Project=E:\UE_ITPS\LyraStarterGame\LyraStarterGame.uproject -WaitMutex -NoHotReloadFromIDE
```

复验结果为 `Target is up to date`、`Result: Succeeded`，耗时 2.49 秒。生成的 `LyraEditor.target` 记录版本 `5.6.1` 和 BuildId `f7a08ad0-e8b2-4e9c-a19d-0c6badd1116c`。

## Lyra 来源追溯

### 可直接证明的事实

本地 `LyraStarterGame/` 没有独立 Git 元数据。项目内 README 明确说明：源码来自 UnrealEngine Git，内容目录需要从 Unreal Marketplace 下载后合并。

本机 Engine 仓库包含 `Samples/Games/Lyra`，其当前提交与 `5.6.1-release` 标签下的 Lyra 子树相同，共 839 个已跟踪文件。将本地工程壳与该目录逐文件比较后得到：

- 834 个文件与当前 Engine 样例逐字节一致。
- 4 个 EOS Target 与提交 `e0004083403d8d9ff4419f2dee6769a209eea311` 逐字节一致。
- `.uproject` 去除 `EngineAssociation`、`Category`、`Description`、`EpicSampleNameHash` 四个安装/样例元数据字段后，与 `e0004083` 的插件和模块声明完全一致，均有 81 个插件引用。
- 没有缺失的 Engine 样例工程壳文件。
- 本地额外的 `Build/Replays`、`Platforms`、Content 和生成文件不在 Engine Git 的 Lyra 子树中，不能纳入上述 Git 同源比较。

`e0004083` 是 `5.6.1-release` 历史中的提交。它后面的提交 `5b0cb659f28161d6f47b662e3e9b984e39c5d0d2`（UE-294580）将 EOS 插件声明从 `.uproject` 移入四个 EOS Target；这正是本地快照与标签 Lyra 子树的 5 处差异来源。

因此，本地 C++、配置、Build 脚本和插件工程壳可以追溯到 Epic 官方历史，不存在“无法解释的一批自定义源码差异”。更准确的版本名称是：

```text
Lyra 官方历史快照 e0004083
+ Marketplace/安装元数据
+ Marketplace Content
+ 本机 UE 5.6.1 EngineAssociation
```

### 仍不能证明的部分

- Engine Git 不包含 Lyra 的 Content，因此不能用 `5.6.1-release` Git 标签校验当前 8,683 个 `.uasset`/`.umap`。
- 本机没有保留 Epic Games Launcher 的 Marketplace 安装 Manifest；`LauncherInstalled.dat` 也为空。
- `EpicSampleNameHash: 451731683`、官方 README、目录组成和工程壳一致性共同支持“Epic 样例包”判断，但不是官方发布包的密码学签名。

所以当前可声明“**Epic 可追溯且本地已冻结**”，不能声明“**已证明与 Epic 5.6.1 发布包逐字节相同**”。

## 本地文件指纹

本次对会影响工程语义或发布结果的文件生成了逐文件 SHA-256 清单：

- 清单：`.planning/evidence/lyra-5.6.1/authoritative-files.sha256`
- 汇总：`.planning/evidence/lyra-5.6.1/baseline-fingerprint.json`
- 生成工具：`.planning/tools/new_lyra_baseline_fingerprint.ps1`
- 文件数：9,656
- 总大小：2,509,522,992 bytes
- 清单自身 SHA-256：`4abc401a69a8dc48be0189d84dd090a2d8397a501bf243081bf64e495192e825`

| 根目录 | 文件数 | 字节数 |
|---|---:|---:|
| `Build` | 37 | 8,342,750 |
| `Config` | 45 | 153,267 |
| `Content` | 2,965 | 1,905,658,945 |
| `Plugins` | 6,116 | 593,626,668 |
| `Source` | 486 | 1,734,300 |
| 其他权威根文件与 `Platforms` | 7 | 7,062 |

清单排除 `.idea`、`.vs`、`Binaries`、`DerivedDataCache`、`Intermediate`、`Saved`、`Build/Scripts/obj`，以及生成的 `.sln`、`.vsconfig`、`Lyra.Automation.csproj.props`。重新计算命令：

```powershell
& E:\UE_ITPS\.planning\tools\new_lyra_baseline_fingerprint.ps1
```

以后任何 Engine、源码、配置或资产研究都应引用源码修订和该指纹；如果指纹变化，已有运行证据不能无条件继承。

## L0 运行证据

当时用于核验的原始运行日志路径：

`LyraStarterGame/Saved/Logs/LyraStarterGame-backup-2026.07.14-10.50.15.log`

该文件已于 2026-07-15 在连续运行 UE Python Commandlet 时被 `Saved/Logs` 自动轮转清理，且此前没有复制到 `.planning/evidence`。以下序列是文件仍存在时完成并提交的检查记录，但当前仓库不能再独立复核原始行。因此 L0 应从“证据完整的 Verified”降级为“历史已观察、证据留存不完整”；重跑 L0 并保存原始日志及 SHA-256 后才能恢复为权威运行证据。

已确认序列：

1. Editor 报告 `Engine Version: 5.6.1-0+UE5`。
2. PIE 从 `/Game/System/DefaultEditorMap/L_DefaultEditorOverview` 启动。
3. `B_LyraDefaultExperience` 进入 StartExperienceLoad 与 OnExperienceLoadComplete。
4. CommonGame 为本地玩家添加 `W_OverallUILayout` 根布局。
5. 随后加载前端地图，`B_LyraFrontEnd_Experience` 进入 StartExperienceLoad 与 OnExperienceLoadComplete。
6. Editor 正常执行 `Editor shut down` 与 `LogExit: Exiting`，没有 Fatal 或 Ensure。

日志中仍有两条无调用栈的 `LogAutomationTest: Error: Condition failed`。它们没有阻止本次 L0，但根因尚未定位，不能视为已解决。

实时 Asset Registry 的查询脚本和精简结果分别位于：

- `.planning/tools/query_lyra_asset_registry.py`
- `.planning/evidence/lyra-5.6.1/asset-registry-slice.json`

## 验收状态

| 验收项 | 状态 |
|---|---|
| Engine 运行报告版本为 5.6.1 | 通过 |
| Engine Git 提交与远端来源冻结 | 通过 |
| Lyra 工程壳来源差异可解释 | 通过 |
| 当前 Lyra 权威文件逐文件指纹冻结 | 通过 |
| `LyraEditor Win64 Development` 完整编译 | 通过 |
| 重复 UBT 构建 | 通过 |
| Editor、PIE、默认/前端 Experience 和正常退出 | 历史观察通过；原始日志已轮转，需重跑留存 |
| 实时 Asset Registry 定向查询 | 通过 |
| 与 `5.6.1-release` Lyra 子树逐字节相同 | 不通过；存在 5 处已解释差异 |
| Marketplace Content 官方发布清单校验 | 无上游 Manifest，无法完成 |
| 官方 Shooter 可玩链路 L1 | 未验证 |
| Gauntlet BootTest | 未运行 |
| 两条 AutomationTest 启动错误根因 | 未定位 |

## 当前边界

现在可以把该组合标记为“**源码、配置、资产指纹可复现，L0 曾在本机观察通过但原始运行证据待重新留存的 UE 5.6.1 Lyra 基线**”。它不等于 5.6.1 标签镜像，也不等于最小可玩链路已经通过。

当前优先继续归档启动生命周期、模块职责、资产配置和验证边界；在资料模型稳定前，不执行 L1、不修改 Gameplay、不删除插件或资产。
