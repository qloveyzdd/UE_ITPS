<!-- generated-by: gsd-doc-writer -->
# 快速入门

本指南介绍如何安装 UE ITPS 的核心 Python CLI，并完成第一次只读 Unreal Engine 工程检查。核心 CLI 不修改工程、Engine、资产或系统配置。

## 前置条件

- `Python >= 3.10`。
- Git，用于克隆仓库。
- 描述符、规则和 C++ Source 检索不要求安装 Unreal Engine，也不需要 UBT/IDE 生成的 `compile_commands.json`。
- 可选：运行 `show/` 本地关系浏览器时需要 `Node.js >= 22.13.0` 和 npm；它们不是核心 CLI 的依赖。

Windows PowerShell 中可先检查版本：

```powershell
python --version
git --version
```

## 安装步骤

1. 克隆仓库并进入项目目录：

   ```powershell
   git clone https://github.com/qloveyzdd/UE_ITPS.git
   cd UE_ITPS
   ```

2. 创建并激活虚拟环境：

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. 安装核心依赖：

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. 如果需要运行测试，再安装开发依赖：

   ```powershell
   python -m pip install -r requirements-dev.txt
   ```

核心 CLI 不需要 `.env` 文件。工程路径、Engine 覆盖路径和其他选择条件均通过命令行参数显式传入。

## 首次运行

在仓库根目录列出全部只读工具：

```powershell
python sourcetools/ue_list_tools.py
```

命令成功时会向标准输出写入 JSON，其中包含工具列表和如下校验状态：

```json
{
  "validation": {
    "status": "ok",
    "problem_count": 0,
    "problems": []
  }
}
```

随后可在自己的工程目录中发现 `.uproject`：

```powershell
python sourcetools/ue_find_projects.py --search-root D:/Projects/MyGame
```

如果结果只有一个候选工程，可将其绝对路径传给聚焦工具：

```powershell
python sourcetools/ue_read_project_descriptor.py --project D:/Projects/MyGame/MyGame.uproject --engine-build-version D:/Epic/UE_5.8/Engine/Build/Build.version
```

每个正式 CLI 都输出带 `schema_version`、`validation` 和 `limits` 的 JSON。`validation.status` 为 `ok` 或 `warning` 表示扫描已完成；`error` 表示工具发现了阻断问题。

## 常见设置问题

### 缺少 Python 模块

如果启动时出现 `ModuleNotFoundError`，通常是当前 Python 解释器没有安装仓库依赖。确认虚拟环境已激活，再重新安装：

```powershell
python -m pip install -r requirements.txt
python -c "import tree_sitter; print('tree-sitter ready')"
python -c "import tree_sitter_cpp; print('tree-sitter-cpp ready')"
```

用 `Get-Command python` 可确认 PowerShell 当前调用的是哪个解释器。

### 搜索结果包含多个 `.uproject`

`sourcetools/ue_find_projects.py` 遇到多个候选工程时会返回 `project-discovery-ambiguous`，不会自动替你选择。缩小 `--search-root`，或从返回的 `candidates` 中选择明确的 `.uproject` 路径，再传给后续命令：

```powershell
python sourcetools/ue_read_project_descriptor.py --project D:/Projects/MyGame/MyGame.uproject --engine-build-version D:/Epic/UE_5.8/Engine/Build/Build.version
```

### 无法解析 Unreal Engine

`EngineAssociation` 只是工程与 Engine 的关联键。如果本机没有对应注册信息，可在确知 Engine 根目录时显式覆盖：

```powershell
python sourcetools/ue_resolve_engine.py `
  --project D:/Projects/MyGame/MyGame.uproject `
  --engine-root D:/Epic/UE_5.8
```

Engine 定位成功只证明工具找到了版本证据，不代表工程能够编译或启动；构建与运行仍需使用 Unreal 官方工具验证。

### C++ 语法结果与编译结果不同

C++ Source 工具直接读取源码，不执行预处理、条件编译、重载解析或跨文件类型绑定。它适合快速导航和建立保守候选；需要确认真实 include 选择、宏展开或调用目标时，仍应使用 UnrealBuildTool、编译器或 IDE：

```powershell
python sourcetools/ue_list_cxx_types.py `
  --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp
```

## 下一步

- 阅读 [开发指南](DEVELOPMENT.md)，了解本地开发、命令和代码规范。
- 阅读 [测试指南](TESTING.md)，了解测试套件、单文件测试和覆盖率约束。
- 阅读 [配置参考](CONFIGURATION.md)，了解 CLI 参数、默认值和环境变量。
- 阅读 [架构说明](ARCHITECTURE.md)，理解各 CLI、领域服务和 Schema 的职责边界。
