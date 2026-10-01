# 贡献指南

感谢参与 UE ITPS。请先确认改动属于工具、Schema、测试、文档或本地浏览器的明确范围，并保持每个提交可以独立理解和验证。

## 开始之前

准备 Python 3.10+，并初始化语法子模块：

```bash
git submodule update --init --recursive
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

修改 `show/` 时还需要 Node.js 22.13+，并在该目录执行 `npm ci`。

## 修改约定

- 核心 CLI 只负责参数和输出，领域逻辑放在对应的 `*_tools/` 包中。
- 修改 CLI 行为时同步更新同名 Schema、测试和必要的工具清单。
- 修改 SQLite 结构或图谱语义时，同时检查 `information_pool/`、`show/` 和相关测试。
- 参考工程、Engine 文件、生成目录和本地环境文件不应进入提交。
- 保留 `validation`、`limits` 和不确定状态，不把候选结果写成确定事实。

## 提交前检查

按改动范围运行最小必要检查：

```bash
python -m tests --suite core
python -m tests --suite components
cd show
npm test
```

Lyra 回归需要本地 Lyra 工程和可解析的 Engine；如果环境不满足，请在提交说明中写明，不能把环境不可用描述成测试通过。

## 提交内容

提交说明应包含改动目的、验证命令和已知限制。请不要提交 `Saved/`、`Intermediate/`、`Binaries/`、`DerivedDataCache/`、`node_modules/`、`.venv/` 或本地参考工程内容。

提交代码默认按仓库的 [Apache License 2.0](LICENSE) 提供；第三方代码及其许可证继续按 [第三方声明](THIRD_PARTY_NOTICES.md) 执行。
