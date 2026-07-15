# UE-ITPS 工具程序设计说明

本文描述仓库 `tools/` 当前实现，供代码检查、架构讨论和后续优化使用。它描述的是研究原型现状，不是最终产品承诺。

## 1. 当前目标

当前程序只解决 UE 项目进入系统时的第一层确定性问题：

```text
项目入口在哪里？
`.uproject` 明确声明了什么？
EngineAssociation 对应哪套真实 Engine？
项目 Module、Target 和直接 Plugin 引用能否在磁盘上定位？
项目根目录中的内容属于输入、生成物、缓存还是运行状态？
```

这些结果未来可以成为 Code Graph 和 Authority Context 的底层证据，但当前不会自动生成 Feature Graph、判断功能权威、修改 UE 项目或执行构建。

## 2. 设计原则

### 单一工程问题对应一个工具

Codex 不应为了回答“引擎版本是什么”而扫描所有 Module 和 Engine Plugin。CLI 按独立工程问题拆分，组合器仅在需要完整快照时调用全部服务。

### 确定性优先

JSON 解析、注册表查询、路径定位、文件哈希和目录分类由程序完成。LLM 负责选择工具、解释结果和提出下一步，不替代可确定的文件系统判断。

### 事实与结论分级

程序区分：

- `.uproject` 的直接声明；
- 文件系统定位结果；
- Profile 下的适用性判断；
- 尚未实现或无法证明的运行语义。

`validation: ok` 只表示该次静态扫描没有阻断错误，不表示项目已经编译、运行或通过测试。

### 默认只读

七个聚焦检查工具只读项目、Engine 和注册表，并向标准输出写 JSON。组合器只有在显式传入输出参数时才归档结果。证据生成工具是单独的有写入能力工具。

## 3. 程序结构

```text
Codex / 用户
    │
    ├─ 仓库 Skill: .agents/skills/ue-project-inspector/
    │       负责意图路由与解释边界
    │
    └─ tools/ue_*.py
            负责参数、退出码与 JSON 输出
                │
                ▼
       tools/ue_project_tools/
            领域服务与共享实现
                │
                ├─ 独立 Schema JSON
                └─ snapshot.py → report.py
                         完整兼容快照与 Markdown
```

### 3.1 CLI 层

| CLI | 单一职责 | 主要输入 | Schema |
|---|---|---|---|
| `ue_find_projects.py` | 发现 `.uproject` 并报告歧义 | Search root | `ue-itps.project-discovery.v1` |
| `ue_read_project_descriptor.py` | 读取描述符显式事实 | `.uproject` | `ue-itps.project-descriptor.v1` |
| `ue_resolve_engine.py` | 解析 Engine 与 `Build.version` | `.uproject`、可选 Engine override | `ue-itps.engine-resolution.v1` |
| `ue_inspect_modules.py` | 对账项目 Module 结构 | `.uproject` | `ue-itps.project-modules.v1` |
| `ue_inspect_targets.py` | 发现 Target 与原生 Target 证据 | `.uproject` | `ue-itps.project-targets.v1` |
| `ue_resolve_plugins.py` | 定位直接 Plugin 引用 | `.uproject`、Engine root、Profile | `ue-itps.project-plugin-references.v1` |
| `ue_classify_project_paths.py` | 分类项目根路径 | `.uproject` | `ue-itps.project-paths.v1` |
| `inspect_uproject.py` | 组合已有结果并兼容旧快照 | 全部扫描上下文 | `ue-itps.uproject-structure.v1` |

CLI 只处理参数、调用服务、序列化结果和退出码，不应包含新的 UE 领域判断。

### 3.2 服务层

| 文件 | 当前职责 |
|---|---|
| `common.py` | UTF-8 JSON、路径规范化、SHA-256、受控遍历和文本输出 |
| `discovery.py` | `.uproject` 搜索、唯一候选选择和歧义状态 |
| `descriptor.py` | 顶层字段、未知字段保留、Additional 目录边界 |
| `engine.py` | GUID/版本关联、Windows 注册表、相对路径、祖先 Engine、`Build.version` |
| `code_inventory.py` | Module Build.cs/入口证据与 Target 文件发现 |
| `plugins.py` | 项目/Engine Plugin 描述符索引、直接引用定位和基础 Profile 过滤 |
| `structure.py` | 根目录的输入、生成物、缓存和运行状态分类 |
| `snapshot.py` | 调用领域服务、聚合兼容快照和诊断 |
| `report.py` | 将兼容快照渲染为中文 Markdown，不产生新事实 |

## 4. 主要执行流程

### 4.1 最小路由

