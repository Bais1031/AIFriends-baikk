# 记忆系统优化：统一记忆源 + 批量更新 + Token 预算

## 背景

记忆系统存在三个问题：

### 问题一：双记忆源导致重复注入

系统同时维护两套记忆存储，导致同一条记忆可能被注入两次，浪费 token 且重复强调导致 LLM 过度偏重：

| 存储 | 类型 | 用途 |
|---|---|---|
| `MemoryItem` 模型 | 结构化 + pgvector embedding | 语义检索、去重、权重衰减 |
| `friend.memory` 文本字段 | 纯文本 | `_refresh_memory_cache()` 拼接 top 20 MemoryItem 写入 |

`context_builder.py` 的注入链路存在重复：

```
1. SystemPrompt 模板 → 注入 memory_override（来自检索结果，回退到 friend.memory）
2. 语义记忆层 → _build_memory_context() 再次注入相同记忆   ← 重复
3. 摘要层
4. 近期对话
5. 当前消息
```

### 问题二：N+1 查询

`memory_retrieval.py` 中两个函数逐条 `save()`，造成大量 DB 写入：

| 函数 | 问题 | 影响 |
|---|---|---|
| `decay_memory_weights()` | 逐条 `save()` 更新 weight | 500 条记忆 = 500 次 DB 写入 |
| `retrieve_relevant_memories()` | 逐条 `save()` 更新 access_count/last_accessed | 检索 5 条 = 5 次 DB 写入 |

### 问题三：记忆和摘要无 token 预算

系统提示词有 1500 token 预留，对话历史有预算约束，但记忆注入和对话摘要没有独立 token 上限。记忆或摘要过长会挤占实际对话空间，且上下文总预算 4096 偏小（DeepSeek v3.2 支持 128K，只用了 3%）。

## 改动

### 1. 删除 `_refresh_memory_cache()`

**文件**: `backend/web/views/friend/message/memory/update.py`

- 删除 `_refresh_memory_cache()` 函数定义
- 删除 `update_memory()` 中对它的调用
- 删除不再使用的 `from django.utils.timezone import now`

### 2. 删除重复的记忆层

**文件**: `backend/web/utils/context_builder.py`

- 删除 `_build_memory_context()` 方法
- 删除 `build()` 中对它的调用
- `MEMORY_TOP_K` 从 5 提高到 8（记忆只注入一次，可以多放几条）

改动后注入链路：

```
1. SystemPrompt 模板 → 注入检索到的记忆（唯一入口）
2. 摘要层
3. 近期对话
4. 当前消息
```

### 3. 去掉 `friend.memory` 回退

**文件**: `backend/web/utils/prompt_template.py`

- `create_system_prompt()`：删除 `memory_override if memory_override else friend.memory` 回退，改为 `memory_text = memory_override`
- `create_memory_update_prompt()`：从 `friend.memory` 改为 `friend.memories.all()[:20]` 拼接

> `friend.memory` 字段暂保留在 Friend 模型中（避免迁移风险），只删除所有读写逻辑。后续可做迁移清空或删除字段。

### 4. 记忆操作批量更新

**文件**: `backend/web/utils/memory_retrieval.py`

#### 4a. `decay_memory_weights()` — N 次 save → 1 次 bulk_update

```python
# 改动前
for m in friend.memories.all():
    ...
    m.save(update_fields=['weight'])  # 每条一次 UPDATE

# 改动后
memories = list(friend.memories.all())
for m in memories:
    ...
if memories:
    MemoryItem.objects.bulk_update(memories, ['weight'])  # 一次 UPDATE
```

#### 4b. `retrieve_relevant_memories()` — K 次 save → 1 次 bulk_update

```python
# 改动前
for m in result:
    m.access_count += 1
    m.save(update_fields=['access_count', 'last_accessed'])  # 每条一次 UPDATE

# 改动后
if result:
    for m in result:
        m.access_count += 1
        m.last_accessed = timezone_now()
    MemoryItem.objects.bulk_update(result, ['access_count', 'last_accessed'])  # 一次 UPDATE
```

#### 为什么不用原生 SQL

优化文档中给出了原生 SQL 方案，但项目当前用 SQLite 开发，`EXTRACT(EPOCH FROM ...)` 是 PG 专有语法，开发环境无法运行。`bulk_update` 跨数据库兼容，性能已足够（1 次 UPDATE vs N 次 UPDATE）。

### 5. 扩大上下文预算 + 各层 token 预算约束

**文件**: `backend/web/utils/token_cache.py`、`backend/web/utils/context_builder.py`

#### 5a. 扩大 CONTEXT_BUDGET

```python
# 改动前
CONTEXT_BUDGET = 4096   # 只用了 DeepSeek v3.2 的 3%，对话历史空间不足

# 改动后
CONTEXT_BUDGET = 8192   # 占 128K 的 6%，对话历史约 15-20 轮
```

#### 5b. 新增各层 token 预算常量

```python
MEMORY_BUDGET = 800    # 记忆层 token 上限
SUMMARY_BUDGET = 500   # 摘要层 token 上限
```

#### 5c. 新增 `_truncate_to_budget()` 裁剪方法

按行粒度裁剪——从最后一行开始丢弃，直到 token 数不超预算，保证每行记忆/摘要完整：

```python
@staticmethod
def _truncate_to_budget(text: str, budget: int) -> str:
    if not text:
        return text
    tokens = TokenCache.estimate_tokens(text)
    if tokens <= budget:
        return text

    lines = text.split('\n')
    while lines and TokenCache.estimate_tokens('\n'.join(lines)) > budget:
        lines.pop()

    result = '\n'.join(lines)
    print(f"[ContextBuilder] 文本超预算裁剪: {tokens} -> {TokenCache.estimate_tokens(result)} (预算: {budget})")
    return result
```

#### 5d. 记忆和摘要注入加裁剪

```python
# 记忆裁剪
memory_text = self._truncate_to_budget('\n'.join(memory_lines), MEMORY_BUDGET)

# 摘要裁剪
summary = self._truncate_to_budget(summary, SUMMARY_BUDGET)
```

改动后预算分配：

```
总上下文 8192 tokens
├── 系统提示词模板  1500  (SYSTEM_PROMPT_RESERVE)
├── 记忆文本        800  (MEMORY_BUDGET，超限裁剪)
├── 对话摘要        500  (SUMMARY_BUDGET，超限裁剪)
└── 近期对话       6192  (get_message_budget = 8192 - 1500 - 500)
```

## 验证

1. 发送聊天消息，确认系统提示词中记忆正常注入（只出现一次）
2. 触发记忆更新（5 条消息后），确认不再写 `friend.memory`，MemoryItem 正常创建
3. 触发对话摘要更新，确认 `create_memory_update_prompt()` 能正确读取记忆
4. 检查数据库 friend 表，确认 `memory` 字段不再被更新
5. 触发记忆衰减，确认权重正常衰减，DB 只执行 1 次 UPDATE
6. 聊天触发记忆检索，确认 access_count 正常递增，DB 只执行 1 次 UPDATE
7. 检查无回归：低权重归档、语义检索等功能正常
8. 记忆超长时确认裁剪日志输出，摘要超长时确认裁剪正常
9. 对话历史预算从 2096 增至 6192，确认可容纳更多轮对话
