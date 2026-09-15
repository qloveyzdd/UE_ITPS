# UE C++ 检查要点

以目标工程现有实现和实际 Engine 源码为准。此处是修改检查清单，不是由 Rider 自动保证的规则集。

## 文件与模块

- 沿用项目的 Public/Private 或平铺目录；跨模块暴露按现有导出宏和 MinimalAPI 用法处理。
- Build.cs 的 public/private 依赖依据接口暴露与实现使用确定；Include 的物理来源只能提供线索。
- Target.cs 沿用项目选定的 BuildSettingsVersion 与 IncludeOrderVersion，不从 EngineAssociation 字符串推导固定映射。
- 头文件中的生成头遵循项目/UHT 要求；出现 generated.h 错误时检查文件主名、反射声明、UHT 诊断与生成步骤，不直接按类名前缀重命名。

## 反射与生命周期

- 沿用 A/U/F/E/I/T 等命名惯例，依据真实继承关系命名。
- UCLASS/USTRUCT 的反射声明按已有模式使用 GENERATED_BODY；不要向 UENUM 枚举体插入该宏。
- 仅在需要反射、编辑器、Blueprint 或 GC 跟踪时添加相应标记，不把所有类默认开放给 Blueprint。
- UObject 的创建与所有权遵循项目模式；成员强引用、弱引用、软引用按生命周期选择。
- Blueprint 私有属性访问权限依据实际元数据与 UHT 结果处理，不把访问错误归结为只能公开成员。

## 复制、异步与资产

- 复制属性、注册方式、RepNotify 与 RPC 声明保持一致；只有声明要求 WithValidation 的 RPC 才补对应验证实现。
- 服务器权限、拥有者、网络执行端与对象重建按关键路径验证，不能只靠添加 HasAuthority 判断完成。
- 异步回调检查对象存活与执行线程；捕获裸 this 后转回游戏线程本身不保证对象仍有效。
- 资产引用与默认值沿用项目的 C++/Blueprint/DataAsset 分工，按加载和复用需求选择硬引用或软引用。

## 验证

先检查实际修改文件的诊断，再执行与风险匹配的构建和行为验证。缺少 Engine、Rider 或运行环境时明确说明；不把静态扫描的 ok 作为编译或运行结果。
