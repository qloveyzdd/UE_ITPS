---
name: ue-project-inspector
description: 使用仓库 SourceTools 检查 UE 工程描述符、构建入口、显式 C++ 文件及配置范围，提取类型、函数、委托和可定位证据。用于静态源码导航与汇总；不用于修改项目、构建或验证运行时行为。
---

# UE Project Inspector

从仓库根目录调用现有 `sourcetools/`，不复制或改写工具。需要完整入口清单时运行 `python sourcetools/ue_list_tools.py`；若目录缺失，说明实现不可用，不在技能内重建。

## 按问题选择工具

| 需要的信息 | 工具 |
|---|---|
| 查找工程 | `ue_find_projects.py --search-root` |
| 实际 Engine 身份 | `ue_resolve_engine.py --project` |
| 项目模块与直接插件声明 | `ue_read_project_descriptor.py --project --engine-build-version` |
| 按模块名或插件名定位描述文件 | `ue_find_build_descriptor.py --project --modulename/--pluginname` |
| Target 及可解析继承声明 | `ue_inspect_targets.py --project` |
| 单插件声明 | `ue_read_plugin_descriptor.py --plugin` |
| 单模块直接依赖或注册入口 | `ue_inspect_module_rules.py` / `ue_inspect_module_entry.py --rules` |
| 模块内显式文件候选及头源配对 | `ue_list_module_cxx_sources.py --rules` |
| Include 来源 | `ue_list_cxx_includes.py --source` |
| 定义基础清单 | `ue_list_cxx_types.py --source` |
| 一个类型的直接成员与基类 | `ue_inspect_cxx_type.py --source --type` |
| 所有函数定义及选择名 | `ue_list_cxx_functions.py --source` |
| 一个函数名对应的符号与委托 | `ue_inspect_cxx_function.py --source --function` |
| 配置范围的分层导航 | `ue_inspect_cxx_scope.py --project --profile` |

只运行回答问题所需的工具。批量汇总仍须保存每个工具自己的输入、Schema、校验与边界，不拼造统一工程返回结构。参数细节先读对应 `--help`；详细输出约定见[工具契约](../../../docs/TOOLS.md)。

## 选择与证据

1. 不知道项目路径时先发现工程。存在多个候选时，用用户已点名的项目消除歧义；仍无法唯一确定才询问。
2. EngineAssociation 只是关联键；版本来自解析得到的 Build.version。不要从关联键猜版本或 Build Settings。
3. 从前一步证据选定 Build.cs、插件或源文件。源码工具只接受一个文件，或同主名的一份 `.cpp/.cc` 与一份 `.h/.hpp`；不自动找伴随文件。
4. 从类型清单选精确限定名，从函数清单选 `qualified_name`。函数简单名会匹配全部同名定义；重载、条件定义继续分别返回。
5. 需要业务/结构展示时，类型清单和函数详情可选 `--view behavior/structure` 与重复 `--focus NAME`。默认 full 保留独立契约；需要调用表达式、参数或非调用语句时请求相应语法详情。
6. Scope 使用已存在或任务明确要求的配置，不为普通单文件查询创建全项目配置。使用返回 ID 进入 type/function/evidence 层，按 `page.next_offset` 翻页；源码或配置变化后重新取 ID。

## 解释结果

- 源码工具解析显式文件，不读取传递头文件或被调用函数体，不进行预处理或编译器语义绑定。
- 类型清单只列定义；成员、基类和接口候选依据属于类型详情。引用过某类型不等于定义了该类型。
- Include 唯一物理来源不证明有效编译搜索路径，也不证明依赖声明正确。
- Build.cs 返回可提取字面量依赖，包含识别到的条件分支但不求值；不能称为实际构建依赖闭包。
- 默认 `external_symbols` 与优先级/Scope 逐位置事实口径不同，不能直接比较条目数。Scope 的 `summary.facts.call` 仅为补充调用。
- 委托只有 `delegate_contract_revision: 2`。读取 `operation/subject/delegate_type/callback/arguments/result/resolution/execution_scope`；identified 有局部类型与 API 证据，candidate 不证明委托操作。Lambda 操作与外层函数分开。
- 人工 roles、entry_points 和 navigation 不是自动推断的业务事实。reviewed 只对符合指纹、唯一定义、必要证据和解析检查的具体提示有效。
- `function_id` 及 Scope ID 依赖文件选择和快照；底层 `evidence.unit` 需结合显式输入路径解释。
- 先读 `validation`，再读 `limits`。warning 是有非阻断问题的完成结果；info-only 可以仍为 ok。退出码 0/1/2 分别表示无阻断完成、阻断扫描结果、参数/输入/读取失败。
- 汇总明确区分文件清单范围、实际语法解析范围和人工职责覆盖；保留未解析与未分类项。校验通过不等于 UBT、UHT、Editor 或运行测试通过。
