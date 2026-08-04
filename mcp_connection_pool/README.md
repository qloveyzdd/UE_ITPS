# MCP 连接池

这是一个与现有工具池、V4 图谱和源码扫描 Worker 完全独立的被动连接目录。

当前只注册一个目标 Provider：`ue5.8-editor`。连接池只读取宿主已经暴露的 MCP 工具清单，不启动、不重连、不关闭 MCP，也不运行 Unreal Editor 或任何外部命令。

## 使用方式

宿主负责把当前可见的 MCP 工具名和可信元数据转换成连接记录：

```python
from mcp_connection_pool import (
    ExternalMcpConnectionPool,
    UE58_PROVIDER_ID,
    connections_from_tool_inventory,
    get_provider_requirement,
)

def discover():
    return connections_from_tool_inventory(
        host_tool_names,
        metadata_by_server=host_mcp_metadata,
    )

pool = ExternalMcpConnectionPool(discover)
requirement = get_provider_requirement(
    UE58_PROVIDER_ID,
    project_file="E:/Games/MyGame/MyGame.uproject",
)
result = pool.resolve(requirement)
```

每次 `resolve()` 都重新读取宿主清单。未发现连接时返回 `missing` 和可重试的用户提示；用户在外部启动并连接 MCP 后，再次调用即可继续。

连接只有同时满足以下条件才会变成 `available`：

- Provider 为 `ue5.8-editor` 或类型为 `unreal-editor`。
- Engine 版本为 `5.8.*`。
- 声明只读访问。
- 提供 Asset Registry、Blueprint 和 Blueprint Graph 能力。
- 请求指定工程时，连接声明的 `.uproject` 与目标一致。
- 连接当前健康，且没有第二个同样兼容的连接。

连接池只负责发现与选择，不负责执行 MCP 工具。工具调用必须由宿主在选中连接后完成。

## 验证

```powershell
python -m unittest discover -s mcp_connection_pool/tests -v
```
