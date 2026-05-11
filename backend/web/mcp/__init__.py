# MCP (Model Context Protocol) 客户端与服务端实现
# 本目录只包含遵循 MCP 协议的组件：
# - client/mcp_client.py: MCP 客户端，通过 SSE 连接 MCP Server 发现并调用工具
# - server/web_search_server.py: MCP 服务端，使用 FastMCP 注册工具供客户端发现
#
# 本地工具注册表（非 MCP 协议）已迁移至 web/utils/local_tool_registry.py
