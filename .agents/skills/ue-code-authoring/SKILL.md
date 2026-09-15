---
name: ue-code-authoring
description: 编写或修改 Unreal Engine C++ 类、组件、子系统及模块代码时使用。依据目标工程约定实施并验证；有 Rider MCP 时使用可用的语义查询与诊断，无连接时使用文件工具和工程现有构建链。不用于 Blueprint-only 或静态源码汇总。
metadata:
  argument-hint: "[要创建或修改的 UE C++ 类、组件或系统]"
---

# UE C++ 编写

这是 Agent 工作流说明，不表示仓库已经实现 Rider MCP、自动构建编排或 UE 代码写入服务。

## 先确认目标工程

- 使用用户已指定的 `.uproject`；没有路径时先在任务范围内定位。仓库根目录可以是工具仓库，不要求当前工作目录本身有 `.uproject`。
- 阅读目标文件、相关 Build.cs 和邻近实现，遵循现有目录、命名、反射和模块边界。
- EngineAssociation 是关联键；实际引擎与 Build Settings 依据解析后的 Engine 和目标 Target.cs，不按固定版本对照表猜测。
- 只在任务确实涉及 C++ 修改时使用本技能。普通静态汇总使用项目检查工具。

## 实施与验证

1. 定位根因或目标接口，说明改动范围；复杂变更收敛目标、约束和验收方式。
2. 沿用现有抽象，仅修改任务所需文件，保留用户已有改动。
3. 按需查看[UE C++ 检查要点](reference/ue-cpp-conventions.md)。
4. 有 Rider MCP 时，先发现当前可调用工具并读取实际参数 Schema。符号查询、文件诊断、跨文件检查、构建与格式化能力均以当前连接为准。
5. 每次修改后检查相关诊断；涉及反射、模块依赖、公共接口、复制或 UObject 生命周期时，运行相应构建及关键路径验证。
6. 没有 Rider 或相关能力时，使用文件工具及目标工程已有构建/测试方式；如无法验证，如实报告原因和剩余风险，不宣称通过。
7. 展示最终差异与验证结果。格式化限定于修改范围；不以检查全项目为由修复无关问题。

## Rider 工具发现线索

`search_symbol`、`search_text`、`get_file_problems`、`lint_files`、`get_project_problems`、`build_solution_start`、`build_solution_state`、`reformat_file` 是可能出现的能力名称，不是保证可用的接口。

某些连接只暴露 `execute_tool`；必须读取该连接的实时参数定义，不将直接工具参数套入包装接口。没有语义查询能力时可退回文本定位，但应保留这种差别。IDE 诊断不能替代必要的 UHT/UBT 和运行验证。
