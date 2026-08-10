# UE ITPS 工程信息池

工程信息池是绑定明确 Git 提交的只读派生视图。它复用项目工具池的确定性探针，
把项目结构、C++ 符号、关系、出现位置和原始证据写入不可变 SQLite 快照。

信息池不是第二事实源。UE 工程是事实源；激活快照只描述其记录的
`source_commit`。对话摘要、LLM 判断和未经验证的临时结果不能写入正式信息池。

## 构建与激活

工程必须位于 Git 中，HEAD 对应的 UE 工程子树必须干净。当前项目将信息池放在仓库内的
`data/` 目录；信息池目录和自定义缓存目录必须被 `.gitignore` 忽略。

```powershell
python information_pool/build_information_pool.py `
  --project D:/Projects/MyGame/MyGame.uproject `
  --pool data/MyGame `
  --workers 8
```

构建流程固定为：

```text
干净 Git HEAD
  → 独立候选数据库
  → SQLite、外键、数量、证据链和全文索引验证
  → 再次确认 HEAD 与工作区未变化
  → 保存不可变快照
  → 原子替换 manifest.json
```

扫描、写库或验证失败时，现有 `manifest.json` 和激活快照保持不变。再次构建同一
提交会复用源单元缓存；同一提交和相同输入得到相同的 `generation_id`。

## 查询

```powershell
python information_pool/query_information_pool.py `
  --pool data/MyGame `
  --operation search `
  --selector GameplayAbility
```

支持的操作：

| 操作 | 必要参数 | 作用 |
|---|---|---|
| `lookup` | `--selector` | 精确选择并遍历邻接关系；歧义时只返回候选 |
| `search` | `--selector` | FTS5/BM25 全文搜索，支持 CamelCase 拆词 |
| `hierarchy` | `--selector` | 查询继承祖先和派生类型 |
| `impact` | `--selector` | 反向追踪静态影响范围 |
| `callers` | `--selector` | 查询已解析的直接调用者 |
| `cycles` | 无 | 检测选定关系类型中的循环 |
| `path` | `--selector --target` | 查询两个实体之间的最短依赖路径 |
| `test-scope` | `--selector` | 从静态影响范围筛选相关测试文件 |
| `diff` | `--against` | 对比激活快照与历史快照或提交 |

`--snapshot` 可选择历史 `generation_id` 或 `source_commit` 前缀；未指定时读取激活
快照。`--relation-kind` 可重复使用，以限制影响、循环或路径查询的关系类型。

语义关系按“源节点、关系类型、目标节点”唯一保存，多处源码位置作为同一关系的独立
证据。已解析的调用和类型使用分别保存为 `CALLS`、`USES_TYPE`；只有无法进一步分类
的引用才保存为 `REFERENCES`。类与结构体之间的 `path` 查询会将成员关系投影到所属
类型，同时保留底层成员关系明细。委托事件使用 `PUBLISHES_EVENT`、
`SUBSCRIBES_EVENT` 和 `DISPATCHES_TO` 表示静态可见的发布、订阅及潜在回调路径；
这些关系表达可能的运行时分发，不保证订阅在每次发布时都处于有效状态。

## 目录

```text
<pool>/
├─ manifest.json                 # 唯一激活指针，原子替换
├─ snapshots/<digest>.sqlite3    # 不可变、提交绑定的正式快照
├─ cache/                        # 按源单元内容哈希失效的探针缓存
└─ .candidates/                  # 构建中的隔离候选文件
```

当前正式事实来自项目工具池支持的项目结构和 C++ 探针。Engine 符号保留为外部实体，
不递归扫描 Engine 源码。结果仍是保守静态证据，不替代 UBT、UHT、编译器、Editor
或运行时验证。
