<!-- generated-by: gsd-doc-writer -->
# 测试指南

## 测试框架与准备

仓库按子系统维护五组自动化测试。Python 部分使用标准库 `unittest`，并用 `jsonschema >=4.18,<5` 校验 JSON Schema Draft 2020-12；`show/` 使用 Node.js 内置的 `node:test`。项目文档要求 Python 3.10 或更高版本，前端测试要求 `Node.js >=22.13.0`。

| 测试区域 | 框架 | 位置 | 主要覆盖内容 |
|---|---|---|---|
| 核心 CLI | Python `unittest` | `tests/` | CLI 契约、Schema、项目导航、构建规则、C++ 静态分析和端到端只读性 |
| Editor 工具 | Python `unittest` | `edittools/tests/` | Editor 工具契约、扫描、会话选择、消息模型和图导出 |
| MCP 连接池 | Python `unittest` | `mcp_connection_pool/tests/` | 连接发现、兼容性、健康状态和歧义处理 |
| 工程信息池 | Python `unittest` | `information_pool/tests/` | 快照构建、缓存、查询、确定性、失败恢复和 Schema |
| 本地关系浏览器 | Node.js `node:test` | `show/tests/` | 生产构建内容和 SQLite 关系查询 |

在仓库根目录安装 Python 测试依赖：

```bash
python -m pip install -r requirements-dev.txt
```

浏览器测试还需要安装 `show/` 的锁定依赖：

```bash
cd show
npm ci
```

Python 测试通过临时目录构造最小 Unreal 工程夹具，不依赖本地 Unreal Engine、示例工程或正在运行的 Unreal Editor。信息池测试会在临时目录中创建 Git 仓库，因此系统需能执行 `git`。

## 运行测试

在仓库根目录运行核心 CLI 的完整套件：

```bash
python -m unittest discover -s tests -v
```

其余 Python 子系统分别运行：

```bash
python -m unittest discover -s edittools/tests -t edittools -v
python -m unittest discover -s mcp_connection_pool/tests -v
python -m unittest discover -s information_pool/tests -v
```

运行本地关系浏览器测试；`npm test` 会先执行生产构建，再运行两个 `*.test.mjs` 文件：

```bash
cd show
npm test
```

只运行一个核心测试模块：

```bash
python -m unittest tests.test_cli_contracts -v
```

只运行一个 Python 测试方法：

```bash
python -m unittest tests.test_cli_contracts.CliContractTests.test_all_schema_documents_are_valid_draft_2020_12 -v
```

只运行一个浏览器测试文件：

```bash
cd show
node --test tests/graph-db.test.mjs
```

当前没有 watch 模式脚本。

## 编写新测试

Python 测试文件采用 `test_*.py` 命名，测试类继承 `unittest.TestCase` 或 `tests.support.CliTestCase`，测试方法以 `test_` 开头。核心 CLI 测试应优先复用 `tests/support.py`：它负责创建隔离的临时 Unreal 工程、执行 CLI、解析 JSON、校验对应 Schema，并检查统一的 `validation` 与 `limits` 契约。

新增核心 CLI 行为时，至少覆盖成功、失败或歧义边界中受影响的路径；公共输出应通过对应的 `schemas/*.schema.json` 校验。不要让测试依赖开发机上的 Unreal Engine、外部示例工程或持久化用户数据。

Editor、连接池和信息池测试应放入各自的 `tests/` 目录，并复用该子系统已有的夹具和 mock 模式。浏览器测试采用 `*.test.mjs` 命名，使用 `node:test` 的 `test()` 与 `node:assert/strict`；涉及生产产物的检查应通过 `npm test` 运行，以保留构建步骤。

## 覆盖率要求

仓库未配置覆盖率工具或最低覆盖率阈值。

| 类型 | 阈值 |
|---|---|
| 行覆盖率 | 未配置 |
| 分支覆盖率 | 未配置 |
| 函数覆盖率 | 未配置 |
| 语句覆盖率 | 未配置 |

因此，测试是否充分目前由行为契约、失败路径、确定性和只读性断言判断，而不是由覆盖率百分比作为门禁。

## CI 集成

仓库中未检测到 `.github/workflows/` 或其他 CI 测试配置，因此当前没有自动在 push 或 pull request 上运行测试的工作流。提交变更前应在本地运行受影响子系统的测试；修改公共 CLI、Schema 或共享解析逻辑时，应至少运行核心完整套件。
