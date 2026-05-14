# 5 外部 API 三层保护机制

## 问题

项目中所有外部 API 调用（LLM、TTS、ASR、Embedding、Vision、OCR）缺少超时、重试和降级保护。阿里云 DashScope 或 WebSocket 服务抖动时：

- 无超时 → 请求挂死，Django worker 线程被永久占用
- 无重试 → 瞬时网络抖动直接失败，本可成功的请求被丢弃
- 无降级 → TTS 语音服务故障时，文本输出也跟着丢失，用户什么都收不到

## 方案：三层保护

```
请求进入
  │
  ├─ 第 1 层：超时 ─── 防止挂死，快速失败
  │     失败 ↓
  │
  ├─ 第 2 层：重试 ─── 瞬时抖动自动恢复
  │     耗尽 ↓
  │
  └─ 第 3 层：降级 ─── 核心功能不丢失
```

三层各自独立，逐级兜底：

1. **超时**：每个外部调用设合理超时，保证不会无限阻塞
2. **重试**：幂等 API 失败后指数退避重试，应对瞬时网络抖动
3. **降级**：非核心服务失败时，核心服务（文本输出）不受影响

## 第 1 层：超时

### 原理

外部调用没有超时上限时，如果对端服务无响应，调用方线程会一直阻塞。Django 每个请求占用一个线程，线程耗尽后新请求全部排队超时。加上超时后，最坏情况下也能在超时时间内释放线程。

### 实现

| 调用点 | 文件 | 超时配置 | 说明 |
|--------|------|----------|------|
| ChatOpenAI (聊天) | `graph.py` | `request_timeout=30` | LangChain 的 request_timeout 覆盖连接建立+首 token 等待 |
| ChatOpenAI (记忆) | `memory/graph.py` | `request_timeout=30` | 同上 |
| ChatOpenAI (摘要) | `context_builder.py` | `request_timeout=30` | 同上 |
| OpenAI Embedding (记忆) | `embedding.py` | `timeout=10` | Embedding 请求小且快，10s 足够 |
| OpenAI Embedding (知识库) | `custom_embeddings.py` | `timeout=10` | 同上 |
| websockets TTS | `chat.py`, `multimodal.py` | `open_timeout=10, close_timeout=5, ping_timeout=20` | WebSocket 三阶段超时 |
| websockets ASR | `asr/asr.py` | `open_timeout=10, close_timeout=5, ping_timeout=20` | 同上 |
| AsyncClient Vision | `image_tools.py` | `timeout=60` | 图片+大模型推理较慢，留 60s |
| AsyncClient OCR | `image_tools.py` | `timeout=30` | OCR 相对较快 |

### 为什么流式 LLM 不整体重试

流式输出已经开始后，部分 token 已发送给前端，整体重试会导致重复输出。`request_timeout` 只保护连接建立和首 token 等待阶段，一旦开始流式输出就不再受此超时约束。

## 第 2 层：重试

### 原理

瞬时网络抖动（如 TCP 重传、负载均衡切换）通常在 1-2 秒内恢复。对于幂等 API（多次调用结果一致），失败后立即重试大概率成功。指数退避（1s → 2s → 4s）避免在服务端过载时雪崩式重试。

### 实现

使用 tenacity 库的装饰器：

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def _call_vision_api(self, image_url, prompt):
    # Vision API 调用
    ...
```

| 调用点 | 文件 | 重试策略 | 重试耗尽后 |
|--------|------|----------|-----------|
| Embedding (记忆) | `embedding.py` | 3 次，指数退避 1-10s | 返回 None，记忆向量缺失 |
| Embedding (知识库) | `custom_embeddings.py` | 3 次，指数退避 1-10s | 抛异常，知识库查询失败 |
| Vision API | `image_tools.py` | 3 次，指数退避 1-10s | 降级到 PIL fallback（只输出尺寸信息） |
| OCR API | `image_tools.py` | 3 次，指数退避 1-10s | 返回空文本，图片描述不含 OCR 内容 |

### 哪些 API 不重试

| 调用点 | 原因 |
|--------|------|
| ChatOpenAI (流式) | 已输出部分 token 后重试会导致重复，由 request_timeout 兜住连接阶段 |
| TTS WebSocket | 非幂等（语音合成有状态），由第 3 层降级兜住 |
| ASR WebSocket | 非幂等（语音识别有状态），由第 3 层降级兜住 |
| MCP 工具调用 | 已有独立的重试机制（`mcp_client.py` 中 max_retries=1） |

## 第 3 层：降级

### 原理

聊天应用的核心价值是文本交互，语音合成（TTS）和图片分析是增强功能。当增强服务不可用时，应确保核心功能（文本输出）不受影响，而非整个请求崩溃。

### 实现

#### TTS 降级：连接失败 → 纯文本流

`chat.py` 和 `multimodal.py` 的 `run_tts_tasks` 方法：

```python
async def run_tts_tasks(self, app, inputs, mq, speaker):
    try:
        # 正常路径：WebSocket 连接 TTS，并行产出文本+音频
        async with websockets.connect(...) as ws:
            await asyncio.gather(
                self.tts_sender(app, inputs, mq, ws, task_id),  # 文本→TTS
                self.tts_receiver(mq, ws),                       # 音频→前端
            )
    except Exception as e:
        # 降级路径：TTS 不可用，只产出文本
        print(f"[TTS] 连接失败，降级为纯文本流: {e}")
        await self._text_only_stream(app, inputs, mq)

