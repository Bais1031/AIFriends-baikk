"""
MCP Client 管理器
连接 MCP Server，发现工具并转为 LangChain Tool，供 ChatGraph 使用
"""
import os
import asyncio
from typing import Optional

from langchain_core.tools import StructuredTool
from mcp import ClientSession
from mcp.client.sse import sse_client
from pydantic import BaseModel, create_model


def _build_args_schema(input_schema: dict) -> type[BaseModel]:
    """将 MCP Tool 的 inputSchema 转为 Pydantic Model，供 StructuredTool 使用"""
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))
    field_definitions = {}
    for name, prop in properties.items():
        prop_type = str
        default = ... if name in required else None
        field_definitions[name] = (prop_type, default)
    return create_model("MCPToolArgs", **field_definitions)


class MCPClientManager:
    """MCP Client 管理器：连接 MCP Server，发现工具并转为 LangChain Tool"""

    def __init__(self, server_url: Optional[str] = None):
        self.server_url = server_url or os.getenv("MCP_SERVER_URL", "http://localhost:8765")

    def discover_tools(self) -> list:
        """同步接口：连接 MCP Server，获取工具列表，转为 LangChain Tool"""
        try:
            return asyncio.run(self._discover_tools())
        except Exception as e:
            print(f"[MCP Client] 连接 MCP Server 失败: {e}，跳过 MCP 工具")
            return []

    async def _discover_tools(self) -> list:
        """异步发现 MCP 工具并转为 LangChain StructuredTool"""
        tools = []
        async with sse_client(f"{self.server_url}/sse") as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()

                for mcp_tool in result.tools:
                    args_schema = _build_args_schema(mcp_tool.inputSchema)

                    def make_caller(server_url: str, tool_name: str):
                        def _call_tool(**kwargs) -> str:
                            return asyncio.run(
                                self._call_mcp_tool(server_url, tool_name, kwargs)
                            )
                        return _call_tool

                    lc_tool = StructuredTool.from_function(
                        func=make_caller(self.server_url, mcp_tool.name),
                        name=mcp_tool.name,
                        description=mcp_tool.description,
                        args_schema=args_schema,
                    )
                    tools.append(lc_tool)

        print(f"[MCP Client] 从 {self.server_url} 发现 {len(tools)} 个工具: "
              f"{[t.name for t in tools]}")
        return tools

    @staticmethod
    async def _call_mcp_tool(server_url: str, name: str, arguments: dict) -> str:
        """通过 MCP 协议调用 Server 端工具"""
        async with sse_client(f"{server_url}/sse") as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                text_parts = [
                    c.text for c in result.content
                    if hasattr(c, "type") and c.type == "text"
                ]
                return "\n".join(text_parts) if text_parts else str(result.content)
