# 测试与验证

## 分组入口

所有命令从仓库根目录运行，页面命令除外。Python 测试使用 unittest；安装 `requirements-dev.txt` 即可，不要求 pytest。

```bash
python -m tests
python -m tests --suite lyra -v
python -m tests --suite all
python -m tests --suite core --list
```

- `core`（默认）：自动发现 `tests/test_*.py` 中不以 `test_lyra` 开头的模块，只使用临时/合成工程。
- `lyra`：运行全部 `test_lyra*.py`，要求真实参考工程。
- `all`：上述两组，仍要求真实参考工程；不包含其他组件的独立测试。
- `--list`：只显示所选模块；`-v`：显示各测试结果。

原始 `python -m unittest discover -s tests -v` 仍可用，但有本地 Lyra 时会连同较慢的参考工程回归一起执行，不再作为默认快速入口。

## 核心覆盖

| 测试模块 | 主要覆盖 |
|---|---|
| `test_contracts` | 16 个入口/Schema/工具池一致性、帮助、分组无遗漏、缺失 Lyra 的处理 |
| `test_workflows` | 临时项目、Build.cs、描述符导航、原生 GameplayTag |
| `test_structured_frontends` | C++/C# AST、UE 宏、声明/执行区域、语法恢复、独立调用归属检查 |
| `test_source_type_semantics` | 类型、成员、变量、反射位置及条件定义 |
| `test_source_function_inventory` | 完整函数定义清单、名称选择与身份 |
| `test_cxx_function_semantics` | 调用、类型、地址、转换、遮蔽、间接调用与定义隔离 |
| `test_delegate_analysis` | 委托 revision 2 的操作、参数、回调及候选边界 |
| `test_source_pairing` | 同目录/镜像/模块内配对、歧义及嵌套模块 |
| `test_source_priority` | 视图、精确关注、日志上下文、状态写入和非调用语句 |
| `test_source_scope` | 四级导航、分页、证据、快照与选择范围 |
| `test_source_navigation_map` | 地图导出、查询路径、改名/移除/实现变更 |
| `test_navigation_guidance` | 人工提示、指纹、缺证据、解析告警、歧义与过期降级 |

原 `test_retrieval_context.py` 的 4 个用例已并入 `test_source_priority.py`，断言保留。合成源码的调用归属用例移至前端测试；真实 Lyra 的 AST 对照仍单独保留。

## Lyra 回归前提

默认工程为仓库下的 `LyraStarterGame/LyraStarterGame.uproject`。参考工程不随仓库分发，其他位置可用环境变量明确指定，例如 PowerShell：

```powershell
$env:UE_ITPS_LYRA_PROJECT = 'D:/Projects/LyraStarterGame/LyraStarterGame.uproject'
python -m tests --suite lyra -v
```

需要匹配当前测试基线的完整项目及插件源码；涉及 Include 来源的 Scope 查询还依赖可解析的 Engine 关联。不同版本或修改后的源码可能改变固定计数、行号和人工复核指纹；应核实变化，不能直接修改期望值来消除失败。

显式选择 lyra/all 而工程缺失时返回退出码 2；直接 unittest 发现这些模块时全部 Lyra 用例明确跳过。跳过不算真实工程验证通过。

| 模块 | 验证内容 |
|---|---|
| `test_lyra_sourcetools_regressions` | 通过公开 CLI 检查宏文本、构造初始化、接收者和限定名 |
| `test_lyra_tree_sitter_baseline` | 707 个头/实现文件的原始 AST 与前端事实逐位置对照、委托与成员投影 |
| `test_lyra_source_scope` | 装备配置的 6 组/12 文件导航、证据、地图查询与局部结果体积约束 |
| `test_lyra_retrieval_accuracy` | 21 个配置问题与 6 个独立保留问题 |
| `test_lyra_retrieval_sampling` | 30 个抽样问题与 4 个新增保留问题，含重载候选、日志和非调用证据 |

单独运行一个模块：

```bash
python -m unittest tests.test_lyra_sourcetools_regressions -v
```

除 `test_lyra_tree_sitter_baseline` 为独立校验而直接遍历源码和原始 AST 外，其余 Lyra 测试通过 SourceTools 读取源码事实。61 个预选问题是回归语料，不代表自然语言检索准确率。42 文件导航样本、707 文件 AST 基线和单模块文件清单的范围不同，不混用计数。

夹具位于 `tests/fixtures/`，人工配置位于 `sourcetools/profiles/`。测试不依赖忽略跟踪的 `Saved/SourceTools/` 历次产物。

## 其他组件

```bash
python -m unittest discover -s edittools/tests -t edittools -v
python -m unittest discover -s information_pool/tests -v
python -m unittest discover -s mcp_connection_pool/tests -t . -v
```

- Editor/离线测试：CLI/Schema、配置、C++ 消息、知识图谱；不连接真实 Editor。
- 文件图谱：用临时工程生成真实 SQLite，检查节点、关系、证据和外键。
- MCP 连接池：使用构造的宿主连接，覆盖缺失、唯一匹配、版本不兼容与歧义；不测试真实网络连接。

页面单独运行：

```bash
cd show
npm ci
npm test
```

`npm test` 先做 TypeScript 检查和生产构建，再执行内存 SQLite 的摘要、关系/证据、搜索测试。没有浏览器交互端到端测试。

## 最近验证

验证日期：2026-09-15。以本轮最终实际结果更新，执行次数不作为永久能力指标。

| 范围 | 结果 |
|---|---|
| SourceTools 核心 | 129 项通过 |
| 本地 Lyra | 26 项通过，含 707 文件 AST 基线 |
| Editor/离线 | 10 项通过 |
| 文件图谱 | 1 项通过 |
| MCP 连接池 | 4 项通过 |
| 页面 | TypeScript 与构建通过，3 项查询测试通过 |

页面构建仍提示单个产物超过 500 kB；这是现有构建体积提示，不影响本轮测试通过。以上结果不包含 UE 编译、Editor/PIE、网络模式或 Blueprint 运行验证。

## 维护与验收

- 合并文件时保留不同场景的断言；先确认新旧用例清单，再运行对应组。
- 先检查原因，再更新固定基线；不要因版本变化自动放宽关键断言。
- 运行与改动相关的核心及组件测试；依赖真实工程的用例单独说明通过、失败或跳过。
- 文档入口、相对链接、工具数量及能力边界与实现一致。
