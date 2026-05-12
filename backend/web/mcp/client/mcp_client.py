"""
MCP Client 管理器
连接 MCP Server，发现工具并转为 LangChain Tool，供 ChatGraph 使用
"""
import os
import time
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


# 断路器状态
_CIRCUIT_BREAKER_THRESHOLD = 3   # 连续失败次数达到此值后打开断路器
_CIRCUIT_BREAKER_COOLDOWN = 300  # 断路器打开后冷却 5 分钟
_circuit_state = {
    "fail_count": 0,
    "open_until": 0,  # 断路器打开的截止时间戳
}


def _is_circuit_open() -> bool:
    """断路器是否处于打开状态"""
    if _circuit_state["open_until"] == 0:
        return False
    if time.time() >= _circuit_state["open_until"]:
        # 冷却期结束，进入半开状态，允许重试
        _circuit_state["open_until"] = 0
        _circuit_state["fail_count"] = 0
        return False
    return True


def _record_failure():
    """记录一次失败，达到阈值后打开断路器"""
    _circuit_state["fail_count"] += 1
    if _circuit_state["fail_count"] >= _CIRCUIT_BREAKER_THRESHOLD:
        _circuit_state["open_until"] = time.time() + _CIRCUIT_BREAKER_COOLDOWN
        print(f"[MCP Circuit] 断路器已打开，{_CIRCUIT_BREAKER_COOLDOWN}s 内跳过 MCP 工具")


def _record_success():
    """记录一次成功，重置失败计数"""
    _circuit_state["fail_count"] = 0


class MCPClientManager:
    """MCP Client 管理器：连接 MCP Server，发现工具并转为 LangChain Tool"""

    def __init__(self, server_url: Optional[str] = None):
        self.server_url = server_url or os.getenv("MCP_SERVER_URL", "http://localhost:8765")

    def discover_tools(self) -> list:
        """同步接口：连接 MCP Server，获取工具列表，转为 LangChain Tool"""
        if _is_circuit_open():
            print("[MCP Circuit] 断路器打开中，跳过 MCP 工具发现")
            return []
        try:
            return asyncio.run(self._discover_tools())
        except Exception as e:
            print(f"[MCP Client] 连接 MCP Server 失败: {e}，跳过 MCP 工具")
            _record_failure()
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

        _record_success()
        print(f"[MCP Client] 从 {self.server_url} 发现 {len(tools)} 个工具: "
              f"{[t.name for t in tools]}")
        return tools

    @staticmethod
    async def _call_mcp_tool(server_url: str, name: str, arguments: dict,
                             max_retries: int = 1, timeout: float = 10.0) -> str:
        """通过 MCP 协议调用 Server 端工具，带重试、超时和 fallback"""
        last_error = None
        for attempt in range(1 + max_retries):
            try:
                async with asyncio.timeout(timeout):
                    async with sse_client(f"{server_url}/sse") as (read, write):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            result = await session.call_tool(name, arguments)
                            text_parts = [
                                c.text for c in result.content
                                if hasattr(c, "type") and c.type == "text"
                            ]
                            _record_success()
                            return "\n".join(text_parts) if text_parts else str(result.content)
            except Exception as e:
                last_error = e
                print(f"[MCP Client] 工具 {name} 调用失败 (尝试 {attempt + 1}/{1 + max_retries}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(1)

        _record_failure()
        print(f"[MCP Client] 工具 {name} 最终调用失败: {last_error}")
        return f"工具 {name} 暂时不可用，请直接回答用户问题。"
