# 3.2 图编译缓存 — 改进方案

## 问题

`ChatGraph.create_app()` 每次 HTTP 请求都执行完整的构建流程：

1. MCP Server 工具发现（SSE 连接 + session 初始化 + `list_tools`）
2. `bind_tools()` 将工具绑定到 LLM
3. `StateGraph` 编译（节点注册 + 边构建 + `compile()`）

其中 MCP 工具发现涉及网络 I/O，图编译涉及 LangGraph 内部校验，两者合计耗时可达数百毫秒。在高并发下，每个请求都重复这些操作，浪费 worker 线程。

## 方案

**TTL 缓存 + 双重检查锁**：编译好的图缓存为类变量，60 秒内直接复用；过期后重新构建，用 `threading.Lock` 防止并发请求重复编译。

### 选择 TTL 而非永久缓存的原因

- MCP Server 可能运行期间新增/下线工具，永久缓存会导致 Agent 无法感知变化
- 60 秒 TTL 在"及时感知工具变化"和"减少重复编译"之间取得平衡
- 聊天场景对工具变化的实时性要求不高，最多 60 秒延迟完全可接受

## 实施改动

### 文件：`backend/web/views/friend/message/chat/graph.py`

**改动前**：`create_app()` 是 `@staticmethod`，每次调用都重新构建。

**改动后**：

```python
import threading
import time

_CACHE_TTL = 60  # 图编译缓存 60 秒


class ChatGraph:
    _cached_app = None
    _cached_time = 0
    _lock = threading.Lock()

    @classmethod
    def create_app(cls):
        # 快路径：缓存未过期直接返回
        if cls._cached_app and (time.time() - cls._cached_time) < _CACHE_TTL:
            return cls._cached_app
        # 慢路径：加锁构建，双重检查避免重复编译
        with cls._lock:
            if cls._cached_app and (time.time() - cls._cached_time) < _CACHE_TTL:
                return cls._cached_app
            cls._cached_app = cls._build_app()
            cls._cached_time = time.time()
            return cls._cached_app

    @classmethod
    def _build_app(cls):
        # 原 create_app() 的全部逻辑，原样搬入
        ...
```

### 调用方无需改动

`chat.py` 和 `multimodal.py` 仍调用 `ChatGraph.create_app()`，签名不变。

## 权衡

| 方面 | 改动前 | 改动后 |
|---|---|---|
| 每次请求开销 | MCP 发现 + 图编译 | 60s 内仅一次时间戳比较 |
| MCP 工具更新感知 | 实时 | 最多延迟 60s |
| 并发安全 | 无状态，天然安全 | Lock 保护，不会重复编译 |
| 内存 | 无额外占用 | 常驻一个编译后的图对象 |

## 后续可选优化

- 如果需要手动触发刷新（如部署新工具后），可添加 `cls.invalidate_cache()` 方法将 `_cached_app` 置为 `None`
- 如果 TTL 不够灵活，可改为监听 MCP Server 的 `tools/list_changed` 事件主动失效
