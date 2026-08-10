<!-- generated-by: gsd-doc-writer -->
# 开发指南

本文说明 UE ITPS 核心 Python 工具、Editor 工具、工程信息池以及 `show/` 本地关系浏览器的开发环境与日常命令。核心静态 CLI 和自动化测试不依赖本地 Unreal Engine；只有调试 `edittools/` 与真实 Editor 的连接时，才需要按 [`edittools/README.md`](../edittools/README.md) 配置 Unreal Editor。

## 本地设置

准备以下工具：

- Git。
- Python `>=3.10`。
- Node.js `>=22.13.0`；仅开发 `show/` 时需要，版本约束来自 `show/package.json`。

如需通过个人仓库提交改动，先在 GitHub 上 fork `qloveyzdd/UE_ITPS`，再将下面的地址替换为你的 fork。只需本地开发时可直接克隆上游仓库：

```powershell
git clone https://github.com/qloveyzdd/UE_ITPS.git
Set-Location UE_ITPS
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` 已包含运行时依赖和测试所需的 `jsonschema`。仓库没有 `.env.example` 或必需的全局环境变量，因此无需复制环境文件。

如需开发本地关系浏览器，再安装其锁定依赖并启动开发服务器：

```powershell
Set-Location show
npm ci
npm run dev
```

也可在 `show/` 中运行 `.\start-local.ps1`：脚本会在缺少 `node_modules` 时执行 `npm ci`，随后以 `http://localhost:4173` 启动本地服务并打开浏览器。修改前端依赖时使用 `npm install <package>`，并同时提交更新后的 `show/package-lock.json`。

## 构建命令

核心 Python CLI 直接从源码运行，没有打包或编译步骤。常用仓库级命令如下：

| 命令 | 说明 |
|---|---|
| `python tools/ue_list_tools.py` | 列出正式工具、输入要求与能力边界，可作为 Python 环境的快速检查。 |
| `python -m unittest discover -s tests -v` | 运行核心 CLI、Schema、导航、Module 和 C++ 分析测试。 |
| `python -m unittest discover -s edittools/tests -t edittools -v` | 运行 Editor 工具的独立测试套件。 |
| `python -m unittest discover -s information_pool/tests -v` | 运行工程信息池构建与查询测试。 |
| `python -m unittest discover -s mcp_connection_pool/tests -v` | 运行 MCP 连接池测试。 |

以下命令均在 `show/` 目录运行，并覆盖 `show/package.json` 中的全部脚本：

| 命令 | 说明 |
|---|---|
| `npm run dev` | 启动 vinext 开发服务器。 |
| `npm run local` | 绑定 `localhost:4173` 启动本地开发服务器。 |
| `npm run build` | 生成前端生产构建。 |
| `npm run start` | 启动已构建的生产服务。 |
| `npm run test` | 先构建，再运行渲染 HTML 与图数据库的 Node.js 测试。 |
| `npm run lint` | 对前端源码运行 ESLint，并忽略 `dist` 与 `.next`。 |

## 代码风格

Python 部分没有提交 Ruff、Black、Flake8、Mypy 或 EditorConfig 配置，也没有统一的 lint/format 命令。修改时应沿用相邻模块的现有模式：4 空格缩进、`snake_case` 命名、类型标注、UTF-8 文本，以及薄 CLI 与领域实现分离。正式 CLI 必须保持双语帮助、stdout JSON、统一退出码和 `validation`/`limits` 契约；修改公共输出时同步更新同名 `schemas/*.schema.json` 与成功、失败契约测试。

前端使用 ESLint 9；[`show/eslint.config.mjs`](../show/eslint.config.mjs) 启用 Next.js Core Web Vitals 与 TypeScript 规则，运行方式为：

```powershell
Set-Location show
npm run lint
```

当前仓库的 `npm run lint` 还会扫描内置的 [`show/public/vendor/sql-asm.js`](../show/public/vendor/sql-asm.js)。该第三方压缩文件会触发 ESLint 规则错误并使命令以非零状态退出；在调整 ESLint 忽略范围或更新内置依赖前，应把它记录为现有基线，不要为消除告警而手工格式化供应商文件。

[`show/tsconfig.json`](../show/tsconfig.json) 启用了 TypeScript `strict` 和 `noEmit`。仓库没有 Prettier 配置；不要引入与现有文件无关的大范围格式化。

文本与二进制规则由根目录 `.gitattributes` 约束：源码、配置和文档使用 LF，Windows `.bat`/`.cmd` 使用 CRLF，Unreal 资产与常见媒体文件按二进制处理。

## 分支约定

默认分支为 `master`。仓库未记录分支命名规范；开始工作前从最新 `master` 创建一个范围明确的短期分支即可，例如 `feat/tool-name`、`fix/parser-case` 或 `docs/development`。提交历史经常使用 `feat:`、`fix:`、`test:`、`refactor:` 和 `docs:` 前缀，但仓库没有强制的提交消息规范。

## PR 流程

仓库当前没有贡献指南文件、Pull Request 模板或 GitHub Actions 工作流。提交 PR 时按以下最小流程执行：

- 从最新 `master` 创建功能分支，并让每个 PR 只处理一个可验证的问题。
- 在描述中说明目标、行为变化、静态分析边界以及实际执行过的验证命令；无法运行的验证需明确列出。
- Python 改动至少运行受影响子系统的 `unittest`；公共 CLI 契约变更还应运行核心测试并同步对应 Schema。
- `show/` 改动至少运行 `npm run test`，并运行 `npm run lint` 记录结果；后者当前存在上文所述的供应商文件基线错误。
- 不提交 `.gitignore` 已排除的 Unreal 参考工程、Engine 生成目录、IDE 状态、虚拟环境或缓存；提交前检查 `git status`，避免混入无关文件。

评审重点是只读边界、明确选择、确定性顺序、可定位证据、保守失败以及文档与公共契约是否同步。更完整的内部约束见 [`docs/PROGRAM-DESIGN.md`](PROGRAM-DESIGN.md)。
