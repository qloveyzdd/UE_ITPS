---
mapped_at: 2026-07-15
scope: LyraStarterGame
status: l0-historically-observed-raw-log-missing-l1-not-run
---

# Lyra 最小运行边界

## 两层定义

“最小运行”必须区分项目壳与可玩主链。

### L0：项目壳可运行

- UE 5.6.1 能加载项目。
- `LyraEditor Win64 Development` 编译成功。
- Editor 和 PIE 可启动。
- 默认 Experience 与前端 Experience 可完成加载。
- CommonUI 根布局可创建。
- Editor 可正常退出。

### L1：最小可玩链路

- 打开一张官方玩法地图。
- 加载一个 Shooter Experience。
- `ShooterCore` 从 Registered 进入 Active。
- GameMode 在 Experience Loaded 后生成 Pawn。
- PawnExtension 与 Hero 达到 `GameplayReady`。
- PlayerState ASC 完成 Owner/Avatar 绑定并获得 AbilitySet。
- 至少一个 Input Action 经 Gameplay Tag 激活 Ability。
- 基础 Shooter HUD 由 Game Feature Action 注入。

对 UE-ITPS 来说，L1 才是可作为首批“权威管线”的最小基准。

## 当前验证状态

| 验收点 | 状态 | 证据 |
|---|---|---|
| Engine 5.6.1 | 通过 | `Build.version` 与运行日志 |
| LyraEditor 完整构建 | 通过 | UBT 455 个动作，`Result: Succeeded` |
| UBT 重复验证 | 通过 | Target up to date，退出成功 |
| Editor/PIE | 历史观察 | `L_DefaultEditorOverview` PIE 启动；原始日志已轮转 |
| 默认 Experience | 历史观察 | `B_LyraDefaultExperience` Start/OnLoadComplete；原始日志已轮转 |
| 前端 Experience | 历史观察 | `B_LyraFrontEnd_Experience` Start/OnLoadComplete；原始日志已轮转 |
| CommonUI 根布局 | 历史观察 | `W_OverallUILayout` 加入 viewport；原始日志已轮转 |
| 正常退出 | 历史观察 | `Editor shut down`、`LogExit: Exiting`；原始日志已轮转 |
| Shooter Experience | 未验证 | 本次运行未进入 Shooter 玩法 |
| Pawn/GAS/Input/HUD 完整链 | 未验证 | 当前日志无足够运行证据 |
| BootTest | 未运行 | 只有测试源码存在 |

因此当前结论是：**L0 曾在本机观察通过，但原始日志留存不完整；L1 尚未运行。** 在 UE-ITPS 的未来权威口径下，L0 当前只能算 `Observed/Suspect`，不能算可独立审计的 `Verified`。

## 首个 L1 切片选择

选择：

```text
DA_ShooterGame_ShooterGym
→ /ShooterCore/Maps/L_ShooterGym
→ B_LyraShooterGame_ControlPoints
```

理由不是它玩法最简单，而是它在保持完整 Lyra 主链的同时拥有最小的插件和地图边界：

- Playlist、Map、Experience 都位于 `ShooterCore`。
- 不依赖 `ShooterMaps` 插件。
- `L_ShooterGym` 的 Asset Registry 直接依赖为 27 个硬依赖、1 个软依赖。
- 对比：`L_Convolution_Blockout` 有 596 个直接软依赖；`L_Expanse` 有 3015 个直接软依赖。
- 它虽然不显示在前端列表，但仍是当前 Lyra 基线自带的 UserFacingExperience，可通过确定参数直接启动。

前端产品路径仍保留用于后续对照：

```text
DA_Convolution_ControlPoint
→ L_Convolution_Blockout
→ B_LyraShooterGame_ControlPoints

DA_Expanse_TDM
→ L_Expanse
→ B_ShooterGame_Elimination
```

## ShooterGym 切片的已知组成

### Experience

`B_LyraShooterGame_ControlPoints`：

- 激活 `ShooterCore`。
- 使用 `HeroData_ShooterGame`。
- 执行 AddWidgets、AddAbilities、AddComponents。
- 组合 SharedInput、StandardComponents、StandardHUD 与 BasicShooterAccolades 四个 ActionSet。
- 直接软依赖 ControlPoint AbilitySet、计分组件、Bot、音乐、队伍规则和玩法 UI。

### PawnData

`HeroData_ShooterGame`：