```text
用户询问 Engine 版本
→ ue_resolve_engine.py
→ 读取 `.uproject` 的 EngineAssociation
→ 精确注册表映射 / 版本匹配 / 路径 / 祖先 Engine
→ 读取 Engine/Build/Build.version
→ 输出版本、根目录、解析方法和 SHA-256
```

### 4.2 完整项目入口快照

```text
发现唯一 `.uproject`
→ 读取描述符
→ 解析 Engine
→ Module / Target / Plugin / Path 检查
→ 聚合诊断
→ 输出 JSON
→ 可选渲染 Markdown
```

Module、Target、Plugin 和 Path 在获得描述符及 Engine 身份后逻辑上可以并行；当前兼容组合器仍按顺序调用。

### 4.3 Engine 解析优先级

```text
显式 --engine-root
→ EngineAssociation 中的相对/绝对路径
→ Windows 注册表精确关联
→ 按 Build.version 匹配语义版本关联
→ 向项目父目录查找 Engine
→ unresolved / ambiguous
```

`EngineAssociation` 是原始关联键，实际版本必须来自解析后 Engine 的 `Build.version`。

## 5. Profile 与“必需”边界

当前扫描上下文包含：

```text
operation: scan | open_editor | build_editor | run_game | cook_package
platform
target_type
configuration
```

默认 Profile 为 `scan / Win64 / Editor / Development`。在 `scan` 下，程序只陈述声明、定位和适用性，不把目录或插件直接判定为某个运行场景的最小必需项。

完整的必需性计算还需要 TargetRules、Build.cs、`.uplugin` 闭包、Config 合并、资产可达性和实际构建/运行证据。

## 6. 诊断与退出码

### 聚焦工具

- 发现工具通过结果中的 `selected`、`not-found` 或 `ambiguous` 表达候选状态。
- Engine 未解析、Module Build.cs 缺失/歧义、非 Optional 且适用的 Plugin 缺失可以导致非零退出。
- Optional、Disabled 或当前 Profile 不适用的 Plugin 不应升级为构建失败。

### 组合器

```text
0 = validation ok
1 = 扫描完成但存在阻断诊断
2 = 输入、发现或 JSON 解析失败
```

诊断 `code` 使用稳定英文机器码；当前部分面向人的说明仍混在领域结果中，后续应进一步移到渲染/本地化层。

## 7. 路径与安全策略

- 多个 `.uproject` 返回歧义，不沿用“取第一个”策略。
- `AdditionalRootDirectories` 和 `AdditionalPluginDirectories` 先规范化路径。
- 指向项目外部的 Additional 目录默认标记为 `skipped_external`，不遍历。
- 项目 Plugin 优先于 Engine Plugin；其他候选保留在 `alternate_descriptors` 中。
- `Binaries` 对源码项目通常是生成物，但对纯预编译分发可能是条件输入。
- `Saved/Logs` 可以作为运行证据来源，但不能反向成为源码权威。

## 8. 其他证据工具

### `new_lyra_baseline_fingerprint.ps1`

扫描项目权威输入候选，排除 `.vs`、`Binaries`、`Intermediate`、`DerivedDataCache`、`Saved` 等可再生或本地状态，生成逐文件 SHA-256 manifest 和汇总 JSON。

### `archive_lyra_run.ps1`

在 UE 进程关闭后复制原始日志，验证源文件捕获前后未变化、复制哈希一致，并通过 staging 目录原子发布不可覆盖的 Run。输出状态固定为 `captured_unassessed`。

### `query_lyra_asset_registry.py`

在 UE Python 环境中等待 Asset Registry 完成，查询固定 Lyra 资产、默认属性和直接依赖，写出当前研究切片。它是 Lyra 5.6.1 专用研究工具，不是通用项目扫描器。

## 9. 当前回归事实

当前本机 Lyra 5.6.1 smoke test：

```text
Engine root: D:/UnrealEngine_5.6
Engine version: 5.6.1
Project Modules: 2
Root Targets: 10
Direct Plugin References: 81
Enabled / Disabled: 69 / 12
Resolved Plugin Descriptors: 69
Project / Engine Plugin Descriptors: 15 / 54
Applicable Enabled Resolved: 66 / 68
Validation: ok
Warnings: 2 Optional Plugin descriptors not resolved
```

这些数值用于回归，不应成为通用算法中的硬编码。

## 10. 已知问题

### 正确性

