# 架构

## 设计目标

UE ITPS 只做一件事：把明确输入范围内的静态或 Editor 现场证据转换为结构化事实。工具不替代 Unreal 官方构建链，也不根据不完整证据推断运行时行为。

## 数据流

```text
.uproject / .uplugin / Build.cs / Target.cs / C++
                         │
                         ▼
              sourcetools/ue_project_tools
                         │
              JSON + validation + limits
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
   information_pool/SQLite      Agent 或命令行调用方
            │
            ▼
       show/ 本地浏览器
```

Editor 路径与静态路径分离：`edittools/` 通过用户明确选择的已连接 Editor 节点读取资产、Blueprint、Gameplay Tag、配置和知识图谱事实；`mcp_connection_pool/` 只评估宿主已经暴露的连接是否匹配 UE 5.8、目标工程、只读要求和所需能力。

## 核心边界

- CLI 层负责参数、退出码和 JSON 输出，不承载领域解析。
- `sourcetools/ue_project_tools/` 负责描述符、C#、C++ 和图关系提取。
- 每个核心 CLI 与一个同名 Schema 对应；`common.schema.json` 提供公共定义。
- C++ 分析使用仓库子模块中的 Tree-sitter UE C++ grammar，只扫描显式选择的文件，不跟随传递 Include。
- 文件图谱保留节点、关系、证据和警告；浏览器只读 SQLite，不回写工程。
- 外部参考工程不参与工具包导入，也不作为测试必须项。

## 失败模型

核心 CLI 使用三类结果：正常事实、带警告的完整扫描、结构化错误。`validation.status` 表示当前扫描的最高问题级别；它不能证明工程可以编译或运行。
