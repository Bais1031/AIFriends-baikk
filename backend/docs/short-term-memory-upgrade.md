## 短期记忆升级文档

### 升级背景

原有短期记忆机制存在以下问题：

| 问题 | 详情 |
|---|---|
| 固定 10 条消息窗口 | 无 token 上限检查，长消息可能超出模型上下文窗口 |
| 无对话摘要 | 超过 10 条后早期上下文完全丢失 |
| 多模态视图消息顺序错误 | 历史消息插在当前消息之后 |
| `% 1` bug | 文本聊天每条消息都触发长期记忆更新，`count % 1 == 0` 永远为 True |
| Token 估算粗略 | `len(text) // 2` 不区分中英文，model 参数硬编码为 qwen2.5:3b |
| 未使用 LLM 实际用量 | 已开启 `include_usage` 但未使用返回的 token 数据 |

### 升级后的架构

```
改进前: [SystemPrompt] + [最近10条固定] + [当前消息]

改进后: [SystemPrompt] + [对话摘要层] + [近期对话(token预算约束)] + [当前消息]
```

### 改动文件清单

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `web/models/friend.py` | 修改 | Friend 模型新增 `conversation_summary`、`summary_message_count` 字段 |
| `web/migrations/0011_add_conversation_summary.py` | 新增 | 数据库迁移文件 |
| `web/utils/token_cache.py` | 重写 | 中英文混合 token 估算 + token 预算常量 |
| `web/utils/context_builder.py` | 新增 | 上下文构建器，整合 token 预算、动态窗口、自动摘要 |
| `web/views/friend/message/chat/chat.py` | 重构 | 使用 ContextBuilder，修复 bug，使用实际 token 用量 |
| `web/views/friend/message/chat/multimodal.py` | 重构 | 使用 ContextBuilder，修复消息顺序，使用实际 token 用量 |
| `web/utils/prompt_template.py` | 修复 | 补充 `SystemPrompt` 导入 |

---

### 各模块详细说明

#### 1. Friend 模型新增字段

```python
# web/models/friend.py
class Friend(models.Model):
    # ... 原有字段 ...
    memory = models.TextField(default="", max_length=5000, blank=True, null=True)
    conversation_summary = models.TextField(default="", blank=True)     # 新增：对话摘要
    summary_message_count = models.IntegerField(default=0)              # 新增：已摘要的消息数量
```

- `conversation_summary`：存储 LLM 生成的早期对话摘要文本
- `summary_message_count`：记录摘要覆盖到第几条消息，避免重复摘要

**迁移操作**：
```bash
cd backend
python manage.py makemigrations --merge --noinput   # 如果有迁移冲突
python manage.py migrate
```

---

#### 2. Token 估算改进

```python
# web/utils/token_cache.py

class TokenCache:
    # token 预算常量
    CONTEXT_BUDGET = 4096        # 上下文总预算
    SYSTEM_PROMPT_RESERVE = 1500 # 系统提示保留
    SUMMARY_RESERVE = 500        # 摘要层保留
    # 消息可用预算 = 4096 - 1500 - 500 = 2096
```

**估算算法改进**：

| 文本类型 | 旧算法 | 新算法 |
|---|---|---|
| 中文 | `len(text) // 2`（1token≈2字） | `中文字数 / 1.5`（1token≈1.5字） |
| 英文 | 同上（偏高） | `英文词数 × 1.3`（按词计算） |
| 标点/数字 | 同上 | `字符数 / 2` |

新增方法：
- `get_message_budget()`：返回对话历史可用的 token 预算

---

#### 3. 上下文构建器（核心新增）

```python
# web/utils/context_builder.py

class ContextBuilder:
    """构建发送给 LLM 的完整上下文"""

    def __init__(self, friend, current_message, image_analysis=""):
        ...

    def build(self) -> list:
        """
        构建消息列表，顺序：
        1. SystemMessage（角色设定 + 长期记忆）
        2. SystemMessage（对话摘要，如有）
        3. HumanMessage/AIMessage 对（近期对话，受 token 预算约束）
        4. HumanMessage（当前用户消息）
        """
```

