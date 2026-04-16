"""
MCP工具注册中心
用于统一管理和调用MCP工具
"""
import time
from typing import Dict, Any, Callable, List, Optional
from dataclasses import dataclass
import json


@dataclass
class ToolInfo:
    """工具信息"""
    name: str
    description: str
    schema: Dict[str, Any]
    implementation: Callable
    usage_count: int = 0
    total_time: float = 0.0


class MCPToolRegistry:
    """MCP工具注册中心"""

    def __init__(self):
        self.tools: Dict[str, ToolInfo] = {}

    def register_tool(self, name: str, description: str, implementation: Callable):
        """注册MCP工具"""
        self.tools[name] = ToolInfo(
            name=name,
            description=description,
            schema=self._generate_schema(implementation),
            implementation=implementation
        )

    async def call_tool(self, name: str, params: Dict[str, Any]) -> Any:
        """调用MCP工具"""
        if name not in self.tools:
            raise ValueError(f"Tool {name} not registered")

        tool = self.tools[name]
        start_time = time.time()

        try:
            result = await tool.implementation(**params)
            duration = time.time() - start_time

            # 更新统计信息
            tool.usage_count += 1
            tool.total_time += duration

            # 记录日志
            print(f"[MCP] Tool '{name}' called, duration: {duration:.3f}s, usage_count: {tool.usage_count}")

            return result
        except Exception as e:
            print(f"[MCP] Error calling tool '{name}': {str(e)}")
            raise

    def _generate_schema(self, implementation: Callable) -> Dict[str, Any]:
        """生成工具的JSON Schema"""
        # 简化版本，实际可以使用inspect模块来生成完整的schema
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    def get_tool_info(self, name: str) -> Optional[ToolInfo]:
        """获取工具信息"""
        return self.tools.get(name)

    def list_tools(self) -> List[str]:
        """列出所有工具名称"""
        return list(self.tools.keys())

    def get_tool_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取工具统计信息"""
        stats = {}
        for name, tool in self.tools.items():
            avg_time = tool.total_time / tool.usage_count if tool.usage_count > 0 else 0
            stats[name] = {
                "usage_count": tool.usage_count,
                "total_time": tool.total_time,
                "avg_time": avg_time
            }
        return stats
