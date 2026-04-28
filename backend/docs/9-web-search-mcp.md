## 网络搜索 MCP Server 实施记录

### 改进背景

当前 LangGraph Agent 只有 `get_time` 和 `search_knowledge_base` 两个工具：

- `get_time`：返回服务器当前时间
- `search_knowledge_base`：从 LanceDB 本地知识库检索（阿里云百炼平台文档）

这两个工具无法回答知识库之外的 **实时信息**（天气、新闻、时事、人物动态等）。

新增 **网络搜索 MCP Server**，使用 Tavily API 作为搜索后端，通过 SSE 传输暴露 `web_search` 工具，LangGraph Agent 作为 MCP Client 按需调用，与 RAG 检索形成互补。

---

### 架构设计

```
用户："今天上海天气怎么样"
    │
    ▼
LangGraph Agent (Django 进程)
    │
    ├─ LLM 判断：知识库无法回答 → 生成 tool_calls: web_search
    │
    ▼
MCP Client (Django 进程内)
    │  SSE 连接 → http://localhost:8765/sse
    ▼
MCP Server (独立进程)
    │  调用 Tavily API
    ▼
Tavily Search API
    │  返回搜索结果
    ▼
结果原路返回 → Agent 结合结果回复
```

**与 RAG 的互补关系**：

| 信息类型 | 工具 | 数据源 | 特点 |
|---|---|---|---|
| 角色设定、历史记忆 | 内置上下文 | PostgreSQL + pgvector | 私有数据，语义检索 |
| 阿里云百炼文档 | `search_knowledge_base` | LanceDB 本地知识库 | 离线索引，混合检索 |
| 实时网络信息 | `web_search` | Tavily API → 互联网 | 按需搜索，覆盖面广 |

LLM 根据工具 docstring 自主决策调用哪个工具（或都不调用）。

---

### 与现有 MCP 系统的关系

现有 `web/mcp/` 目录下的 `MCPToolRegistry` 是一个 **进程内工具注册中心**（非标准 MCP 协议），仅用于图片分析：

```
现有架构（图片 MCP）：
  MultiModalChatView → MCPToolRegistry.call_tool_sync("image_analysis") → ImageAnalysisTools → 阿里云视觉API
  特点：视图层命令式调用，结果注入上下文，Agent 不感知

新增架构（搜索 MCP）：
  LangGraph Agent → tool_calls: web_search → MCP Client → SSE → MCP Server → Tavily API
  特点：Agent 自主决策调用，通过标准 MCP 协议通信
```

两套系统共存，互不影响。图片 MCP 保持不变（视图层预调用模式适合图片分析，避免 Agent 多轮 tool_call）。

---

### 改动文件清单

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `backend/requirements.txt` | 修改 | 添加 `mcp==1.9.3`、`tavily-python==0.7.3` |
| `backend/.env` | 修改 | 添加 `TAVILY_API_KEY`、`MCP_SERVER_URL` |
| `backend/web/mcp/server/__init__.py` | 新建 | 包标记 |
| `backend/web/mcp/server/web_search_server.py` | 新建 | MCP Server 主文件，定义 `web_search` 工具 |
| `backend/web/mcp/client/__init__.py` | 新建 | 包标记 |
| `backend/web/mcp/client/mcp_client.py` | 新建 | MCP Client，连接 Server 发现工具，转为 LangChain StructuredTool |
| `backend/web/views/friend/message/chat/graph.py` | 修改 | `create_app()` 从 MCP Client 获取工具，合并到 tools 列表 |

无需改动：`context_builder.py`、`multimodal.py`、前端代码、`tool_registry.py`（图片 MCP 保持不变）。

---

### Step 1: 安装依赖

**requirements.txt** 添加：
```
mcp==1.9.3
tavily-python==0.7.3
```

- `mcp`：MCP 官方 Python SDK，提供 Server/Client/Transport 实现
- `tavily-python`：Tavily 搜索 API 客户端，专为 AI Agent 设计，返回结构化搜索结果

**.env** 添加：
```
TAVILY_API_KEY="tvly-..."
MCP_SERVER_URL="http://localhost:8765"
```

Tavily 免费额度：1000 次/月。

---

### Step 2: 创建 MCP Server

**文件**: `backend/web/mcp/server/web_search_server.py`

使用 `mcp` SDK 的 `FastMCP` 创建 SSE 传输的 MCP Server，定义 `web_search` 工具：

```python
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
```

关键设计：
- **延迟初始化 TavilyClient**：`_get_tavily()` 在首次调用时才创建客户端，避免模块加载时因缺少 `TAVILY_API_KEY` 报错
- **`load_dotenv()`**：MCP Server 作为独立进程运行，不会继承 Django 的环境变量加载，需手动加载 `.env`
- 工具 docstring 用中文，与现有 `get_time`/`search_knowledge_base` 风格一致，LLM 据此决定何时调用
- `max_results=3` 限制返回条数，避免上下文过长
- `search_depth="basic"` 平衡速度和深度（`advanced` 消耗更多额度）
- 返回结构化文本（标题+内容+来源），方便 LLM 引用
- SSE 传输模式，HTTP 长连接，适合跨进程通信

启动命令：
```bash
cd backend
python -m web.mcp.server.web_search_server
```

---

### Step 3: 创建 MCP Client

**文件**: `backend/web/mcp/client/mcp_client.py`

Client 负责：连接 MCP Server → 发现工具 → 转换为 LangChain `StructuredTool` → 供 `ChatGraph` 使用。

```python
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
```

