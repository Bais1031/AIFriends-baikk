# MemoryGraph 增强：ReAct Agent

## 背景

`MemoryGraph` 只有一个节点、无条件路由，本质上等于 `llm.invoke(messages)`。用 LangGraph 包一层没有发挥 StateGraph 的价值（条件分支、工具循环、状态管理），反而增加了编译开销。

更关键的问题：LLM 提取记忆时**不知道已有记忆**，去重完全靠后处理 `find_similar_memory()` 语义匹配。这导致：
1. LLM 可能提取明显重复的记忆（如已有"用户喜欢猫"，又提取"用户喜欢猫"）
2. 无法检测矛盾（用户改了偏好），merge 逻辑只会 boost 旧记忆的权重——旧记忆反而是错的

## 当前 Agent 工作流全景

系统包含两条 ReAct Agent 工作流 + 一条直接 LLM 调用，由聊天视图按条件触发：

### 触发时序

```
用户发送消息
  │
  ▼
ChatGraph.create_app()          ← 每次聊天都触发（流式响应）
  │
  ▼
保存 Message 到 DB
  ├── 每 5 条  → update_memory()        ← MemoryGraph Agent
  └── 每 20 条 → update_conversation_summary()  ← 直接 llm.invoke()
```

### 工作流 1：聊天 Agent（ChatGraph）

**触发时机**：每次用户发消息

**职责**：基于角色设定、记忆、对话历史生成回复，可调用工具获取外部信息

```
用户消息
  │
  ▼
ContextBuilder.build()                    ← 组装完整上下文
  │
  ├── 1. retrieve_relevant_memories(top_k=8)   ← pgvector 语义检索，返回最相关的 8 条记忆
  │      └── 更新 access_count + last_accessed（bulk_update）
  │
  ├── 2. SystemPrompt                         ← 注入角色设定 + 记忆文本
  │      └── 记忆文本经 MEMORY_BUDGET=800 裁剪（按行丢弃，保证每行完整）
  │
  ├── 3. 对话摘要                             ← friend.conversation_summary
  │      └── 经 SUMMARY_BUDGET=500 裁剪
  │
  ├── 4. 近期对话                             ← token 预算 6192，从最新往前取
  │      └── 预算 = 8192(CONTEXT_BUDGET) - 1500(SYSTEM_PROMPT_RESERVE) - 500(SUMMARY_RESERVE)
  │
  └── 5. 当前消息
  │
  ▼
ChatGraph.create_app()                    ← ReAct Agent
  │
  ├── 绑定工具:
  │   ├── get_time()                     ← 返回当前时间 [YYYY-MM-DD HH:MM:SS]
  │   ├── search_knowledge_base(query)   ← LanceDB 混合检索，返回 top-3 文档片段
  │   └── MCP: web_search(query)         ← Tavily API 网络搜索（MCP Server 动态发现）
  │
  │  ┌─────────────────────────────────────────────┐
  │  │  START → agent ──→ should_continue           │
  │  │                    ├── 有 tool_calls          │
  │  │                    │   → tools → agent（循环） │
  │  │                    └── 无 tool_calls          │
  │  │                        → END                  │
  │  └─────────────────────────────────────────────┘
  │
  ▼
SSE 流式输出 + TTS 语音合成（WebSocket 双工）
```

### 工作流 2：记忆提取 Agent（MemoryGraph）

**触发时机**：每 5 条消息后（`msg_count % 5 == 0`）

**职责**：从对话中提取值得长期记住的信息，去重合并或更新已有记忆

