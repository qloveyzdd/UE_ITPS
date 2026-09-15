# Lyra 基线与历史调查索引

本目录保存 2026 年 7～8 月的 Lyra 调查。旧版源码位置、文件数量、资产与运行结论不能直接作为当前环境事实；当前实现以[项目状态](../PROJECT.md)和[工具契约](../../docs/TOOLS.md)为准。

## 当前参考环境

2026-09-15 使用 `ue_resolve_engine.py` 读取本地 Lyra 的 Engine 关联及 Build.version：

| 项目 | 定向扫描结果 |
|---|---|
| 工程 | `E:/UE_ITPS/LyraStarterGame/LyraStarterGame.uproject` |
| Engine 根目录 | `D:/UnrealEngine_5.8` |
| Build.version | **5.8.3** |
| 项目直接声明模块 | LyraGame、LyraEditor |
| Target | 10 个 |
| 插件直接声明 | 启用 73 个、禁用 11 个 |

以上只确认静态声明与版本解析。本轮没有构建、启动 Editor、运行 PIE 或重新验证网络模式。

## 旧环境摘要

| 时间与版本 | 已记录的观察 | 使用边界 |
|---|---|---|
| 2026-07，UE 5.6.1 | 本地源码 Engine、LyraEditor 构建、定向 Asset Registry 查询、L0/PIE 观察 | 部分原始运行日志被轮转，不能恢复为证据完整的运行验收 |
| 2026-08-09，UE 5.8.2 | 文档记录 Editor、PIE 与 MCP 工具基座观察 | 不是当前 5.8.3 的实测结果；独立运行归档仍需另行核验 |

旧目录/模块/入口报告已合并至此：当时的工程壳由 LyraGame/LyraEditor、Game/Editor/Client/Server Target、通用项目插件与 Game Feature 插件构成；Source、Config、Build 和 Content 承担不同输入职责。目录或启用声明不能单独证明运行必要性或可删除性。

旧快照曾记录 9,656 个权威文件、81 个直接插件引用（69 启用、12 禁用）。这些是旧基线数量，不能与当前源码清单混算，也不保证此后本地参考工程逐字节相同。

## 保留的证据

- [旧工程入口 JSON](../evidence/lyra-5.6.1/uproject-structure.json)：旧聚合 Schema `ue-itps.uproject-structure.v1`，不是当前核心 CLI 契约。
- [旧文件指纹摘要](../evidence/lyra-5.6.1/baseline-fingerprint.json)与[逐文件清单](../evidence/lyra-5.6.1/authoritative-files.sha256)。
- [旧 Asset Registry 切片](../evidence/lyra-5.6.1/asset-registry-slice.json)：选定资产的历史查询事实。

历史源码 Engine 位于 `D:/UnrealEngine_5.6`，旧记录的运行版本为 5.6.1；本地来源与 Epic 发布包的逐字节对应关系并未由官方包清单证明。

## 保留的专题调查

| 文档 | 历史内容 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Experience、Game Feature、Pawn/ASC、输入及 UI 的结构调查 |
| [PIPELINES.md](PIPELINES.md) | 启动、Experience 加载与 Pawn 初始化链 |
| [TRAVEL.md](TRAVEL.md) | 前端、Session、地图旅行和 World 替换 |
| [NETWORK-MODES.md](NETWORK-MODES.md) | 网络模式、Hard/Seamless Travel、对象存续与失败边界 |
| [MINIMAL-RUNTIME.md](MINIMAL-RUNTIME.md) | L0/L1 假设及尚未完成的最小运行验证 |
| [RUNTIME-EVIDENCE.md](RUNTIME-EVIDENCE.md) | 日志归档、manifest 与观察/验收分离方法 |

这些文档内部的“当前”“下一步”均指原调查日期。恢复某项调查时，应先重新确认引擎、工程指纹与证据来源，不自动恢复旧任务列表。
