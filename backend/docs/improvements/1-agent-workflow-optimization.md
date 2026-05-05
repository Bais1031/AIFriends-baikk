# Agent 工作流优化方案

## 背景

当前系统包含两个 LangGraph Agent（ChatGraph / MemoryGraph）和完整的记忆检索管线，已实现基本可用。但从 Agent 应用工程化的角度，存在架构、性能、能力和健壮性方面的优化空间。本文档梳理所有可优化点，按优先级分级，作为后续迭代的参考。

---

## 一、架构层面

### 1.1 MemoryGraph 是伪 Agent

**现状**：`backend/web/views/friend/message/memory/graph.py` 的 MemoryGraph 只有一个节点、无条件路由，本质上等于 `llm.invoke(messages)`。用 LangGraph 包一层没有发挥 StateGraph 的价值（条件分支、工具循环、状态管理），反而增加了编译开销。

**问题**：面试官可能质疑"为什么用 LangGraph 却只做单次 LLM 调用"——这说明对工具选型缺乏判断。

**优化方向（二选一）**：

| 方案 | 说明 | 适用场景 |
|---|---|---|
| 简化 | 去掉 MemoryGraph，直接调 `llm.invoke()` | 记忆提取逻辑简单，不需要工具辅助 |
| 增强 | 给 MemoryGraph 加工具节点（查询已有记忆、检索相关事实），做成真正的 Agent 循环，让 LLM 自主决定提取哪些记忆、如何分类 | 需要更智能的记忆管理，如跨会话关联、矛盾检测 |

**建议**：短期简化，长期增强。先去掉不必要的抽象层，等记忆系统稳定后再考虑升级为真正的 Agent。

---

### 1.2 记忆更新同步阻塞 Django Worker

**现状**：`update_memory()` 和 `update_conversation_summary()` 在 SSE 流结束后同步执行。虽然用户感知不到延迟，但会占用 Django worker 线程，高并发时成为瓶颈。

**涉及的调用链**：
```
chat.py event_stream()
    --> Message.objects.create()
    --> update_memory(friend)           # 同步，含 embedding 计算 + DB 写入
    --> update_conversation_summary()   # 同步，含 LLM 调用
```

**优化**：引入异步任务队列（Celery / Django-Q），消息保存后发布事件，worker 消费触发记忆更新。与聊天主流程彻底解耦。

```python
# 改动前
Message.objects.create(...)
if msg_count % MEMORY_UPDATE_INTERVAL == 0:
    update_memory(friend)  # 阻塞

# 改动后
Message.objects.create(...)
if msg_count % MEMORY_UPDATE_INTERVAL == 0:
    update_memory_task.delay(friend.id)  # 异步
```

---

### 1.3 双记忆系统并存 — 一致性风险

**现状**：系统同时维护两套记忆存储：

| 存储 | 类型 | 用途 |
|---|---|---|
| `MemoryItem` 模型 | 结构化 + pgvector embedding | 语义检索、去重、权重衰减 |
| `friend.memory` 文本字段 | 纯文本 | 系统提示词中的记忆注入 |

`_refresh_memory_cache()` 把 top 20 MemoryItem 拼接写入 `friend.memory`，但 `context_builder.py` 同时用了两个来源：
- 系统提示词模板里注入 `friend.memory`（通过 `PromptTemplateManager`）
- 又独立检索 top-K 条 `MemoryItem` 作为"相关记忆"层注入

**问题**：同一条记忆可能被注入两次，浪费 token 且重复强调导致 LLM 过度偏重。

**优化**：统一为单一记忆源。去掉 `friend.memory` 文本缓存，系统提示词中的记忆也走 pgvector 检索，确保每条记忆只出现一次。

```python
# 改动前：两层注入
system_prompt = PromptTemplateManager.create_system_prompt(
    friend, ..., memory_override=memory_text  # friend.memory 或检索结果
)
semantic_layer = SystemMessage(content=f"【相关记忆】\n{retrieved_memories}")

# 改动后：单一检索源
retrieved = retrieve_relevant_memories(friend, query, top_k=8)
system_prompt = PromptTemplateManager.create_system_prompt(
    friend, ..., memory_override=format_memories(retrieved)
)
# 不再注入额外的 semantic_layer
```

---

## 二、性能层面

### 2.1 记忆衰减是 N+1 查询

**现状**：`decay_memory_weights()` 遍历全部 MemoryItem 逐条计算新权重并 `save()`。500 条记忆 = 500 次 DB 写入。

**涉及文件**：`backend/web/utils/memory_retrieval.py`

**优化**：用 `bulk_update` 或原生 SQL 批量更新：