```
update_memory(friend)
  │
  ├── 取最近 10 条对话，拼接为文本
  │
  ▼
MemoryGraph.create_app(friend)            ← ReAct Agent（本次改动重点）
  │
  ├── 绑定工具:
  │   └── query_memories(query)          ← 调 retrieve_relevant_memories(top_k=5)
  │       ├── 有记忆 → 返回: "- [category] content (重要性:x.x, 权重:x.xx)"
  │       └── 无记忆 → 返回: "未找到相关记忆"
  │
  │  ┌──────────────────────────────────────────────────────┐
  │  │  START → agent ──→ should_continue                    │
  │  │                    ├── 有 tool_calls                   │
  │  │                    │   → tools: 执行 query_memories   │
  │  │                    │   → agent: 基于已有记忆做提取    │
  │  │                    │     （避免重复 + 检测矛盾）       │
  │  │                    └── 无 tool_calls                   │
  │  │                        → END: 输出 JSON 提取结果      │
  │  └──────────────────────────────────────────────────────┘
  │
  │  LLM 最终输出格式:
  │  [
  │    {"content": "...", "category": "preference|event|fact|emotion|general",
  │     "importance": 0.0-1.0, "action": "add|update", "old_content": "..."}
  │  ]
  │
  ▼
_merge_memories()                         ← 分支处理
  │
  ├── action="add"（新增/重复）
  │   ├── find_similar_memory() 找到相似 → boost 权重 +0.1, 取 max(importance)
  │   └── 未找到 → 创建 MemoryItem（生成 embedding）
  │
  └── action="update"（矛盾更新）
      ├── 优先用 old_content 找相似记忆 → 替换 content + 重新生成 embedding
      ├── 回退用新 content 找 → 同上
      └── 都找不到 → 当新增处理（安全回退）
  │
  ▼
decay_memory_weights()                    ← bulk_update 批量权重衰减
  │   公式: weight = importance × e^(-0.693 × 天数/30) × (1 + 0.05 × access_count)
  │
  ▼
archive_low_weight_memories()             ← 删除 weight < 0.05 的记忆
```

**ReAct 循环示例**：用户之前说过喜欢吃辣，现在说不吃辣了

```
[agent] 收到提取请求 → 决定先查已有记忆
  ↓ tool_calls: query_memories("用户饮食偏好")
[tools] 返回: "- [preference] 用户喜欢吃辣 (重要性:0.8, 权重:0.75)"
[agent] 发现矛盾：用户改了偏好 → 输出 JSON
  ↓ [{"content": "用户不吃辣", "action": "update", "old_content": "用户喜欢吃辣", ...}]
[END]  → _merge_memories() 找到旧记忆 → 替换内容 + 重新生成 embedding
```

### 工作流 3：摘要更新（直接 LLM 调用）

**触发时机**：每 20 条消息后（`should_update_summary() == True`）

**职责**：将已摘要范围外的对话压缩为摘要，保留关键信息

```
update_conversation_summary(friend)
  │
  ├── 取上次摘要之后到最近 5 条之前的对话
  │
  ▼
llm.invoke(messages)                     ← 直接调用，不走 Agent
  │                                      （摘要不需要工具，单次 LLM 调用即可）
  ├── SystemMessage: "你是一个对话摘要助手..."
  └── HumanMessage: "【已有摘要】...\n【新增对话】...\n请合并生成更新后的完整摘要"
  │
  ▼
friend.conversation_summary = 摘要内容
friend.summary_message_count = summary_end
```

## 改动详述

### 1. MemoryGraph 重写为 ReAct Agent

**文件**: `backend/web/views/friend/message/memory/graph.py`

改动前：单节点 StateGraph（START → agent → END），等于 `llm.invoke(messages)`

改动后：与 ChatGraph 相同的 ReAct 模式——agent + tools + 条件路由循环：

```
START → agent → should_continue → tools (有 tool_calls)
                             → END   (无 tool_calls)
tools → agent (循环回来)
```

新增 `query_memories` 工具：
- 输入：`query: str`（搜索查询）
- 内部调用 `retrieve_relevant_memories(friend, query, top_k=5)`
- 输出：已有记忆列表，含 category、importance、weight
- 在 `create_app(friend)` 闭包内定义，捕获 `friend` 参数（friend 不暴露给 LLM）

`create_app()` 签名变更：`create_app()` → `create_app(friend: Friend)`

### 2. 提取 prompt 增强

**文件**: `backend/web/views/friend/message/memory/update.py`

核心改动：
- 明确要求 LLM 提取前**先用 `query_memories` 工具搜索已有记忆**
- 输出格式增加 `action` 字段：`"add"`（默认，新增）和 `"update"`（矛盾更新）
- update action 必须提供 `old_content` 字段，用于匹配旧记忆

