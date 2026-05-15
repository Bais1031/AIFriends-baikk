"""
MCP 工具服务器
使用 FastMCP + SSE 传输，暴露以下工具供 LangGraph Agent 调用：
- web_search: 网络搜索
- weather_query: 天气查询
"""
import os

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()
from tavily import TavilyClient

mcp = FastMCP("tool-server", host="0.0.0.0", port=8765)

# ── 网络搜索 ──────────────────────────────────────────────

_tavily = None


def _get_tavily() -> TavilyClient:
    global _tavily
    if _tavily is None:
        _tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    return _tavily


@mcp.tool()
def web_search(query: str) -> str:
    """当需要搜索互联网上的实时信息时调用此函数，例如新闻、时事、人物动态等。输入为搜索关键词，输出为搜索结果摘要。"""
    response = _get_tavily().search(query, max_results=3, search_depth="basic")
    results = []
    for r in response.get("results", []):
        results.append(f"标题：{r['title']}\n内容：{r['content']}\n来源：{r['url']}")
    return "\n\n---\n\n".join(results) if results else "未找到相关搜索结果"


# ── 天气查询 ──────────────────────────────────────────────

_QWEATHER_KEY = None
_QWEATHER_GEO_API = "https://geoapi.qweather.com/v2/city/lookup"
_QWEATHER_WEATHER_API = "https://devapi.qweather.com/v7"


def _get_qweather_key() -> str:
    global _QWEATHER_KEY
    if _QWEATHER_KEY is None:
        _QWEATHER_KEY = os.getenv("QWEATHER_API_KEY", "")
    return _QWEATHER_KEY


def _lookup_city(location: str):
    """城市名 → (city_id, city_name, province) 或 None"""
    key = _get_qweather_key()
    if not key:
        return None
    try:
        resp = httpx.get(_QWEATHER_GEO_API,
                         params={"location": location, "key": key, "lang": "zh"},
                         timeout=5)
        data = resp.json()
        if data.get("code") == "200" and data.get("location"):
            loc = data["location"][0]
            return loc["id"], loc["name"], loc["adm1"]
    except Exception as e:
        print(f"[Weather] 城市查找失败: {e}")
    return None


@mcp.tool()
def weather_query(location: str, days: int = 0) -> str:
    """查询指定城市的天气信息。当用户询问天气、气温、是否下雨等问题时调用此函数。location 为城市名（如"北京"、"上海"），days 为预报天数（0=仅当前天气，1-3=含未来预报，默认0）。"""
    key = _get_qweather_key()
    if not key:
        return "天气服务未配置，请在 .env 中设置 QWEATHER_API_KEY"

    # MCP 客户端可能将 int 参数传为字符串
    if isinstance(days, str):
        try:
            days = int(days)
        except ValueError:
            days = 0
    days = max(0, min(days, 3))

    city_info = _lookup_city(location)
    if not city_info:
        return f"未找到城市「{location}」，请检查城市名是否正确"

    city_id, city_name, province = city_info
    parts = [f"{province} {city_name}"]

    # 实时天气
    try:
        resp = httpx.get(f"{_QWEATHER_WEATHER_API}/weather/now",
                         params={"location": city_id, "key": key, "lang": "zh"},
                         timeout=5)
        now = resp.json().get("now", {})
        parts.append(
            f"当前：{now.get('text', '未知')}，"
            f"温度 {now.get('temp', '?')}°C，"
            f"体感 {now.get('feelsLike', '?')}°C，"
            f"{now.get('windDir', '?')} {now.get('windScale', '?')}级，"
            f"湿度 {now.get('humidity', '?')}%"
        )
    except Exception as e:
        parts.append(f"实时天气获取失败: {e}")

    # 预报
    if days > 0:
        try:
            resp = httpx.get(f"{_QWEATHER_WEATHER_API}/weather/3d",
                             params={"location": city_id, "key": key, "lang": "zh"},
                             timeout=5)
            daily = resp.json().get("daily", [])[:days]
            for d in daily:
                parts.append(
                    f"{d.get('fxDate', '?')}：{d.get('textDay', '?')}→{d.get('textNight', '?')}，"
                    f"{d.get('tempMin', '?')}~{d.get('tempMax', '?')}°C"
                )
        except Exception as e:
            parts.append(f"天气预报获取失败: {e}")

    return "\n".join(parts)


if __name__ == "__main__":
    mcp.run(transport="sse")
