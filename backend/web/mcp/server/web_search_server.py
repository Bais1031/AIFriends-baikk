"""
网络搜索 MCP Server
使用 FastMCP + SSE 传输，暴露 web_search 工具供 LangGraph Agent 调用
"""
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()
from tavily import TavilyClient

mcp = FastMCP("web-search-server", host="0.0.0.0", port=8765)
_tavily = None


def _get_tavily() -> TavilyClient:
    global _tavily
    if _tavily is None:
        _tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    return _tavily


@mcp.tool()
def web_search(query: str) -> str:
    """当需要搜索互联网上的实时信息时调用此函数，例如天气、新闻、时事、人物动态等。输入为搜索关键词，输出为搜索结果摘要。"""
    response = _get_tavily().search(query, max_results=3, search_depth="basic")
    results = []
    for r in response.get("results", []):
        results.append(f"标题：{r['title']}\n内容：{r['content']}\n来源：{r['url']}")
    return "\n\n---\n\n".join(results) if results else "未找到相关搜索结果"


if __name__ == "__main__":
    mcp.run(transport="sse")