```json
// 新增
{"content": "用户不吃辣", "category": "preference", "importance": 0.8, "action": "update", "old_content": "用户喜欢吃辣"}
```

### 3. 解析器兼容 action 字段

**文件**: `backend/web/views/friend/message/memory/update.py`

`_parse_extraction_result()` 在过滤后加 `item.setdefault('action', 'add')`，确保向后兼容（LLM 不输出 action 字段时默认为 add）。

### 4. 合并逻辑增加 update 分支

**文件**: `backend/web/views/friend/message/memory/update.py`

`_merge_memories()` 新增 `action == "update"` 分支：

```
1. 优先用 old_content 调 find_similar_memory() 查找旧记忆（LLM 引用了 query_memories 看到的原文）
2. 找到 → 更新 content/category/importance/weight/embedding（重新生成 embedding，保证后续语义检索正确）
3. 找不到 → 回退用新 content 查找
4. 都找不到 → 当新增处理（安全回退，不丢失信息）
```

原有的 add 逻辑不变：重复记忆 boost 权重，新记忆创建 MemoryItem。

### 5. 摘要更新改用直接调用

**文件**: `backend/web/utils/context_builder.py`

`update_conversation_summary()` 原来用 `MemoryGraph.create_app()` 做单次摘要，不需要工具。改为直接 `llm.invoke()`：
- 删除 `MemoryGraph` import
- 用 `ChatOpenAI(...)` 直接调用
- `app.invoke(inputs) → res['messages'][-1].content` 改为 `llm.invoke(messages) → res.content`

理由：摘要是单次 LLM 调用，用 StateGraph 增加编译开销无意义。同时避免 `create_app()` 新增 `friend` 参数后需传参的问题。

## 改动前后对比

| 组件 | 改动前 | 改动后 |
|---|---|---|
| MemoryGraph | 伪 Agent（单节点 = `llm.invoke()`） | ReAct Agent（query_memories 工具 + 循环） |
| 记忆提取 | LLM 盲提取，后处理去重 | LLM 先查已有记忆，支持 add/update |
| 摘要更新 | 走 MemoryGraph（伪 Agent 开销） | 直接 `llm.invoke()`（无工具，无编译开销） |
| 矛盾处理 | 无（只会 boost 旧记忆权重） | LLM 标记 update，替换内容+重新生成 embedding |
| Agent 数量 | 1 个真 Agent + 1 个伪 Agent | 2 个真 ReAct Agent + 1 个直接调用 |

## 设计考量

### 为什么 query_memories 用闭包而不是全局函数

`query_memories` 需要访问 `friend` 对象来查询该好友的记忆，但 `friend` 不应该暴露为工具参数（LLM 不需要知道 friend 的存在）。将工具定义在 `create_app(friend)` 闭包内，`friend` 作为闭包变量被捕获，LLM 只看到 `query: str` 这一个参数。

### 为什么 update 要重新生成 embedding

如果用户从"喜欢吃辣"变成"不吃辣"，旧 embedding 对应的是"喜欢吃辣"的语义。如果不更新 embedding，后续语义检索"辣的食物"仍然会匹配到这条记忆，但内容已经变了。重新生成 embedding 保证检索结果与实际内容一致。

### 为什么后处理去重仍然是必要的

LLM 不保证一定调用 `query_memories` 工具（可能跳过直接提取）。`find_similar_memory()` 在 add 分支作为安全网，确保即使 LLM 没用工具也不会产生完全重复的记忆。

### 为什么摘要不走 Agent

对话摘要是一个确定性的单次任务——输入对话文本，输出摘要文本。不需要查询外部信息，不需要条件分支。用 StateGraph 包一层只会增加编译开销（构建图、编译节点/边），没有收益。

## 验证

1. `update_memory()` 端到端：确认 LLM 先调用 `query_memories`，再输出 JSON 提取结果
2. add 场景：新记忆正常创建，已有相似记忆 boost 权重
3. update 场景：已有记忆内容被替换，embedding 重新生成
4. 摘要更新：`update_conversation_summary()` 正常工作，不依赖 MemoryGraph
5. 无记忆场景：`query_memories` 返回"未找到相关记忆"，LLM 正常提取
6. 向后兼容：LLM 不输出 action 字段时默认为 add
