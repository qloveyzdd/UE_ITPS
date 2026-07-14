---
mapped_at: 2026-07-14
scope: LyraStarterGame
status: ue-5.6.1-local-build-and-l0-runtime-verified
---

# Lyra 5.6.1 基线

## 结论

**UE 5.6.1 + 当前 Lyra 源码** 已在本机完成项目编译、Editor 启动、PIE、默认 Experience、前端 Experience 和正常退出验证。它可以作为后续架构取证的本机基线。

这还不是完整的“可复现发布基线”：当前 Lyra 目录尚未冻结来源指纹，Gauntlet BootTest 尚未运行，最小可玩 L1 链路也尚未验证。

## Engine 基线

| 项目 | 已验证事实 |
|---|---|
| Engine 根目录 | `D:/UnrealEngine_5.6` |
| 版本文件 | `D:/UnrealEngine_5.6/Engine/Build/Build.version` |
| 精确版本 | `5.6.1-0+UE5` |
| 兼容版本 | `5.6.0`，Compatible Changelist `43139311` |
| Engine 类型 | 源码构建，`Installed Engine Build: 0` |
| Editor | `D:/UnrealEngine_5.6/Engine/Binaries/Win64/UnrealEditor.exe` |
| 构建配置 | Win64 Development Editor |

`LyraStarterGame/LyraStarterGame.uproject` 的 `EngineAssociation` 仍只写 `5.6`，精确补丁版本必须以 `Build.version`、`.target` 和运行日志为准。

## 构建证据

首次完整项目构建记录位于：

`D:/UnrealEngine_5.6/Engine/Programs/UnrealBuildTool/Log-backup-2026.07.14-10.38.36.txt`

该日志记录：

- 共执行 455 个动作。
- 成功编译并链接 `LyraGame`、`LyraEditor`、`ShooterCoreRuntime`、`ShooterTestsRuntime`、`TopDownArenaRuntime` 等模块。
- 写入 `LyraEditor.target`。
- `Result: Succeeded`。
- 总耗时 88.62 秒。

随后使用以下确定命令复验：

```powershell
D:\UnrealEngine_5.6\Engine\Build\BatchFiles\Build.bat LyraEditor Win64 Development -Project=E:\UE_ITPS\LyraStarterGame\LyraStarterGame.uproject -WaitMutex -NoHotReloadFromIDE
```

复验结果为：

```text
Generated code is up to date.
Target is up to date
Result: Succeeded
Total execution time: 2.49 seconds
```

当前 `LyraStarterGame/Binaries/Win64/LyraEditor.target` 已记录：

- Target：`LyraEditor`
- Project：`../../LyraStarterGame.uproject`
- Version：`5.6.1`
- BuildId：`f7a08ad0-e8b2-4e9c-a19d-0c6badd1116c`

项目模块及已构建插件的 `UnrealEditor.modules` 使用同一 BuildId。此前 5.6.0 且指向 `Lyra.uproject` 的旧清单已被本次构建替换。

## 运行证据

原始运行日志保存在：

`LyraStarterGame/Saved/Logs/LyraStarterGame-backup-2026.07.14-10.50.15.log`

已确认的运行序列：

1. Editor 报告 `Engine Version: 5.6.1-0+UE5`，Base Directory 为 `D:/UnrealEngine_5.6/Engine/Binaries/Win64/`。
2. PIE 从 `/Game/System/DefaultEditorMap/L_DefaultEditorOverview` 启动，耗时 0.446 秒。
3. `B_LyraDefaultExperience` 被识别、开始加载并完成加载。
4. CommonGame 为本地玩家添加 `W_OverallUILayout` 根布局。
5. 随后浏览 `/Game/System/FrontEnd/Maps/L_LyraFrontEnd?Experience=B_LyraFrontEnd_Experience`。
6. `B_LyraFrontEnd_Experience` 被识别并完成加载。
7. 用户关闭 Editor 后正常执行 `Editor shut down` 和 `LogExit: Exiting`，没有 Fatal 或 Ensure。

运行日志中有两条无调用栈的 `LogAutomationTest: Error: Condition failed`，出现在 Engine 初始化前。它们没有阻止 PIE、Experience 加载或正常退出，但根因尚未定位，不能直接视为已解决。

## 默认启动配置

- 默认地图：`/Game/System/FrontEnd/Maps/L_LyraFrontEnd`，来自 `LyraStarterGame/Config/DefaultEngine.ini`。
- 全局 GameMode：`/Game/B_LyraGameMode.B_LyraGameMode_C`。
- Asset Manager：`/Script/LyraGame.LyraAssetManager`。
- Game Feature Policy：`/Script/LyraGame.LyraGameFeaturePolicy`。
- 默认空 PawnData：`/Game/Characters/Heroes/EmptyPawnData/DefaultPawnData_EmptyPawn`。
- 前端 Experience：`/Game/System/FrontEnd/B_LyraFrontEnd_Experience`。

## Asset Registry 证据

`LyraStarterGame/Intermediate/CachedAssetRegistry_0.bin` 是 Editor 缓存格式，不能直接传给 `DumpAssetRegistry` Commandlet。已改为使用 UE Python API 读取实时 Asset Registry：

- 查询脚本：`.planning/tools/query_lyra_asset_registry.py`
- 精简结果：`.planning/evidence/lyra-5.6.1/asset-registry-slice.json`
- 查询结果记录 Engine 为 `5.6.1-0+UE5`。
- 指定的 Map、Experience、ActionSet 和 PawnData 均已从实际 Registry 和反射数据中读取。

## 验收状态

| 验收项 | 状态 |
|---|---|
| `Build.version` 为 5.6.1 | 通过 |
| `LyraEditor Win64 Development` 完整编译 | 通过 |
| 当前 Target 指向 `LyraStarterGame.uproject` | 通过 |
| 重复 UBT 构建返回成功 | 通过 |
| Editor 启动与 PIE | 通过 |
| 默认 Experience 完成加载 | 通过 |
| 前端地图与前端 Experience 完成加载 | 通过 |
| Editor 正常退出 | 通过 |
| 实时 Asset Registry 定向查询 | 通过 |
| 官方 Shooter 可玩链路 L1 | 未验证 |
| Gauntlet BootTest | 未运行 |
| Lyra 来源版本/文件指纹冻结 | 未完成 |
| 两条 AutomationTest 启动错误根因 | 未定位 |

## 当前边界

现在可以把 L0 标记为“**本机 UE 5.6.1 基线通过**”，但不能标记为“完整可复现基线”或“最小可玩链路通过”。下一步应验证单一 L1 切片，并保留原版 Lyra 不做删减。
