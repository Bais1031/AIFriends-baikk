"""
本地工具注册表
用于管理进程内的工具调用（非 MCP 协议）
"""
import time
from typing import Dict, Any, Callable, List, Optional
from dataclasses import dataclass


@dataclass
class ToolInfo:
    name: str
    description: str
    implementation: Callable
    usage_count: int = 0
    total_time: float = 0.0


class LocalToolRegistry:
    """本地工具注册表（进程内调用，非 MCP 协议）"""

    def __init__(self):
        self.tools: Dict[str, ToolInfo] = {}

    def register_tool(self, name: str, description: str, implementation: Callable):
        self.tools[name] = ToolInfo(
            name=name,
            description=description,
            implementation=implementation
        )

    async def call_tool(self, name: str, params: Dict[str, Any]) -> Any:
        if name not in self.tools:
            raise ValueError(f"Tool {name} not registered")

        tool = self.tools[name]
        start_time = time.time()

        try:
            result = await tool.implementation(**params)
            duration = time.time() - start_time
            tool.usage_count += 1
            tool.total_time += duration
            print(f"[LocalTool] '{name}' called, duration: {duration:.3f}s, usage_count: {tool.usage_count}")
            return result
        except Exception as e:
            print(f"[LocalTool] Error calling '{name}': {str(e)}")
            raise

    def call_tool_sync(self, name: str, params: Dict[str, Any]) -> Any:
        import asyncio

        if name not in self.tools:
            raise ValueError(f"Tool {name} not registered")

        tool = self.tools[name]
        start_time = time.time()

        try:
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, tool.implementation(**params))
                    result = future.result()
            except RuntimeError:
                result = asyncio.run(tool.implementation(**params))

            duration = time.time() - start_time
            tool.usage_count += 1
            tool.total_time += duration
            print(f"[LocalTool] '{name}' called (sync), duration: {duration:.3f}s, usage_count: {tool.usage_count}")
            return result
        except Exception as e:
            print(f"[LocalTool] Error calling '{name}' (sync): {str(e)}")
            raise

    def get_tool_info(self, name: str) -> Optional[ToolInfo]:
        return self.tools.get(name)

    def list_tools(self) -> List[str]:
        return list(self.tools.keys())

    def get_tool_stats(self) -> Dict[str, Dict[str, Any]]:
        stats = {}
        for name, tool in self.tools.items():
            avg_time = tool.total_time / tool.usage_count if tool.usage_count > 0 else 0
            stats[name] = {
                "usage_count": tool.usage_count,
                "total_time": tool.total_time,
                "avg_time": avg_time
            }
        return stats
