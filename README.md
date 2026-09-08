# UE ITPS

UE ITPS 是一组面向 Unreal Engine 工程的确定性、只读检查工具。它从明确选择的 `.uproject`、构建规则和 C++ 源文件中提取 JSON 事实，不启动 Editor、不编译工程，也不修改项目内容。

## 当前组成

- `sourcetools/`：根目录保留 14 个静态检查 CLI，负责工程、Engine、Module、Target、Plugin 和 C++ 源文件分析；`lyra/` 集中存放 Lyra 专用证据工具。
- `schemas/`：核心 CLI 的 JSON Schema，采用 Draft 2020-12。
- `edittools/`：16 个 Editor/离线检查 CLI；连接 Editor 的命令只读取已连接节点的现场状态。
- `information_pool/`：把工程、模块、Target、源码和 Include 关系写入 SQLite 文件图谱。
- `show/`：本地打开并浏览文件图谱的 React 页面。
- `mcp_connection_pool/`：被动选择宿主已提供的 UE 5.8 只读 MCP 连接，不负责启动或重连外部进程。

`ExternalProjects/` 和 `LyraStarterGame/` 是检查对象或参考工程，不属于工具运行时实现。仓库内的 `parsers/tree-sitter-ue-cpp` 是独立子模块。

源码语法统一由 Tree-sitter 前端处理：C++/UE 宏通过 `tree-sitter-ue-cpp` 和 `cpp_frontend.py` 生成结构化事实，C# 通过 `tree-sitter-c-sharp` 和 `syntax_tree.py` 生成结构化事实。下游工具只负责名称解析和 UE 领域语义，不再用正则或字符串切割恢复 C++/C# 语法；INI、对象路径等独立数据格式仍由各自解析器处理。

Lyra 全量 Tree-sitter 回归基线覆盖项目与插件 `Source` 目录内 707 个 `.h/.cpp` 文件，要求原始 AST 无语法恢复，校验 Slate 参数声明与自动化测试声明的 UE 专用节点，并固定关键事实计数。另逐一对照原始 AST 的类型、函数定义及调用所属函数，检查每处定义的引用独立性和宏结束行，避免只有计数正确却存在遗漏或覆盖。可运行 `python -m pytest -q tests/test_lyra_tree_sitter_baseline.py --import-mode=importlib` 单独验证。

函数外部符号按源码位置排序（包括同一行）；调用模板实参中 AST 标记为类型的项保留为完整类型表达式，数字和表达式实参不作为类型输出。结果仍是语法候选，不执行模板语义绑定。

## 安装

需要 Python 3.10 或更高版本：

```bash
python -m pip install -r requirements.txt
```

开发和测试还需要：

```bash
python -m pip install -r requirements-dev.txt
```

## 快速开始

先查看当前工具清单：

```bash
python sourcetools/ue_list_tools.py
```

查找工程后，必须从结果中明确选择一个 `.uproject`：

```bash
python sourcetools/ue_find_projects.py --search-root D:/Projects
```

检查一个明确选择的 C++ 文件或同名 `.cpp`/`.h` 文件对：

```bash
python sourcetools/ue_list_cxx_types.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp D:/Projects/MyGame/Source/MyGame/Public/MyActor.h
python sourcetools/ue_inspect_cxx_type.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp D:/Projects/MyGame/Source/MyGame/Public/MyActor.h --type AMyActor
python sourcetools/ue_inspect_cxx_function.py --source D:/Projects/MyGame/Source/MyGame/Private/MyActor.cpp D:/Projects/MyGame/Source/MyGame/Public/MyActor.h --function BeginPlay
```

`ue_list_cxx_types.py` 会把 Engine 5.8 的原生 GameplayTag 声明/定义宏投影为 `FNativeGameplayTag` 变量事实；extern 声明不进入最终定义列表，static 定义保留内部 linkage。

`ue_list_cxx_types.py` 只输出所给文件中类、结构体（含 union）、枚举、自由函数、全局变量及 `#define` 宏定义的基础清单。保留名称、限定名、所属作用域、位置、函数签名、变量类型和附带的 UE 宏；不展开继承、成员、枚举项或接口推断。类型的 `evidence.line` 从附带的 `UCLASS`、`USTRUCT`、`UENUM` 或 `UINTERFACE` 宏起始行计算，`end_line` 仍为类型结束行；无附带宏时从类型声明行开始。独立宏仅返回名称、参数及位置，`parameters: null` 表示对象宏，`[]` 表示无参数函数宏，不输出宏体。前向声明、extern 声明和函数原型仍不进入清单。

