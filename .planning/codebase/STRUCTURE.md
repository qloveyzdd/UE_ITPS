---
mapped_at: 2026-07-15
scope: LyraStarterGame
status: directory-and-ownership-map-verified
---

# Lyra 目录结构与职责边界

## 顶层结构

```text
LyraStarterGame/
├─ Source/                  项目 Target、LyraGame 与 LyraEditor
├─ Plugins/                 项目本地基础设施与 Game Feature
├─ Content/                 项目壳共享资产、前端、角色、输入和 UI
├─ Config/                  基础、平台、在线后端和本地化配置
├─ Build/                   Automation、Gauntlet、打包资源和回放输入
├─ Platforms/               平台扩展占位说明
├─ LyraStarterGame.uproject 项目模块和插件入口
├─ README.md                Epic 样例源码/Content 合并说明
├─ Binaries/                生成物，不属于权威源文件集
├─ Intermediate/            生成物，不属于权威源文件集
├─ DerivedDataCache/        缓存，不属于权威源文件集
└─ Saved/                   日志、配置和运行输出，不属于权威源文件集
```

当前指纹覆盖 9,656 个权威文件。`Content` 与 `Plugins` 占绝大多数体积和文件数，说明 Lyra 的真实功能边界不能只靠 C++ 目录判断。

## `Source/`：稳定项目壳

### Target 层

`Source/*.Target.cs` 定义 Game、Client、Editor、Server，以及 EOS、Steam、SteamEOS 的变体。Target 回答“构建哪种程序和允许编进哪些插件”，不回答“某个 Experience 运行时激活什么”。

### `Source/LyraGame/`

`Source/` 共有 486 个文件：10 个 Target、`LyraGame` 450 个文件、`LyraEditor` 26 个文件。`LyraGame` 主模块按领域拆分如下：

| 领域 | 文件数 | 主要内容 |
|---|---:|---|
| `AbilitySystem` | 51 | ASC、Ability、Effect Context、AbilitySet、Tag Relationship |
| `GameModes` | 20 | Experience、GameMode、GameState、PawnData、UserFacingExperience |
| `Character` | 16 | Character、PawnExtension、Hero、Health、PawnData |
| `Player` | 16 | Controller、PlayerState、LocalPlayer、Spawning |
| `Input` | 14 | Enhanced Input 配置与 Gameplay Tag 绑定 |
| `UI` | 79 | HUD、布局、设置、武器/指示器和 CommonUI 集成 |
| `GameFeatures` | 16 | AddAbilities、AddInput、AddWidgets 等项目 Action |
| `Equipment` / `Inventory` / `Weapons` | 44 | 装备、库存和武器通用运行时 |
| `Teams` | 22 | 队伍身份、比较和子系统 |
| `Settings` | 35 | 游戏、平台、性能和本地玩家设置 |
| 其他领域与模块根文件 | 137 | Camera、Audio、Feedback、Interaction、Replay、System 等 |

边界原则：`LyraGame` 放跨 Experience、可被多个玩法复用的项目框架；某个玩法独有的规则、资产和注入应优先归属对应 Game Feature。

### `Source/LyraEditor/`

包含 `Commandlets`、`Private`、`Utilities`、`Validation`，只在 Editor Target 中加载。其职责是开发和数据质量工作流，不应被当作运行时依赖。

## `Plugins/`：可复用基础设施与可选玩法

### 通用项目插件

`Plugins/` 根下的 12 个非 Game Feature 插件提供加载、用户、UI、设置、消息、模块化 Actor、Pocket World、Editor 工具和共享样例内容。它们与 Engine Plugin 不同：源码随 Lyra 项目分发，生命周期通常随 Target/Module 加载，而不是由 Experience 动态激活。

### `Plugins/GameFeatures/`

| 目录 | 文件数 | 源码文件 | 资产/地图 | 所有权判断 |
|---|---:|---:|---:|---|
| `ShooterCore` | 290 | 27 | 260 | Shooter 通用规则、体验、角色/武器/UI 资产 |
| `ShooterExplorer` | 53 | 0 | 51 | 基于 ShooterCore 的探索内容 |
| `ShooterMaps` | 5,332 | 0 | 5,330 | 大型 Shooter 地图与 World Partition 外部 Actor |
| `ShooterTests` | 56 | 18 | 35 | Shooter 自动化/功能测试 |
| `TopDownArena` | 101 | 11 | 87 | 独立俯视角玩法 |