- PawnClass：`B_Hero_ShooterMannequin_C`
- AbilitySets：`AbilitySet_ShooterHero`
- TagRelationshipMapping：`TagRelationships_ShooterHero`
- InputConfig：`/Game/Input/InputData_Hero`
- DefaultCameraMode：`CM_ThirdPerson_C`

### SharedInput

`LAS_ShooterGame_SharedInput`：

- 执行 `GameFeatureAction_AddInputBinding`。
- 执行 `GameFeatureAction_AddInputContextMapping`。
- 直接软依赖 `InputData_ShooterGame_AddOns` 与 `IMC_ShooterGame`。

### StandardComponents

`LAS_ShooterGame_StandardComponents`：

- 执行 `GameFeatureAction_AddComponents`。
- 直接软依赖 Shooter Hero、QuickBar、Nameplate 与 Niagara Number Pop 组件。

### StandardHUD

`LAS_ShooterGame_StandardHUD`：

- 执行 `GameFeatureAction_AddWidgets`。
- 直接软依赖 `W_ShooterHUDLayout`、QuickBar、WeaponReticle、EliminationFeed、AccoladeHost、触屏区域和性能 Widget。

以上来自 `.planning/evidence/lyra-5.6.1/asset-registry-slice.json`，不是文件名推断。

## L1 验证必须记录的证据

1. 实际 Map 与 URL 中的 Experience 参数。
2. `ShooterCore` 激活完成。
3. `B_LyraShooterGame_ControlPoints` Start/Complete。
4. PawnClass 与 PawnData 实例。
5. PawnExtension/Hero 的 InitState 到达 `GameplayReady`。
6. PlayerState ASC 的 Owner、Avatar 与已授予 AbilitySet。
7. 一次真实 InputTag → Ability 激活。
8. `W_ShooterHUDLayout` 或等价 Shooter HUD 注入。
9. 无 Fatal、Ensure、模块或 Primary Asset 错误。
10. 正常退出、完整日志文件、日志 SHA-256 与不会被后续 UE 进程轮转的受控副本。

如果现有日志级别不足，应先增加临时日志类别或使用调试命令观察，不能仅凭“画面能动”宣布管线权威。

## 派生最小项目的暂定保留边界

在 L1 通过前，不删除以下机制：

- `ULyraAssetManager` 与 Primary Asset 扫描规则。
- `ALyraGameMode`、UserFacingExperience 与 `ULyraExperienceManagerComponent`。
- `ULyraGameFeaturePolicy` 与 `ShooterCore`。
- `ULyraPawnData`、PawnExtension、Hero 与 Modular Gameplay InitState。
- PlayerState ASC、AbilitySet、Gameplay Tags 与 Enhanced Input。
- CommonUI、UIExtension 与 Game Feature Widget 注入。
- ShooterGym Map 及 Registry 证明的直接依赖。
- 当前基线测试与 BootTest，直到派生项目拥有替代验证。

`ShooterMaps`、TopDownArena、ShooterExplorer、在线平台 Target 和非启动主链工具可进入后续删减候选，但必须在派生副本中一次移除一项并重复 L0/L1。

## 下一步顺序

1. 已完成：冻结当前 Lyra 的 Engine 修订、来源边界和 9,656 个权威文件指纹。
2. 继续归档启动生命周期、资产配置、功能管线、测试入口和已知风险。
3. 使用已建立的日志捕获工具重跑一次 L0，恢复原始运行证据。
4. 资料模型稳定后，再运行 `ShooterGym + ControlPoints` L1 并收集上述十项证据。
5. 运行或明确配置 Gauntlet BootTest。
6. 只有当前基线的 L0/L1 都稳定后，才创建 Lyra-derived 最小项目副本。
7. 在副本中按单变量实验缩减插件和资产。

第 3 项使用的捕获规则与工具见 `.planning/codebase/RUNTIME-EVIDENCE.md` 和 `tools/archive_lyra_run.ps1`；本轮没有启动 UE，尚未生成新的 L0 Run。

## 未关闭风险

- 两条 Editor 启动期 `LogAutomationTest: Error: Condition failed` 尚未定位。
- Asset Registry 结果是直接依赖，不是完整传递闭包。
- Lyra 目录本身仍未纳入 Git；当前通过已跟踪的 SHA-256 清单检测变化，不能直接获得资产级 Git 历史。
- 2026-07-14 L0 原始日志已被 `Saved/Logs` 自动轮转；已提交结论仍可作为历史观察，但不能作为当前可审计运行证据。
- L1 尚无 Pawn、ASC、Input 和 HUD 的运行证据。