关键设计：
- **同步封装**：`discover_tools()` 是同步接口，内部用 `asyncio.run()` 调用异步实现，供 `ChatGraph.create_app()` 直接调用
- **容错**：MCP Server 不可用时返回空列表，chat 仍可用 `get_time` + `search_knowledge_base`
- **LangChain 桥接**：`_build_args_schema()` 将 MCP Tool 的 `inputSchema` 转为 Pydantic Model，`StructuredTool.from_function()` 创建带 schema 的 LangChain Tool
- **`make_caller` 闭包**：每个工具调用时新建 SSE 连接执行 `session.call_tool()`，避免长连接超时问题
- **结果解析**：`_call_mcp_tool()` 从 `CallToolResult.content` 提取 `TextContent.text`

---

### Step 4: 集成到 ChatGraph

**文件**: `backend/web/views/friend/message/chat/graph.py`

修改 `ChatGraph.create_app()`，合并 MCP Client 发现的工具：

```python
# 改动前
from web.documents.utils.custom_embeddings import CustomEmbeddings
from web.documents.utils.hybrid_search import hybrid_search

class ChatGraph:
    @staticmethod
    def create_app():
        # ... tool 定义 ...
        tools = [get_time, search_knowledge_base]

# 改动后
from web.documents.utils.custom_embeddings import CustomEmbeddings
from web.documents.utils.hybrid_search import hybrid_search
from web.mcp.client.mcp_client import MCPClientManager

class ChatGraph:
    @staticmethod
    def create_app():
        # ... tool 定义 ...
        tools = [get_time, search_knowledge_base]

        # 从 MCP Server 发现工具，容错：Server 不可用时跳过
        try:
            mcp_client = MCPClientManager()
            mcp_tools = mcp_client.discover_tools()
            tools.extend(mcp_tools)
        except Exception as e:
            print(f"[ChatGraph] MCP 工具发现失败: {e}，仅使用内置工具")
```

LLM 通过 `bind_tools(tools)` 看到所有工具（包括 `web_search`），自主决定何时调用。

**工具决策流程**：

```
用户消息进入 LangGraph Agent
    │
    ▼
LLM 分析消息意图 + 工具描述
    │
    ├─ 需要精确时间 → tool_calls: get_time
    ├─ 查询百炼平台文档 → tool_calls: search_knowledge_base
    ├─ 查询实时网络信息 → tool_calls: web_search
    └─ 无需工具 → 直接回复
    │
    ▼
should_continue() 检查 tool_calls
    │
    ├─ 有 → ToolNode 执行 → 结果注入 → 返回 Agent 重新生成
    └─ 无 → END
```

---

### 踩坑记录

**坑 1：MCP Server 启动时 TavilyClient 报错**

MCP Server 作为独立进程运行，模块加载时 `TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))` 如果环境变量未设置会直接报错退出。

解决：改为延迟初始化 `_get_tavily()`，首次调用时才创建客户端。同时在 Server 入口添加 `load_dotenv()` 加载 `.env` 文件。

**坑 2：MCP Server 进程不加载 .env**

Django 通过 `settings.py` 中的 `load_dotenv()` 加载环境变量，但 MCP Server 是独立进程，不会执行 Django 的启动流程。

解决：在 `web_search_server.py` 入口处显式调用 `load_dotenv()`。

**坑 3：ChatGraph 中直接调 async 函数**

计划阶段写的是 `asyncio.run(mcp_client.discover_tools())`，但 `discover_tools()` 在 `create_app()` 中调用，Django 的 runserver 可能已在事件循环中，直接 `asyncio.run()` 会冲突。

解决：将 `MCPClientManager.discover_tools()` 封装为同步接口，内部处理 `asyncio.run()`，ChatGraph 直接调用 `mcp_client.discover_tools()` 即可。

---

### 验证步骤

1. **启动 MCP Server**：
   ```bash
   cd backend && python -m web.mcp.server.web_search_server
   ```
   预期输出：`Uvicorn running on http://0.0.0.0:8765`

2. **验证工具发现**：另开终端测试 MCP Client
   ```python
   from dotenv import load_dotenv
   load_dotenv()
   from web.mcp.client.mcp_client import MCPClientManager
   client = MCPClientManager()
   tools = client.discover_tools()
   # 预期输出: [MCP Client] 从 http://localhost:8765 发现 1 个工具: ['web_search']
   ```

3. **验证搜索调用**：
   ```python
   web_search = [t for t in tools if t.name == 'web_search'][0]
   result = web_search.invoke({'query': '上海今天天气'})
   print(result)
   # 预期: 返回实时天气搜索结果
   ```

4. **启动 Django**：
   ```bash
   python manage.py runserver
   ```

5. **测试实时信息问题**：
   ```json
   {"friend_id": 1, "message": "今天上海天气怎么样"}
   ```
   预期：Agent 调用 `web_search`，结合搜索结果回复

6. **测试知识库问题**：
   ```json
   {"friend_id": 1, "message": "阿里云百炼怎么用"}
   ```
   预期：Agent 调用 `search_knowledge_base`，不调用 `web_search`

7. **测试容错**：停掉 MCP Server 后发送消息，确认 chat 正常工作（仅少一个工具）

---

### 目录结构

改动后 `backend/web/mcp/` 结构：

```
web/mcp/
├── __init__.py
├── tool_registry.py        # 现有：进程内工具注册中心（图片 MCP）
├── init_tools.py           # 现有：图片工具注册
├── tools/
│   ├── __init__.py
│   └── image_tools.py      # 现有：阿里云视觉 API 调用
├── server/                 # 新增：MCP Server
│   ├── __init__.py
│   └── web_search_server.py
└── client/                 # 新增：MCP Client
    ├── __init__.py
    └── mcp_client.py
```
