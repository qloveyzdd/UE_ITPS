# UE-ITPS

面向 Unreal Engine 项目的可验证功能复用、工程知识管理与增量信任编程系统。

当前阶段不开发具体玩法或信任系统，先以 **UE 5.6.1 运行基线 + Epic 可追溯 Lyra 快照** 为可复现研究对象，归档工程组成、启动架构并界定最小运行链路。

当前入口：

- [基线与复现状态](.planning/codebase/BASELINE.md)
- [工程栈与依赖全景](.planning/codebase/STACK.md)
- [目录结构与职责边界](.planning/codebase/STRUCTURE.md)
- [Lyra 顶层架构与启动主链](.planning/codebase/ARCHITECTURE.md)
- [启动、Experience 与玩家初始化管线](.planning/codebase/PIPELINES.md)
- [前端、会话与地图旅行管线](.planning/codebase/TRAVEL.md)
- [网络模式、旅行存续与失败边界](.planning/codebase/NETWORK-MODES.md)
- [L0/L1 运行证据捕获规范](.planning/codebase/RUNTIME-EVIDENCE.md)
- [最小运行边界](.planning/codebase/MINIMAL-RUNTIME.md)

当前已完成 UE 5.6.1 本机编译，冻结 9,656 个权威文件的 SHA-256 清单，并归档 Engine/Lyra 来源、Target、Module、Plugin、目录职责、核心 Asset Registry 关系，以及 PIE 启动、Frontend、Session/Travel、四种网络模式、Hard/Seamless 对象存续、失败恢复、Experience、PlayerState、Pawn、ASC、InitState 和输入的静态主链。原始日志不可覆盖复制与 SHA-256 manifest 工具已经就绪。

当前本地 Lyra 工程壳可追溯到 Epic UnrealEngine 历史提交，但不是 `5.6.1-release` 标签的逐字节副本。L0 曾在本机观察通过，但原始运行日志已被 UE 日志轮转清理，必须重跑并受控留存后才能恢复为可审计权威证据；完整边界见基线文档。当前仍不执行 L1，也不修改或删减 Lyra。

## 仓库结构

```text
UE_ITPS/
├─ tools/                         UE 项目检查、基线指纹与运行证据工具
├─ docs/                          面向维护者的程序说明
├─ .agents/skills/                仓库级 Codex Skill
├─ .planning/codebase/            Lyra 架构研究归档
├─ .planning/evidence/            指纹、Registry 查询与运行证据
└─ LyraStarterGame/               当前 UE 5.6.1 Lyra 基准项目
```

工具的实现边界、数据流、已知缺口和优化建议见 [程序设计说明](docs/PROGRAM-DESIGN.md)。

## 在 Codex 中使用

仓库包含 `ue-project-inspector` Skill。打开本仓库后，可以显式调用：

```text
$ue-project-inspector 找出当前仓库的 .uproject，只读取项目声明。
```

```text
$ue-project-inspector 识别当前 UE 项目的精确引擎版本并给出证据文件。
```

```text
$ue-project-inspector 读取当前 .uproject 的紧凑声明，列出 Plugin 的简单启用、简单禁用和扩展声明。
```

```text
$ue-project-inspector 检查项目 Module 结构，不扫描插件。
```

```text
$ue-project-inspector 生成完整的项目入口扫描报告。
```

Skill 默认选择能回答问题的最小工具。只有明确要求完整报告时，才运行组合器。

## 直接运行 UE 项目检查工具

以下命令从仓库根目录执行。项目路径示例：

```powershell
$Project = "E:\UE_ITPS\LyraStarterGame\LyraStarterGame.uproject"
```

### 1. 发现 `.uproject`

```powershell
python tools\ue_find_projects.py --search-root E:\UE_ITPS
```

只定位候选项目；存在多个项目时返回 `ambiguous`，不会自行选择。

### 2. 读取 `.uproject` 显式声明

```powershell
python tools\ue_read_project_descriptor.py --project $Project
```

输出 `FileVersion`、`EngineAssociation`、Module 数量、Plugin 简单启用/禁用列表、扩展声明索引、Additional 目录和描述符 SHA-256；不重复完整 `Modules`/`Plugins`，也不搜索 Engine、Module 文件或插件目录。

### 3. 解析真实 Engine 身份

```powershell
python tools\ue_resolve_engine.py --project $Project
```