1. Plugin 工具只解析 `.uproject` 直接引用，没有计算 Engine 默认插件、项目插件默认值和 `.uplugin` 传递依赖闭包。
2. Plugin Profile 过滤只覆盖基础 Platform/Target 字段，尚未完整实现 TargetConfiguration、Program、GameTarget 和 `HasExplicitPlatforms` 语义。
3. Module 定位按 `*.Build.cs` basename 搜索，尚未使用 UBT 规则程序集证明最终选中项。
4. Target 工具只发现文件，不解析 `TargetRules` 继承、TargetType、CustomConfig 或编译插件选择。
5. 项目类型只记录根 Target 证据，尚未分析 UBT 临时 Target/hybrid 项目原因。
6. 路径边界依赖规范化结果，尚未针对 Windows junction、symlink 和权限不可访问状态建立完整测试。

### 契约

1. 结果使用裸 `dict`，没有提交独立 JSON Schema、TypedDict 或 dataclass 契约。
2. 完整快照包含绝对路径和 `generated_at`，不利于跨机器 golden diff。
3. 聚焦工具的诊断信封尚未完全统一；`not-found`、`ambiguous` 与进程退出码的关系需要固定。
4. 兼容组合器仍承担部分策略聚合，事实发现、Profile policy 和报告展示还可以进一步分离。

### 性能

1. 每次 Plugin 解析都重新遍历 Engine Plugin 树，没有进程内索引缓存。
2. Module 工具为每个声明重复扫描搜索根，项目规模增大后接近 `Module 数 × 目录树遍历`。
3. CLI 逐进程调用无法共享描述符和目录索引；未来 MCP 常驻进程应提供只读缓存和明确失效键。

### 测试

1. 当前只有真实 Lyra smoke test，没有自动化 fixture 测试套件。
2. 未覆盖无项目、多项目、非法 JSON、FileVersion 变体、Engine 解析歧义、外部 Additional 目录、重复插件和 Profile 过滤矩阵。
3. Markdown renderer 与兼容快照之间没有 schema contract test。

## 11. 建议优化顺序

### P0：固定正确性和契约

1. 为七个 Schema 添加版本化 JSON Schema。
2. 建立小型 fixture 仓库和 Lyra 5.6.1 smoke/golden 测试，归一化时间与绝对路径。
3. 将事实发现、Profile policy、诊断定级和 Markdown 本地化拆开。
4. 统一工具结果信封、状态枚举、证据结构和退出码。
5. 补齐外部路径、junction/symlink 和不可访问状态测试。

### P1：扩大确定性图谱输入

1. 新增 `.uplugin` 描述符检查和有效 Plugin 闭包工具。
2. 新增 Build.cs/TargetRules 分析层，优先复用 UBT 可提供的确定性结果。
3. 建立 Config 合并、AssetManager 和 Primary Asset 入口工具。
4. 为 Engine/Project Plugin 索引增加以根目录和修改状态为键的缓存。
5. 将 Module/Target/Plugin 搜索改为一次索引、多次查询。

### P2：Codex 产品接入

1. 将服务函数暴露为本地 STDIO MCP tools。
2. 保留 Skill 作为任务路由和解释策略，不在 Skill 中复制程序逻辑。
3. 稳定后打包为 Codex Plugin，供团队安装。
4. React/Editor UI 只消费稳定 JSON，不参与扫描和权威判断。

## 12. 扩展规则

- 新的独立工程问题优先新增小服务和小 CLI，不扩大现有 CLI 的语义。
- 共享 helper 不作为 Codex 工具暴露。
- 组合器只调用和聚合，不重新实现领域扫描。
- 每个新结论必须标注来源文件、规则或运行证据。
- 没有对应测试和上下文条件的结果不得晋升为权威。
- 对 Engine、Lyra 源码和资产的修改不属于这些只读检查工具的职责。

## 13. 维护者审查清单

建议重点检查以下决策：

1. 七个工具边界是否足够小，是否仍有应独立拆出的策略层？
2. Profile 是否应继续由工具接收，还是由更上层 Policy Engine 统一计算？
3. 完整快照 v1 是否需要长期兼容，还是在 MCP 阶段改为按资源查询？
4. Engine 解析是否应直接复用 UE DesktopPlatform/UBT，而不是维护注册表近似实现？
5. Plugin 闭包应优先做到“描述符闭包”还是“某个 Target/Profile 的有效闭包”？
6. 绝对路径、时间戳和 SHA-256 在跨机器可复现结果中如何分层存储？
7. 是否接受 Python 作为长期核心，还是将扫描核心迁移到更贴近 UBT 的 C#/.NET？
8. MCP 常驻缓存如何失效，如何证明缓存没有污染权威边界？
9. 哪些事实可以仅由静态扫描获得，哪些必须进入 UHT、UBT、Editor 或运行验证？
10. 下一阶段是否先建设测试契约，再继续扩展 Config、Asset 和 Plugin 闭包？
