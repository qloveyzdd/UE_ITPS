# 知识图谱查询

这个目录只包含面向已构建知识图谱的查询入口、查询实现和输出契约。它不读取原始工程文件，也不替代 `edittools/` 下的 Editor 扫描和图谱构建工具。

入口：

```powershell
python edittools/knowledge_query/ue_query_knowledge_graph.py --input graph.json --operation search --query Death
python edittools/knowledge_query/ue_query_knowledge_graph.py --input graph.json --operation inspect --select <node-id>
python edittools/knowledge_query/ue_query_knowledge_graph.py --input graph.json --operation neighbors --select <node-id> --direction outgoing --relation CALLS
python edittools/knowledge_query/ue_query_knowledge_graph.py --input graph.json --operation trace --select <node-id> --direction outgoing --depth 2
python edittools/knowledge_query/ue_query_knowledge_graph.py --input graph.json --operation impact --select <node-id> --depth 2
python edittools/knowledge_query/ue_query_knowledge_graph.py --input graph.json --operation evidence --select <relation-id>
python edittools/knowledge_query/ue_query_knowledge_graph.py --input graph.json --operation uncertainty
python edittools/knowledge_query/ue_query_knowledge_graph.py --input graph.json --operation domain --select equipment
python edittools/knowledge_query/ue_query_knowledge_graph.py --input graph.json --operation compare --select <left-id> --select <right-id>
```

推荐 LLM 按“`search` 定位 → `inspect` 确认 → `neighbors/trace/impact` 追踪 → `evidence` 回查”的顺序调用。所有结果都保留 `node_id`、`relation_id` 和 `evidence_id`，便于后续查询继续使用稳定选择器。

旧版 `--level overview/system/entity/evidence` 仍然可用，便于已有调用方迁移。