async def _text_only_stream(self, app, inputs, mq):
    """TTS 不可用时的降级方案：只输出文本，不合成语音"""
    async for msg, metadata in app.astream(inputs, stream_mode="messages"):
        if isinstance(msg, BaseMessageChunk):
            if msg.content:
                mq.put_nowait({'content': msg.content})
            if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                mq.put_nowait({'usage': msg.usage_metadata})
```

#### TTS 中途断开：音频跳过，文本不丢

`tts_sender` 和 `tts_receiver` 各自 try/except：

```python
async def tts_sender(self, app, inputs, mq, ws, task_id):
    async for msg, metadata in app.astream(...):
        if msg.content:
            try:
                await ws.send(...)   # 发给 TTS，失败也不影响文本
            except Exception:
                print("[TTS] 发送失败，降级为纯文本")
            mq.put_nowait({'content': msg.content})  # 文本始终入队

async def tts_receiver(self, mq, ws):
    try:
        async for msg in ws:
            # 接收音频...
    except Exception:
        print("[TTS] 音频接收异常，跳过音频")  # 音频丢了，文本还在
```

#### ASR 降级：识别失败 → 返回空文本

```python
def post(self, request):
    try:
        text = asyncio.run(self.run_asr_tasks(pcm_data))
    except Exception as e:
        print(f"[ASR] 语音识别失败: {e}")
        return Response({'result': 'error', 'text': ''})
    return Response({'result': 'success', 'text': text})
```

### 降级路径汇总

| 服务 | 失败场景 | 降级行为 | 用户感知 |
|------|---------|---------|---------|
| TTS | WebSocket 连接失败 | 纯文本流，无语音 | 能看到回复，听不到语音 |
| TTS | 推理中途断开 | 跳过后续音频，文本完整 | 语音中断，文字完整 |
| ASR | 语音识别失败 | 返回空文本 | 语音消息无法转文字 |
| Vision | API 重试耗尽 | PIL fallback（尺寸信息） | AI 只知图片尺寸，不知内容 |
| OCR | API 重试耗尽 | 跳过 OCR 文本 | 图片中文字不被识别 |

## 与 MCP 断路器的关系

MCP 工具调用有独立的断路器机制（`mcp_client.py`），属于第 2 层和第 3 层之间的补充：

- **第 2 层补充**：MCP 工具调用失败后重试 1 次（比其他 API 少，因为 MCP 调用发生在 LLM ReAct 循环内，重试太久会让用户等待过久）
- **断路器**：连续失败 3 次后，5 分钟内跳过 MCP 工具发现，避免每次请求都尝试连接已挂掉的服务

详见 `4-graph-compile-cache.md` 和 `mcp_client.py` 中的 `_circuit_state`。

## 全景图

```
用户发消息
  │
  ▼
Django View (chat.py / multimodal.py)
  │
  ├─ ChatGraph.create_app()  ─── [TTL 缓存 5min] ─── MCP 断路器检查
  │     │
  │     ├─ ChatOpenAI ──────── request_timeout=30 ─── 流式不重试
  │     │
  │     └─ MCP 工具调用 ────── asyncio.timeout=10s ─── 重试 1 次 ─── 断路器
  │
  ├─ TTS WebSocket ────────── open/close/ping 超时 ─── 降级为纯文本流
  │
  ├─ ASR WebSocket ────────── open/close/ping 超时 ─── 返回空文本
  │
  ├─ Embedding ────────────── timeout=10 ─── 重试 3 次指数退避
  │
  └─ Vision/OCR ───────────── timeout=30/60 ─── 重试 3 次指数退避 ─── fallback
```
