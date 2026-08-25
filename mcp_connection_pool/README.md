# UE MCP 连接池

`mcp_connection_pool/` 是被动连接目录：它只检查宿主已经暴露的 MCP 连接，不启动、停止、重连或管理外部进程。

当前唯一 Provider 是 `ue5.8-editor`。匹配条件包括：

- Unreal Engine 5.8；
- 只读访问声明；
- Asset Registry、Blueprint 和 Blueprint Graph 能力；
- 调用方指定时，连接绑定的 `.uproject` 必须一致。

解析结果为 `available`、`missing`、`incompatible`、`ambiguous` 或 `unhealthy`。多个兼容连接不会被静默选择。

```bash
python -m unittest discover -s mcp_connection_pool/tests -t . -v
```