**动态消息窗口**：
- 从最新消息往前取，累计 token 数不超过预算
- 超过预算时截断，保证最重要的近期上下文不丢失

**自动摘要触发**：

```python
SUMMARY_THRESHOLD = 20  # 每 20 条新消息触发一次摘要

def should_update_summary(friend) -> bool:
    """判断是否需要更新对话摘要"""
    total = Message.objects.filter(friend=friend).count()
    new_since_summary = total - friend.summary_message_count
    return new_since_summary >= SUMMARY_THRESHOLD

def update_conversation_summary(friend):
    """
    更新对话摘要：
    1. 取上次摘要之后到最近5条之前的消息
    2. 调用 LLM（MemoryGraph）生成摘要
    3. 与已有摘要合并
    4. 更新 friend.conversation_summary 和 friend.summary_message_count
    """
```

摘要请求的 LLM prompt 结构：
```
[SystemMessage] 你是一个对话摘要助手...

[HumanMessage]
【已有摘要】
{friend.conversation_summary}

【新增对话】
user: ...
ai: ...

请将已有摘要和新增对话合并，生成一份更新后的完整摘要。
```

---

#### 4. 聊天视图重构

**文本聊天**（`web/views/friend/message/chat/chat.py`）：

| 改动项 | 改前 | 改后 |
|---|---|---|
| 上下文组装 | `add_system_prompt()` + `add_recent_messages()` | `ContextBuilder.build()` |
| 消息窗口 | 固定 10 条 | Token 预算约束，动态条数 |
| 记忆更新频率 | `count % 1 == 0`（每条） | `count % 5 == 0`（每5条） |
| Token 记录 | `TokenCache.estimate_tokens()` 粗估 | 优先使用 `usage_metadata`，回退到估算 |
| 对话摘要 | 无 | `should_update_summary()` 检查触发 |

**多模态聊天**（`web/views/friend/message/chat/multimodal.py`）：

| 改动项 | 改前 | 改后 |
|---|---|---|
| 上下文组装 | 硬编码拼接 | `ContextBuilder.build()` |
| 消息顺序 | 历史消息插在当前消息之后（bug） | 正确顺序：系统提示 → 摘要 → 历史 → 当前消息 |
| 图片描述位置 | 与历史消息混在一起 | 插入系统提示之后（位置 1） |
| Token 记录 | 粗估 | 优先使用实际用量 |
| 对话摘要 | 无 | 同文本聊天 |

---

### 配置参数

可在 `token_cache.py` 和 `context_builder.py` 中调整：

```python
# web/utils/token_cache.py
CONTEXT_BUDGET = 4096          # 上下文总 token 预算，根据模型上下文窗口调整
SYSTEM_PROMPT_RESERVE = 1500   # 系统提示保留 token 数
SUMMARY_RESERVE = 500          # 摘要层保留 token 数

# web/utils/context_builder.py
SUMMARY_THRESHOLD = 20         # 每多少条新消息触发一次摘要更新

# web/views/friend/message/chat/chat.py
MEMORY_UPDATE_INTERVAL = 5     # 每多少条消息触发一次长期记忆更新
```

---

### 数据流全景（升级后）

```
用户发消息
    │
    ▼
ContextBuilder.build()
    ├── 1. SystemMessage: 角色设定 + 长期记忆 (PromptTemplateManager)
    ├── 2. SystemMessage: 对话摘要 (friend.conversation_summary)
    ├── 3. 近期对话 (受 token 预算约束，动态条数)
    └── 4. HumanMessage: 当前用户消息
    │
    ▼
ChatGraph (LLM + tools) → 流式返回 + TTS
    │
    ▼
保存 Message 到 DB
    ├── Token 记录: 优先 usage_metadata，回退估算
    ├── 长期记忆: 每 5 条触发 update_memory()
    └── 对话摘要: 每 20 条触发 update_conversation_summary()
```
