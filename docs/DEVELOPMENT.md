# 开发约定

## 环境

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
git submodule update --init parsers/tree-sitter-ue-cpp
```

本地浏览器需要 Node.js 22.13 或更高版本：

```bash
cd show
npm install
```

## 修改核心 CLI

1. 把领域逻辑放在 `sourcetools/ue_project_tools/`，CLI 只处理参数和输出。
2. 为公开入口维护同名 `schemas/<name>.schema.json`。
3. 输出保留 `schema_version`、`validation` 和 `limits`，不要把静态候选描述成编译器或运行时事实。
4. C++ 文件选择必须显式；两个输入只能是同主名的一份源文件和一份头文件。
5. 新行为先加入最小临时工程工作流测试，再扩展实现。

## 修改 Editor 工具

- 实时命令必须要求明确的 `--node-id`。
- 保持只读，不保存、编译或修改资产。
- 离线扫描器不得假装拥有 Editor 运行时证据。
- 新 CLI 必须在 `edittools/schemas/` 增加同名 Schema。

## 修改文件图谱或页面

SQLite Schema 版本由 `information_pool/ue_file_graph/storage.py` 定义。改变表结构或语义时，应同时更新生成器、浏览器校验和两侧测试。页面只负责本地读取、查询和展示。

验证命令见 [TESTING.md](TESTING.md)。
