---
defined_at: 2026-07-15
baseline: UE-5.6.1 / Lyra frozen fingerprint
scope: L0/L1 raw runtime evidence capture
status: capture-protocol-and-tool-ready; no-new-run-captured
---

# Lyra 运行证据捕获规范

## 目标

解决一个具体根因：UE 会轮转 `Saved/Logs`，后续 Editor/Commandlet 进程可能删除上一轮日志。运行结论如果仍引用该易变路径，就不能独立复核。

本规范只回答“如何把一次已经结束的运行原样捕获为不可覆盖证据”。它不自动判断测试通过，也不把 `exit code 0` 晋升为权威。

## 最小目录结构

```text
.planning/evidence/lyra-5.6.1/
├─ baseline-fingerprint.json
├─ authoritative-files.sha256
└─ runs/
   └─ <run-id>/
      ├─ raw.log
      └─ manifest.json
```

`run-id` 建议使用：

```text
20260715T153000Z-L0-editor-pie
20260716T091500Z-L1-shootergym-listen
```

目录一旦存在，捕获工具拒绝覆盖。失败重跑必须使用新的 Run ID。

## 捕获流程

1. 确认 Engine、Lyra 指纹和计划运行上下文。
2. 启动一次 UE 运行；不要并发启动会写同一 `Saved/Logs` 的 UE 进程。
3. 完成操作并关闭该 UE 进程。
4. 在启动任何新 UE/Commandlet 进程之前，立即运行归档工具。
5. 工具对源文件执行“哈希 → 复制 → 再哈希”，源文件变化或副本不一致立即失败。
6. 后续分析只读取 `runs/<run-id>/raw.log`，不再引用 `Saved/Logs`。
7. 运行结论单独评估；只有上下文、验收点和失败扫描完整时才能标记 Verified。

源 UE 进程必须先退出。两次哈希一致只能证明捕获窗口内稳定，不能防止仍在运行的进程稍后继续写入。

## 使用工具

```powershell
& E:\UE_ITPS\tools\archive_lyra_run.ps1 `
  -SourceLog E:\UE_ITPS\LyraStarterGame\Saved\Logs\LyraStarterGame.log `
  -RunId 20260715T153000Z-L0-editor-pie `
  -Level L0 `
  -Target LyraEditor `
  -Platform Win64 `
  -Configuration Development `
  -RunMode PIE `
  -Map /Game/System/DefaultEditorMap/L_DefaultEditorOverview `
  -Experience B_LyraDefaultExperience `
  -ExitCode 0
```

工具写入：

- 原始字节副本 `raw.log`；
- SHA-256 与字节数；
- 源日志文件名和最后写入时间；
- 捕获脚本本身的 SHA-256；
- L0/L1、Target、Platform、Configuration、RunMode、Map、Experience；
- 当前基线 manifest SHA-256；
- `capture_state=captured_unassessed`。

工具故意不记录源机器绝对路径，避免把机器目录或用户名写进长期证据。

## Capture、Assessment 与 Authority 必须分离

| 状态 | 含义 | 能否证明通过 |
|---|---|---|
| `captured_unassessed` | 原始日志已稳定复制并哈希 | 否 |
| Assessed Pass/Fail | 已按明确验收点分析该 Run | 只能证明该上下文的本次结果 |
| Verified | 运行、构建、测试、上下文和证据完整 | 可以成为晋升输入 |
| Authoritative | 团队接受其为指定上下文的标准 | 仍会因上下文变化失效 |

捕获工具永远只产生第一种状态。这样可以防止“日志存在”被误解为“行为正确”。

## L0 重新验证的最小验收点

受控 L0 至少需要从同一个 Run 中证明：

1. Engine 报告 `5.6.1`。
2. 运行 Target/Configuration 与 manifest 一致。
3. PIE 创建目标 World。
4. 实际 GameMode 为 `B_LyraGameMode_C`。
5. 默认 Experience 完成，而不只是开始加载。
6. 前端 Travel URL、前端 Map 与 `B_LyraFrontEnd_Experience` 一致。
7. CommonUI RootLayout 加入 viewport。
8. Frontend Flow 解除 Loading Screen 并显示 Main Screen。
9. 没有未解释的 Fatal、Ensure、TravelFailure 或 Experience/GameFeature Error。
10. 正常退出，完整日志已复制且 SHA-256 可复算。

当前历史 L0 日志中曾有两条未定位的 `LogAutomationTest: Error: Condition failed`。重跑时必须定位来源；不能仅因进程正常退出就忽略。

## L1 未来需要追加的证据

L1 的 Run 除 L0 上下文外，至少还要记录：

- 选中的 UserFacingExperience、MapID、ExperienceID 和解析后 URL options；
- Target、Runtime NetMode、World Role、Host/Join、Offline/LAN/Online、Hard/Seamless；
- Session 完成、Travel 发起、OldWorld EndPlay、NewWorld BeginPlay；
- 目标 Experience `ExecutingActions → Loaded`；
- Game Feature `Active`；
- PlayerState PawnData/AbilitySet；
- ASC Owner/Avatar；
- Pawn 所有 Feature 到达 GameplayReady；
- 一个真实 InputTag 激活 Ability；
- Shooter HUD 注入。

网络或 Seamless Run 还必须记录：

- 各进程独立 Run ID、PID、Target、命令行与监听/连接地址；
- Server 与每个 Client 的时间基准及可对齐事件；
- PC、PS、ASC、Pawn、GameState、ExperienceManager 的对象唯一标识；
- Seamless 前后 `CopyProperties`、PawnData、AbilitySet、Team/Squad、Attribute 与 Effect 的结果；
- PendingNetGame 创建、连接成功/失败、LoadMap 和 TravelCompleted；
- 失败时 `?closed`、默认前端图、Session/User 清理、错误 UI 与 Loading Screen 退出。

如果现有日志没有这些锚点，应先设计最小 Trace/临时日志方案，再运行 L1；不能用静态源码推断填补缺失运行证据。

## 失败关闭规则

出现以下任一情况，该 Run 不得晋升为 Verified：

- 源日志在捕获时仍变化；
- `raw.log` 与 manifest 的 SHA-256 不一致；
- Run ID 已存在或文件被覆盖；
- Engine/Lyra 指纹、Target、Map、Experience 或网络模式缺失；
- Process exit code 缺失且没有其他正常结束证据；
- 预期日志锚点数量为零；
- 存在未解释的 Error、Ensure、TravelFailure、加载失败或测试跳过；
- Session 成功但没有目标 World/Experience Ready 证据；
- 只保存摘要，没有原始日志。

失败证据仍应保留。它说明该候选为何不能晋升，也是后续修复和回归验证的输入。

## 当前边界

归档协议与工具已经就绪，但本轮没有重新启动 UE，也没有生成新的 L0/L1 Run。当前 L0 仍是历史观察、原始证据缺失；只有按本规范重跑后才能恢复为可审计运行证据。