将 `EngineAssociation` 解析到 Engine 根目录，并读取 `Engine/Build/Build.version`。当前基线应解析为 UE 5.6.1。

### 4. 检查项目 Module

```powershell
python tools\ue_inspect_modules.py --project $Project
```

对账 `.uproject` 声明的 Module、`*.Build.cs`、源码数量和 `IMPLEMENT_*_MODULE` 入口候选。

### 5. 发现项目 Target

```powershell
python tools\ue_inspect_targets.py --project $Project
```

发现 `Source/**/*.Target.cs`，并单独报告根 `Source/*.Target.cs` 的原生项目证据。Target 不由 `.uproject` 声明。

### 6. 定位直接 Plugin 引用

先解析 Engine 根目录，再传给 Plugin 工具：

```powershell
$Engine = python tools\ue_resolve_engine.py --project $Project | ConvertFrom-Json

python tools\ue_resolve_plugins.py `
  --project $Project `
  --engine-root $Engine.engine_root `
  --operation scan `
  --platform Win64 `
  --target-type Editor `
  --configuration Development
```

当前只解析 `.uproject` 的直接 Plugin 引用，不计算 `.uplugin` 传递依赖和默认启用插件闭包。

### 7. 分类项目根目录

```powershell
python tools\ue_classify_project_paths.py --project $Project
```

将路径分成描述符输入、条件输入、生成物、缓存和本地运行状态。目录存在不代表运行时真正使用，也不代表最小项目必需。

### 8. 生成完整兼容快照

```powershell
python tools\inspect_uproject.py `
  --project $Project `
  --operation scan `
  --platform Win64 `
  --target-type Editor `
  --configuration Development `
  --json-out .planning\evidence\lyra-5.6.1\uproject-structure.json `
  --markdown-out .planning\codebase\UPROJECT-ENTRYPOINT.md
```

`inspect_uproject.py` 是薄组合器，用于兼容生成完整 JSON 和 Markdown；各领域事实仍由小工具实现。省略两个输出参数时，组合器只向标准输出写 JSON，不创建文件。

## Lyra 研究证据工具

### 生成基线文件指纹

```powershell
& .\tools\new_lyra_baseline_fingerprint.ps1
```

默认扫描 `LyraStarterGame/`，排除可再生目录，并写入：

- `.planning/evidence/lyra-5.6.1/authoritative-files.sha256`
- `.planning/evidence/lyra-5.6.1/baseline-fingerprint.json`

### 归档一次 UE 运行日志

关闭对应 UE 进程后执行：

```powershell
& .\tools\archive_lyra_run.ps1 `
  -SourceLog E:\UE_ITPS\LyraStarterGame\Saved\Logs\LyraStarterGame.log `
  -RunId l0-editor-pie-001 `
  -Level L0 `
  -RunMode PIE
```

工具验证复制前后哈希，并创建不可覆盖的 Run 目录。捕获状态固定为 `captured_unassessed`，不会自动晋升为已验证证据。

### 查询 Lyra Asset Registry

`tools/query_lyra_asset_registry.py` 依赖 `unreal` Python 模块，必须在 Unreal Editor/Commandlet 的 Python 环境中运行，不能用普通系统 Python 执行。默认输出：

```text
.planning/evidence/lyra-5.6.1/asset-registry-slice.json
```

## 输出与安全边界

- 七个聚焦的 UE 项目检查 CLI 默认只读，并将 JSON 写到标准输出。
- 完整组合器只有在显式传入 `--json-out` 或 `--markdown-out` 时写文件。
- 基线指纹、运行日志归档和 Asset Registry 查询属于证据生成工具，会写入 `.planning/evidence/`。
- 项目检查结果只证明静态声明和文件定位，不证明项目已经编译、启动、联网或通过测试。
- 当前工具固定以 UE 5.6.1 Lyra 为首个回归基准，但长期数据模型不应绑定 Lyra 架构。

## 当前回归基线

```text
Engine: 5.6.1
Project Modules: 2
Root Targets: 10
Direct Plugin References: 81
Declared Enabled / Disabled: 69 / 12
Simple Enabled / Disabled / Extended: 63 / 11 / 7
Resolved Plugin Descriptors: 69
Project / Engine Plugin Descriptors: 15 / 54
Applicable Enabled Resolved: 66 / 68
Validation: ok, warnings: 2
```

两条警告来自当前环境未定位的 Optional 插件 `D3DExternalGPUStatistics` 和 `EOSReservedHooks`。