`ShooterMaps` 的大量文件主要是 World Partition 外部 Actor，不代表有同等数量的独立功能。图谱阶段必须把这些资产聚合回 Map/Feature，而不是把每个文件都提升为人工审查单元。

## `Content/`：项目壳共享资产

项目根 Content 共有 2,965 个文件，主要分区：

| 目录 | 资产/地图数 | 职责 |
|---|---:|---|
| `Characters` | 796 | 共享角色、动画和外观资源 |
| `Audio` | 947 | 共享音频和 MetaSound 资产 |
| `UI` | 607 | CommonUI 布局、控件、图标和设置界面 |
| `Effects` | 257 | Niagara/VFX 等共享表现 |
| `Weapons` | 107 | 共享武器表现与基础资产 |
| `System` | 16 | 前端、默认地图和基础 Experience |
| `Input` | 15 | 项目级 Input Action/Mapping/InputConfig |
| `GameplayEffects` | 15 | 项目壳共享 Gameplay Effect |

根 Content 不是“所有玩法内容”的总仓库。Shooter 和 TopDown 的 Feature-owned 资产位于各自插件 Content 下；跨 Feature 的角色、UI、音频和样例资源仍可能位于项目根或 `LyraExampleContent`。

## `Config/`：配置叠加

45 个配置文件分为四层：

| 层 | 路径 | 作用 |
|---|---|---|
| 项目默认 | `Config/Default*.ini` | Map、GameMode、AssetManager、输入、Tag、性能等默认值 |
| 在线后端 | `Config/Custom/EOS`、`Steam`、`SteamEOS` | 由 Target 的 `CustomConfig` 选择 |
| 平台覆盖 | `Config/Android`、`IOS`、`Linux`、`Mac`、`Windows` | 平台差异 |
| 本地化管线 | `Config/Localization` | Gather、Import、Export、Compile 和报告 |

读取配置时必须记录最终 Target/平台和合并顺序；单独引用某个 Default INI 不能证明运行时最终值。

## `Build/`：验证与发布输入

排除生成的 `Build/Scripts/obj` 后，关键内容包括：

- `Build/Scripts/Automation/`：BootTest、ContentValidation、测试配置与审计集合。
- `Build/LyraTests.xml`、`LyraBuild.xml`：BuildGraph/测试入口。
- `Build/GauntletSettings.xml`：Gauntlet 设置。
- `Build/BatchFiles/`：本地测试、打包和本地化入口。
- `Build/Replays/`：示例和 PGO 回放输入。
- `Build/Android`、`IOS`、`Windows`：平台资源和打包输入。

这些文件属于验证/发布管线，不应与 `Binaries` 或 `Intermediate` 一起删除或忽略。

## 权威源文件与生成物边界

| 类别 | 默认处理 |
|---|---|
| `Source`、`Plugins/*/Source`、`*.Build.cs`、`*.Target.cs` | 权威源码候选 |
| `.uproject`、`.uplugin`、`Config`、`Build` | 权威工程配置/管线候选 |
| `Content`、插件 Content | 权威资产候选，但需要 Registry/运行证据解释语义 |
| `Binaries`、`Intermediate`、`DerivedDataCache` | 可重建生成物，不作为知识权威来源 |
| `Saved/Logs` | 运行证据，不能反向当作源码 |
| `.sln`、`.vs`、`.idea`、`.vsconfig` | 本地 IDE 状态/生成物 |

## 常见问题应该从哪里开始

| 问题 | 首查位置 |
|---|---|
| 项目为什么启动某张地图 | `Config/DefaultEngine.ini`、World Settings、UserFacingExperience |
| Experience 如何选中和加载 | `Source/LyraGame/GameModes` |
| Pawn/ASC/Input 为什么没就绪 | `Character`、`Player`、`AbilitySystem`、`Input` 与运行日志 |
| Shooter 规则在哪里 | `Plugins/GameFeatures/ShooterCore` |
| 大型 Shooter 地图在哪里 | `Plugins/GameFeatures/ShooterMaps` |
| UI 谁注入 | `Source/LyraGame/UI`、`GameFeatures`、`Plugins/UIExtension`、Experience Action |
| 某插件是否必需 | `.uproject`、`.uplugin`、Target、Build.cs、Experience 和运行证据联合判断 |
| 自动化从哪里运行 | `Build/Scripts/Automation`、`Build/LyraTests.xml`、`ShooterTests` |

## 当前边界

目录位置只能提供所有权线索，不能独立证明生命周期、数据流或可删除性。本阶段不根据目录名删除插件或资产；后续最小化必须先建立运行管线，再通过隔离实验验证。
