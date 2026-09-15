# 开发约定

## 环境

需要 Python 3.10+。先准备本地语法子模块，再安装依赖：

```bash
git submodule update --init parsers/tree-sitter-ue-cpp
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

`requirements.txt` 固定 Tree-sitter 与 C# grammar，并安装 `parsers/tree-sitter-ue-cpp`。语法子模块独立版本管理；更新后在实际执行工具的 Python 环境重新安装：

```bash
python -m pip install --force-reinstall ./parsers/tree-sitter-ue-cpp
```

前端会检查所需 AST 节点，拒绝不兼容的旧语法包。测试使用标准库 unittest；不要求 pytest。

页面需要 Node.js 22.13+，使用已提交的依赖锁文件：

```bash
cd show
npm ci
```

## 修改约定

1. 核心 CLI 只处理参数和输出，领域逻辑放在 `sourcetools/ue_project_tools/`。
2. 每个核心 CLI 维护同名 `schemas/<name>.schema.json`；新增入口同步工具池。
3. C++/C# 语法事实由 Tree-sitter 前端产生；下游沿用结构化字段。UE 宏、委托与展示规则集中在 `ue_cpp_conventions.py`。
4. 保留独立工具的 `validation`、`limits` 和不确定状态，不以名称相同推断跨文件绑定。
5. 修改行为时先用临时工程复现；真实 Lyra 用例补充覆盖，不替代可独立运行的回归。
6. 默认 full、优先级视图、Scope 和导航地图具有不同输出口径。影响共同前端时检查对应消费者及 Schema。
7. 修改说明集中到对应文档；README 保留概况，不追加历次执行日志、过期快照链接或未经重跑的测试成绩。

## 组件约束

- Editor 实时命令要求明确 `--node-id`；不保存、编译或修改资产。新增 CLI 在 `edittools/schemas/` 维护契约。
- SQLite 结构或语义改变时，同步 `information_pool/`、`show/` 的读取校验与测试。
- 参考工程、Engine、第三方许可证与独立语法子模块不混入普通工具变更。
- 保留已有用户改动；提交前检查差异与必要测试，不自动提交或推送。

测试入口和各层验收口径见 [TESTING.md](TESTING.md)。
