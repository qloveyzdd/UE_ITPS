<!-- generated-by: gsd-doc-writer -->
# 配置

UE ITPS 没有统一的全局配置文件。核心 Python CLI 通过每次调用时显式传入的参数选择 `.uproject`、`.uplugin`、规则文件或源码文件；工程信息池和 Editor 工具也采用相同原则。仓库中的环境变量主要服务于测试编码和 `show/` 本地关系浏览器的开发工具链。

## 环境变量

仓库未提交 `.env`、`.env.development`、`.env.test` 或 `.env.production` 文件。项目源码直接设置或读取的环境变量如下：

| 变量 | 必需 | 默认值 | 说明 |
|---|---|---|---|
| `PYTHONUTF8` | 否 | 普通 CLI 不设置；测试子进程固定为 `1` | `tests/support.py` 为 CLI 测试子进程启用 Python UTF-8 模式，保证中英文帮助和 JSON 不受 Windows 本地代码页影响。 |
| `CODEX_SANDBOX` | 否 | 未设置 | 仅由 `show/vite.config.ts` 读取。值为 `seatbelt` 时，Vite 开发服务器禁用 FSEvents 并改用轮询监听。 |
| `WRANGLER_WRITE_LOGS` | 否 | `false` | `show/vite.config.ts` 在变量尚未设置时关闭 Wrangler 日志写入。调用方预先设置的值不会被覆盖。 |
| `WRANGLER_LOG_PATH` | 否 | `.wrangler/logs` | Wrangler 日志目录；相对路径以启动 `show/` 时的工作目录为基准。 |
| `MINIFLARE_REGISTRY_PATH` | 否 | `.wrangler/registry` | Miniflare 本地注册表目录；相对路径以启动 `show/` 时的工作目录为基准。 |

核心 Python CLI、工程信息池和 Editor 工具没有读取业务环境变量。它们所需的项目路径、Engine 覆盖路径和操作选项均由命令行参数提供。

## 配置文件格式

### 本地关系浏览器托管配置

[`show/.openai/hosting.json`](../show/.openai/hosting.json) 是 JSON 对象，并由 [`show/vite.config.ts`](../show/vite.config.ts) 静态导入。仓库当前配置为：

```json
{
  "d1": null,
  "r2": null
}
```

- `d1`：为非空值时，作为本地 Cloudflare D1 binding 名称；`null` 表示不创建 D1 binding。
- `r2`：为非空值时，作为本地 Cloudflare R2 binding 名称；`null` 表示不创建 R2 binding。

构建时，[`show/build/sites-vite-plugin.ts`](../show/build/sites-vite-plugin.ts) 会把该文件复制到 `show/dist/.openai/hosting.json`。该文件没有仓库内 JSON Schema；因此应保持合法 JSON，并只使用当前实现读取的 `d1`、`r2` 字段。

<!-- VERIFY: 生产部署实际使用的 D1/R2 binding 名称和对应云资源 -->

### CLI 调用配置

核心工具不从 INI、YAML、TOML 或用户级配置目录读取默认目标。应在每次调用中显式选择输入：

```powershell
# 先发现候选工程
python tools/ue_find_projects.py --search-root D:/Projects

# 再把唯一、明确的工程传给聚焦工具
python tools/ue_read_project_descriptor.py --project D:/Projects/MyGame/MyGame.uproject

# Engine 自动解析不满足需要时才使用显式覆盖
python tools/ue_resolve_engine.py `
  --project D:/Projects/MyGame/MyGame.uproject `
  --engine-root D:/Epic/UE_5.8
```

当搜索根目录内存在多个 `.uproject` 时，发现工具返回歧义错误，不会选取默认工程。每个命令的完整参数和默认值以其 `--help` 输出为准，例如：

```powershell
python tools/ue_resolve_plugins.py --help
python information_pool/build_information_pool.py --help
python edittools/ue_editor_list_sessions.py --help
```

`requirements.txt`、`requirements-dev.txt` 是 Python 依赖清单，`schemas/*.schema.json` 是 CLI 输出契约；它们都不是运行时设置文件。

## 必需与可选设置

### 核心 Python CLI

没有所有命令共享的必需环境变量。必需项由各 CLI 的参数解析器检查，缺失时返回参数错误：

