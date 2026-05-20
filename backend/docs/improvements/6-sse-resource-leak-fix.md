# 6 SSE 资源泄漏修复

## 问题

用户关闭页面后，Django 的 `StreamingHttpResponse` 生成器被停止迭代，但工作线程没有任何感知，继续跑完整个 LLM+TTS 流程，白白消耗 API 额度。并发用户多了会成倍放大浪费。

具体风险点：

1. **线程无法停止**：没有取消信号，`tts_sender` 的 `async for` 循环会一直跑完 LLM 全部输出
2. **队列无界**：`Queue()` 无上限，大量 chunk 积压可能 OOM
3. **入队无保护**：`put_nowait()` 在队列满时直接抛异常，未处理
4. **出队死等**：`mq.get()` 无超时，生成器异常退出后线程永远阻塞
5. **线程非守护**：进程退出时必须等非守护线程结束，可能卡住

## 方案：协作式取消 + 有界队列

```
用户关闭页面
  │
  ▼
Django 停止迭代生成器
  │
  ▼
生成器 finally 块执行 cancel.set()
  │
  ▼
工作线程下一轮循环检测到 cancel.is_set()
  │
  ▼
break 退出循环 → WebSocket 关闭 → 线程结束
```

核心思路：用 `threading.Event` 做协作式取消。生成器是"入口"，工作线程是"出口"，Event 是连接两者的信号。用户断开时生成器 set，工作线程每轮循环 check，最多再跑几个 chunk 就退出。

## 实现

### 1. 创建 cancel 事件 + 有界队列 + daemon 线程

```python
def event_stream(self, ...):
    cancel = threading.Event()
    mq = Queue(maxsize=100)
    thread = threading.Thread(
        target=self.work,
        args=(app, inputs, mq, speaker, cancel),
        daemon=True,
    )
    thread.start()
```

### 2. 生成器 finally 触发取消

```python
def event_stream(self, ...):
    try:
        while True:
            try:
                msg = mq.get(timeout=30)   # 带超时，防止死等
            except Exception:
                break
            if not msg:
                break
            ...
    except Exception:                      # 用户关页面 → GeneratorExit
        pass
    finally:
        cancel.set()                       # 通知工作线程停止
```

### 3. 工作线程每轮检查 cancel

`tts_sender`、`tts_receiver`、`_text_only_stream` 每轮循环检查：

```python
async def tts_sender(self, app, inputs, mq, ws, task_id, cancel):
    async for msg, metadata in app.astream(inputs, stream_mode="messages"):
        if cancel.is_set():
            print("[TTS] 用户已断开，提前终止流式输出")
            break
        ...
```

### 4. 队列操作带超时

```python
# 入队：带超时，满则 break
try:
    mq.put({'content': msg.content}, timeout=5)
except Full:
    break

# 出队：带超时，防止死等
try:
    msg = mq.get(timeout=30)
except Exception:
    break
```

### 5. TTS 降级也检查 cancel

```python
async def run_tts_tasks(self, app, inputs, mq, speaker, cancel):
    if cancel.is_set():
        return                             # 用户已走，不启动任何流程
    try:
        ...
    except Exception as e:
        if cancel.is_set():
            return                         # 用户已走，不再降级
        await self._text_only_stream(app, inputs, mq, cancel)
```

## 改动范围

| 文件 | 改动 |
|------|------|
| `chat.py` | `event_stream` / `work` / `tts_sender` / `tts_receiver` / `run_tts_tasks` / `_text_only_stream` 全部加入 cancel 参数 |
| `multimodal.py` | 同上，对称改动 |

## 效果对比

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| 用户关闭页面 | 线程跑完整个 LLM+TTS 流程 | 最多再消耗几个 chunk 后提前退出 |
| 队列积压 | 无界 Queue 可能 OOM | maxsize=100 + put timeout 保护 |
| 出队阻塞 | `mq.get()` 死等 | `mq.get(timeout=30)` 带超时 |
| 进程退出 | 非守护线程阻塞退出 | daemon 线程自动终止 |
| TTS 降级 | 用户断开后仍降级跑完 | cancel 时直接 return |
