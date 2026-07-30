# UE ITPS v4

v4 在不修改现有 v1–v3 探针的前提下，将项目级 C++ 符号和关系写入 SQLite。

## 构建数据库

```powershell
python v4/build_graph.py `
  --project D:/Projects/MyGame/MyGame.uproject `
  --database D:/Projects/MyGameGraph.sqlite3 `
  --workers 8
```

默认 Worker 数为 `min(8, 逻辑核心数 - 1)`，也可以使用 `--workers 1`
执行确定性的单进程基准。`--cache-dir` 可指定固定缓存目录；未指定时使用
`<database>.cache/`。

每个 `.cpp + .h` 源码单元只建立一次解析上下文。类型、include、函数索引
和函数引用共享该上下文，并以原子 JSON 文件写入固定缓存。扫描中断后，
下一次运行会复用已经完成的源码单元；修改一个源文件只会失效对应源码单元。
每个函数匹配保留独立 JSON，同时每个源码单元保存一个引用汇总文件；
建图读取汇总文件，避免全缓存运行逐个读取大量小文件。

## 查询符号

```powershell
python v4/query_graph.py `
  --database D:/Projects/MyGameGraph.sqlite3 `
  --symbol "MyNamespace::UMyType" `
  --depth 2
```

查询名称不唯一时返回候选列表，不自动选择。每条关系保留
`observed`、`resolved` 或 `inferred` 可信等级，以及对应探针和源码证据。

当前扫描范围是项目及项目 Plugin 中由现有探针支持的
`.h`、`.hpp`、`.cpp` 和 `.cc`。Engine 符号保留为外部符号或外部文件，
不递归扫描 Engine 源码。