- 项目级检查器通常要求 `--project FILE`；项目发现器使用 `--search-root DIRECTORY`，未提供时搜索当前目录。
- `.uplugin`、`Build.cs`、`Target.cs` 和 C++ 源码检查器分别要求显式的 `--plugin`、`--rules`、`--target` 或 `--source`。
- 函数级检查器还要求 `--function NAME`；图查询按操作要求 `--class`、`--symbol`、`--selector` 或其他选择器。
- `--engine-root` 是可选覆盖。未提供时，工具依据所选 `.uproject` 的 `EngineAssociation` 和支持的平台机制解析 Engine。

### 工程信息池

构建命令要求 `--project` 和 `--pool`。查询命令要求 `--pool` 和 `--operation`；`lookup`、`search`、`hierarchy`、`impact`、`callers`、`path` 和 `test-scope` 等操作还会检查各自所需的选择器。

### Editor 工具

连接到运行中的 Unreal Editor 时，`--project` 必需；`--engine-root`、`--node-id` 和 `--timeout` 可选。具体扫描器还可能要求 Gameplay Tag、Blueprint 资产或输入 JSON 路径。目标项目中的 Editor 插件和 Remote Execution 状态不由仓库配置文件控制。

### 本地关系浏览器

运行 `show/` 需要存在合法的 `show/.openai/hosting.json`，因为 Vite 配置在加载阶段静态导入它。`d1` 与 `r2` 的值可选，当前均为 `null`；浏览本地 SQLite 快照不要求配置云绑定。

## 默认值

以下是源码中对常用可选项声明的默认值：

| 范围 | 设置 | 默认值 | 定义位置 |
|---|---|---|---|
| 项目发现 | `--search-root` | 当前目录 `.` | `tools/ue_find_projects.py` |
| Plugin 解析 | `--operation` | `scan` | `tools/ue_resolve_plugins.py` |
| Plugin 解析 | `--platform` | `Win64` | `tools/ue_resolve_plugins.py` |
| Plugin 解析 | `--target-type` | `Editor` | `tools/ue_resolve_plugins.py` |
| C++ 影响分析 | 最大深度 | `3` | `tools/ue_analyze_cxx_impact.py` |
| 信息池查询 | `--depth` | `3` | `information_pool/query_information_pool.py` |
| 信息池查询 | `--limit` | `100` | `information_pool/query_information_pool.py` |
| Editor 连接 | `--timeout` | `3.0` 秒 | `edittools/ue_editor_tools/cli.py` |
| Gameplay Message 扫描 | `--batch-size` | `20` | `edittools/ue_editor_scan_gameplay_messages.py` |
| Blueprint 检查 | `--max-nodes` | `0`，表示不限制 | `edittools/ue_editor_inspect_blueprint.py` |
| 本地浏览器 | 监听地址 | `localhost:4173` | `show/package.json` |
| 本地 Cloudflare 绑定 | `d1`、`r2` | `null` | `show/.openai/hosting.json` |

命令行提供的值优先于这些参数默认值；`WRANGLER_*` 和 `MINIFLARE_REGISTRY_PATH` 也只会在调用环境尚未设置时获得项目默认值。

## 多环境覆盖

仓库没有为开发、测试、预发布或生产维护不同的核心 CLI 配置文件。推荐按执行环境在命令行中传入明确路径和 Profile，而不是修改源码默认值：

```powershell
# 本地静态扫描
python tools/ue_resolve_plugins.py `
  --project D:/Projects/MyGame/MyGame.uproject `
  --operation scan `
  --platform Win64 `
  --target-type Editor

# 另一目标 Profile
python tools/ue_resolve_plugins.py `
  --project D:/Projects/MyGame/MyGame.uproject `
  --operation cook_package `
  --platform Linux `
  --target-type Game
```

`show/.gitignore` 忽略 `.env*` 和 `.wrangler/`，因此本地工具链状态不会进入版本控制。若需要覆盖 Wrangler 或 Miniflare 设置，应在启动 `npm run local` 或 `npm run build` 前设置相应环境变量；仓库目前没有定义应用自有的 `.env` 变量。

测试环境不需要单独的 `.env.test`。测试辅助代码会为 CLI 子进程设置 `PYTHONUTF8=1`，其余测试配置由测试命令和临时目录提供。