局部类型使用包含外层函数名的词法路径导航，例如 `AWorker::Run::Local`；它是工具的选择名，不是可直接用于 C++ 的限定表达式。同名定义仍可返回多个匹配。内联友元函数归入命名空间自由函数；局部类型的成员函数体独立扫描，不计入外层函数或 Lambda 的调用。前端已有的 UE 测试类与 Spec 节点也进入类型清单，测试方法按 `TEST_METHOD` 的名称参数、`Setup`、`TearDown` 输出，保留原宏签名作为源码证据；不展开宏生成的额外成员。位置的结束行均为包含式行号，单行证据可省略 `end_line`。

`ue_inspect_cxx_type.py --type <qualified_name>` 精确选择类或结构体，返回 `matches`，包含继承、直接成员 `member_anchors`、成员函数定义 `member_functions` 和接口候选原因。嵌套类型须单独选择；类外实现只来自显式传入的文件，找不到类型返回退出码 1。成员覆盖类内定义、构造函数、模板和条件编译中的成员；类外静态成员变量定义仍在基础清单保留完整限定名。旧清单的 `member_anchors`、`base_types` 和顶层 `member_functions`、`interface_candidates` 已迁往类型详情，`enumerators` 及空的 `unresolved_declarations` 已移除。

函数扫描按本地作用域区分自由函数与成员调用，保留类型限定名及模板参数。成员归属复用调用点的词法绑定，处理局部变量、Lambda 参数及范围循环变量的遮蔽；`auto` 和 `decltype(auto)` 不作为已解析的所属类型。通过 `.*`、`->*` 发起的成员函数指针调用保留原始表达式，目标无法确定时输出 `unknown`，不生成虚构的具名成员方法。

取地址表达式依据所选文件中的函数、变量和成员声明分类，并考虑参数、局部变量、Lambda 参数及范围循环变量的遮蔽；有函数声明证据才输出 `function_address`，已知数据地址不进入该类别，无法确认的地址保留原表达式并输出 `unknown`。已识别委托操作的指定回调参数继续由委托分析生成 `callback_target`。C++ 的 `const_cast`、`static_cast`、`reinterpret_cast` 和 `dynamic_cast` 不进入调用列表或外部函数候选，但保留目标类型及内部实际调用；基本类型的函数式转换（例如 `int(Value)`）同样不作为调用，内部实际调用仍保留。普通模板调用（例如 UE `Cast<T>`）仍按调用处理；缺少类型证据的 `(UnknownName)(Value)` 无法仅凭语法区分转换与调用，继续保留未知调用候选。

`function_id` 标识所选文件中的一处具体定义，格式在原签名后增加 `|unit:line:column`。条件编译分支、头源文件和同一行上的定义各自保存符号、调用及委托结果；内部函数签名身份仍用于实体描述。依赖旧 `function_id` 的缓存需重新生成，源码位置变化也会改变该标识。

委托分析使用唯一的 `delegate_contract_revision: 2` 契约：`delegate_operations` 区分创建、绑定、添加、解除绑定、移除、清空、执行、广播和查询；以 `subject` 表达被操作的成员、参数、局部变量或返回值，旧 `event` 字段已移除。`delegate_type` 来自所选文件的声明宏、显式模板或可解析别名；`identified` 表示类型及 API 形状有依据，`candidate` 保留无法确认的调用和原因，不代表真实委托关系。未知类型不会生成虚构的限定成员名。

`callback` 按 API 参数位置识别函数、反射函数名、Lambda 或已有委托值，`callback_target` 从同一分析结果派生。`arguments` 保留对象、payload、执行参数和移除条件，`result` 记录直接承接的委托值或句柄；嵌套创建通过 `source_operation` 关联。`execution_scope` 区分外层函数与 Lambda 函数体。规则基于 UE 5.8；不读取传递头文件，不追踪变量赋值后的绑定流、不证明对象存活或回调线程安全。此次为原位契约替换，没有旧版开关或双写字段。

所有核心 CLI 都把结果写到标准输出，并包含 `schema_version`、领域事实、`validation` 和 `limits`。静态结果是源码证据，不等同于 UBT、UHT、编译器、Editor 或运行时结论。

## 文档

- [架构](docs/ARCHITECTURE.md)
- [工具清单](docs/TOOLS.md)
- [开发约定](docs/DEVELOPMENT.md)
- [测试与验证](docs/TESTING.md)

各子组件的使用方式见 [Editor 工具](edittools/README.md)、[文件图谱](information_pool/README.md)、[连接池](mcp_connection_pool/README.md) 和 [本地浏览器](show/README.md)。

核心测试可直接从仓库根目录运行：`python -m unittest discover -s tests -v`。其余组件的验证命令见 [测试与验证](docs/TESTING.md)。

## 许可证

仓库尚未声明项目级许可证。第三方许可信息见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 `LICENSES/`。