```python
# 方案 A：bulk_update
memories = MemoryItem.objects.filter(friend=friend)
updates = []
for m in memories:
    m.weight = _calc_weight(m)
    updates.append(m)
MemoryItem.objects.bulk_update(updates, ['weight'])

# 方案 B：原生 SQL（最快）
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("""
        UPDATE web_memoryitem
        SET weight = LEAST(1.0, GREATEST(0.0,
            importance * EXP(-0.693 * (EXTRACT(EPOCH FROM NOW() - create_time) / 86400) / 30)
            * (1 + 0.05 * access_count)
        ))
        WHERE friend_id = %s
    """, [friend.id])
```

---

### 2.2 MCP 工具调用无连接池

**现状**：`mcp_client.py` 的 `_call_mcp_tool()` 每次调用都新建 SSE 连接 + 初始化 session。Agent 连续调用 `web_search` 两次就要建两次连接。

**涉及文件**：`backend/web/mcp/client/mcp_client.py`

**优化**：维护长连接 session，复用已建立的连接：

```python
class MCPClientManager:
    def __init__(self):
        self._session = None
        self._session_lock = asyncio.Lock()

    async def get_session(self):
        async with self._session_lock:
            if self._session is None:
                self._session = await self._create_session()
            return self._session

    async def call_tool(self, name, arguments):
        session = await self.get_session()
        result = await session.call_tool(name, arguments)
        return result
```

需要处理连接断开后的重连逻辑（try/except + 重置 `_session = None`）。

---

### 2.3 记忆检索每次写 DB

**现状**：`retrieve_relevant_memories()` 每返回一条记忆就 `save()` 更新 `access_count` 和 `last_accessed`。检索 5 条 = 5 次写入。

**涉及文件**：`backend/web/utils/memory_retrieval.py`

**优化**：用 `bulk_update` 或 `F()` 表达式批量更新：

```python
# 方案 A：bulk_update
memories = list(queryset[:top_k])
for m in memories:
    m.access_count += 1
    m.last_accessed = now()
MemoryItem.objects.bulk_update(memories, ['access_count', 'last_accessed'])

# 方案 B：F() 表达式（不需要先查出来）
MemoryItem.objects.filter(
    id__in=[m.id for m in memories]
).update(
    access_count=F('access_count') + 1,
    last_accessed=now()
)
```

---

## 三、Agent 能力层面

### 3.1 图片分析工具与 ChatGraph 断连

**现状**：`init_tools.py` 注册了 6 个图片工具到 `MCPToolRegistry`，但 ChatGraph 通过 `MCPClientManager` 从 SSE 服务发现工具。这些图片工具不在 MCP Server 上暴露，所以 Agent 永远无法调用它们。图片分析只能在 `multimodal.py` 视图层硬编码调用。

**涉及文件**：
- `backend/web/mcp/init_tools.py`（注册但未暴露）
- `backend/web/mcp/server/web_search_server.py`（只暴露 web_search）

**优化**：在 MCP Server 上也注册图片工具，让 Agent 自主决定何时分析图片。这更符合 Agent 设计理念——工具由 Agent 按需调用，而非在视图层硬编码流程。

```python
# web_search_server.py 扩展
from web.mcp.init_tools import get_global_registry

@mcp.tool()
async def analyze_image(image_path: str) -> str:
    registry = get_global_registry()
    return await registry.call_tool("image_analysis", {"image_path": image_path})
```

---

### 3.2 工具绑定是静态的 — 每次请求都 create_app()

**现状**：`ChatGraph.create_app()` 每次调用都重新发现 MCP 工具、重新 `bind_tools`、重新编译 StateGraph。这意味着：

- 每次 HTTP 请求都有 MCP 工具发现 + 图编译开销
- 如果 MCP Server 在运行期间新增/下线工具，已有请求不会感知（因为每次都重新发现，所以反而是"感知了"，但代价是编译开销）

**涉及文件**：`backend/web/views/friend/message/chat/graph.py`

**优化**：编译好的图可以缓存复用，工具发现做定时刷新：

```python
from functools import lru_cache
import time

_cached_app = None
_cached_time = 0
CACHE_TTL = 60  # 60 秒刷新一次工具

@classmethod
def create_app(cls):
    global _cached_app, _cached_time
    now = time.time()
    if _cached_app and (now - _cached_time) < CACHE_TTL:
        return _cached_app
    # 重新发现工具 + 编译
    _cached_app = cls._build_app()
    _cached_time = now
    return _cached_app
```

---

### 3.3 没有重试和容错机制

**现状**：整个 Agent 链路没有重试——LLM 调用失败直接抛、工具执行失败直接抛、embedding 失败静默回退。

