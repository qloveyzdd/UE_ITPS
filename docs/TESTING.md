# 测试与验证

项目测试分为三层：仓库根目录的 SourceTools 核心测试、辅助组件测试，以及依赖本地参考工程的 Lyra 回归。统一入口是 `python -m tests`。

## 测试套件

| 套件 | 命令 | 内容 | 外部前提 |
| --- | --- | --- | --- |
| `core` | `python -m tests --suite core` | 工程描述符、C++/C# 前端、类型、函数、委托、Scope、导航和输出契约 | 无 |
| `components` | `python -m tests --suite components` | Editor/离线工具、知识图谱、文件图谱、MCP 连接池和问答路由 | Python 依赖 |
| `lyra` | `python -m tests --suite lyra` | Lyra 参考工程回归、AST 基线、检索准确性和 Scope 配置 | Lyra 工程及可解析的 Engine |
| `all` | `python -m tests --suite all` | 上述三套测试 | Lyra 工程及可解析的 Engine |

使用 `--list` 查看选中的测试模块，使用 `-v` 查看每个用例：

```bash
python -m tests --suite core --list
python -m tests --suite components -v
```

Lyra 默认路径为 `LyraStarterGame/LyraStarterGame.uproject`，可通过环境变量覆盖：

```powershell
$env:UE_ITPS_LYRA_PROJECT = 'D:/Projects/LyraStarterGame/LyraStarterGame.uproject'
python -m tests --suite lyra -v
```

显式选择 `lyra` 或 `all` 时，如果工程不存在，入口返回退出码 2 并报告环境问题。直接使用 unittest 发现 Lyra 模块时，缺少工程的用例会跳过；跳过不计为真实工程验证通过。

## 组件测试

统一入口会加载以下组件模块：

- `edittools.tests.test_contracts`
- `edittools.tests.test_cxx_messages`
- `edittools.tests.test_message_resolution`
- `edittools.tests.test_offline_tools`
- `edittools.tests.test_question_router`
- `information_pool.tests.test_file_graph`
- `mcp_connection_pool.tests.test_pool`

页面测试独立运行：

```bash
cd show
npm ci
npm test
```

页面测试包括 TypeScript 检查、生产构建和内存 SQLite 查询；没有浏览器端到端测试。

## 验证边界

- Python 测试验证 CLI、Schema、解析事实、图谱结构和确定性输出，不证明 UE 工程可以编译或运行。
- Lyra AST 基线验证源文件解析结果与固定参考快照的一致性，不替代 UBT、UHT、Editor、PIE 或网络模式测试。
- Editor/离线测试使用合成输入或离线图谱，不连接真实 Editor；真实 Editor 结果必须由对应工具单独取得。
- 页面构建通过只说明 TypeScript 和生产构建成功，不说明浏览器交互全部可用。

## 当前验证记录

本轮整理前的已执行结果：

- SourceTools 核心：154 项通过。
- Editor/离线、文件图谱和 MCP 组件：38 项通过，包含运行时公共工具回归。
- 全量套件实际运行 223 项，其中 221 项通过、2 项失败；失败集中在 Lyra AST 基线的两个局部扫描，原因都是当前 Engine provenance 无法解析，扫描返回 `source-unit-engine-unresolved` warning，而基线断言要求 `validation.status == "ok"`。
- Lyra 回归必须在本机 Engine 关联可解析时重新执行；不能仅凭参考工程文件存在判定通过，也不应为了消除环境 warning 放宽基线断言。

测试数量随用例和参考工程版本变化；文档中的数字只记录最近一次实际执行结果，不是永久能力保证。修改解析规则、Schema、测试入口或参考工程后，应重新运行受影响的套件。

## 维护规则

1. 先运行与改动直接相关的套件，再运行 `core` 或 `all` 做集成确认。
2. 固定基线失败时先判断源码、Engine、配置还是解析规则发生变化，再调整期望值。
3. 新增 CLI 时同时新增 Schema、帮助检查和工具池契约；新增组件时加入 `components` 套件清单。
4. 测试无法执行时明确区分失败、跳过和环境不可用，不把环境问题改写成代码通过。
