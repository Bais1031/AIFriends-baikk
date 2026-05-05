# 统一记忆源：去掉 friend.memory 文本缓存

## 背景

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

## 验证

1. 发送聊天消息，确认系统提示词中记忆正常注入（只出现一次）
2. 触发记忆更新（5 条消息后），确认不再写 `friend.memory`，MemoryItem 正常创建
3. 触发对话摘要更新，确认 `create_memory_update_prompt()` 能正确读取记忆
4. 检查数据库 friend 表，确认 `memory` 字段不再被更新