**涉及文件**：所有 graph.py、mcp_client.py、embedding.py

**优化**：

```python
# LLM 调用加重试
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def call_llm(messages):
    return llm.invoke(messages)

# 工具节点加 fallback
class SafeToolNode:
    def __call__(self, state):
        try:
            return original_tool_node(state)
        except Exception as e:
            # 返回错误信息给 LLM，让它调整策略，而非中断整个流
            return {"messages": [ToolMessage(
                content=f"工具调用失败：{e}，请尝试其他方式回答",
                tool_call_id=tool_call_id,
            )]}
```

---

### 3.4 classify_image_content 是硬编码存根

**现状**：`image_tools.py` 的 `classify_image_content()` 直接返回 `["风景", "自然"]`，完全没实现。如果 Agent 调用这个工具，永远得到错误结果。

**涉及文件**：`backend/web/mcp/tools/image_tools.py`

**优化**：要么实现（调用已有的 vision API 提取标签），要么删掉不要暴露未实现的工具。未实现的工具对 Agent 是误导。

---

## 四、Prompt / Token 层面

### 4.1 记忆注入没有独立 token 预算

**现状**：系统提示词有 token 预算（4096），但语义记忆检索（top-K=5）和对话摘要的注入没有独立预算上限。如果记忆内容很长或摘要很长，可能挤压实际对话空间。

**涉及文件**：`backend/web/utils/context_builder.py`

**优化**：给每个层设独立 token 上限，动态裁剪：

```python
MEMORY_BUDGET = 800    # 语义记忆层
SUMMARY_BUDGET = 500   # 对话摘要层
HISTORY_BUDGET = 2000  # 对话历史层
SYSTEM_RESERVE = 796   # 系统提示词预留

# 记忆裁剪
memory_text = format_memories(retrieved)
if estimate_tokens(memory_text) > MEMORY_BUDGET:
    memory_text = truncate_to_tokens(memory_text, MEMORY_BUDGET)
```

---

### 4.2 模型名硬编码

**现状**：`graph.py` 和 `memory/graph.py` 都硬编码了 `'deepseek-v3.2'`，应该走配置。

**优化**：

```python
# .env
CHAT_MODEL=deepseek-v3.2
MEMORY_MODEL=deepseek-v3.2

# graph.py
llm = ChatOpenAI(model=os.getenv('CHAT_MODEL', 'deepseek-v3.2'), ...)
```

---

## 优化优先级总览

| 优先级 | 编号 | 优化项 | 影响范围 | 工作量 |
|---|---|---|---|---|
| P0 | 1.3 | 双记忆系统一致性 | 架构 / Token 效率 | 中 |
| P0 | 3.3 | 重试与容错 | 线上稳定性 | 小 |
| P1 | 2.1 | 记忆衰减 N+1 查询 | 性能 | 小 |
| P1 | 2.3 | 记忆检索写 DB | 性能 | 小 |
| P1 | 4.1 | 记忆注入 token 预算 | 对话质量 | 小 |
| P1 | 4.2 | 模型名硬编码 | 可维护性 | 小 |
| P2 | 1.1 | MemoryGraph 伪 Agent | 架构清晰度 | 小（简化）/ 大（增强） |
| P2 | 1.2 | 记忆更新异步化 | 并发性能 | 中 |
| P2 | 3.2 | 图编译缓存 | 性能 | 小 |
| P2 | 3.4 | 删除未实现的工具 | 代码质量 | 小 |
| P3 | 2.2 | MCP 连接池 | 性能 | 中 |
| P3 | 3.1 | 图片工具接入 Agent | Agent 能力 | 中 |

---

## 面试重点展开建议

以上优化点中，最值得在面试时展开的 3 个：

### 1. 双记忆系统一致性 → 展示数据架构思维

可以引出：
- 读写分离、CQRS（查询走 pgvector，写入走 MemoryItem）
- Event Sourcing（记忆更新作为事件，查询端异步刷新物化视图）
- 数据一致性的权衡（最终一致性 vs 强一致性）

### 2. 工具动态发现与连接池 → 展示 Agent 工程化理解

可以引出：
- MCP 协议的设计意图（工具标准化、解耦、热插拔）
- 连接复用 vs 按需建立的权衡
- 工具注册中心的健康检查与故障转移

### 3. 图编译缓存 vs 实时发现 → 展示延迟与一致性的权衡

可以引出：
- Agent 的"冷启动"问题（工具发现 + 图编译 + 模型加载）
- 缓存失效策略（TTL / 事件驱动 / 手动刷新）
- 在线业务中"秒级延迟"和"工具不可用"哪个更不可接受
