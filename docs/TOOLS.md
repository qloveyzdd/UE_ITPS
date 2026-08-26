# 工具清单

权威机器可读清单由以下命令实时输出：

```bash
python sourcetools/ue_list_tools.py
```

## 核心静态工具

| 类别 | CLI | 用途 |
|---|---|---|
| 工程 | `ue_find_projects` | 在一个根目录下发现 `.uproject`，歧义时不自动选择 |
| 工程 | `ue_read_project_descriptor` | 读取 Module、Plugin 启用状态和显式 Target allow list |
| 工程 | `ue_resolve_engine` | 解析工程关联的 Engine 身份和路径证据 |
| 构建 | `ue_find_build_descriptor` | 按名称查找 Module Build.cs 或 Plugin 描述符 |
| 构建 | `ue_inspect_targets` | 发现 Target 及其直接声明 |
| 构建 | `ue_inspect_module_rules` | 读取一个 Build.cs 的直接字面量依赖 |
| Plugin | `ue_read_plugin_descriptor` | 读取一个 `.uplugin` 的 Module 和 Plugin 声明 |
| 源码 | `ue_list_module_cxx_sources` | 汇总一个 Module 的 C++ 文件并配对同名头源文件 |
| 源码 | `ue_list_cxx_includes` | 提取显式文件的直接 Include 及物理来源 |
| 源码 | `ue_list_cxx_types` | 提取显式文件创建的类型、变量和函数定义 |
| 源码 | `ue_inspect_cxx_function` | 提取指定函数的外部符号候选 |
| Module | `ue_inspect_module_entry` | 定位支持的模块注册宏及可唯一匹配的头文件 |
| 图 | `ue_analyze_cxx_dependencies` | 构建工程内类型依赖并检测循环 |
| 图 | `ue_query_cxx_hierarchy` | 查询一个类型的继承邻域 |
| 图 | `ue_analyze_cxx_impact` | 反向追踪一个符号的静态影响范围 |
| 图 | `ue_trace_cxx_function_flow` | 提取指定函数的局部控制流和直接调用 |
| 工具池 | `ue_list_tools` | 输出全部核心工具的入口、输入和能力 |

CLI 文件位于 `sourcetools/`，调用时使用文件名并加 `.py`。

## Editor 与离线工具

`edittools/` 当前包含 16 个 CLI，分为四组：

- Editor 会话与资产：列出会话、Gameplay Tag、Tag 引用、资产关系、DataTable、DataAsset、Primary Asset。
- Blueprint：检查单个 Blueprint、扫描 Blueprint 结构和 Gameplay Message。
- 离线静态输入：扫描配置和 C++ Gameplay Message。
- 知识图谱：构建、校验、比较和导出统一逻辑图谱。

所有入口的参数契约都由测试直接执行。连接 Editor 的命令需要用户明确提供 `--node-id`，不会静默选择多个连接。
