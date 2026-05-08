# MemoryGraph 增强：从伪 Agent 到 ReAct Agent

## 背景

`MemoryGraph` 只有一个节点、无条件路由，本质上等于 `llm.invoke(messages)`。用 LangGraph 包一层没有发挥 StateGraph 的价值（条件分支、工具循环、状态管理），反而增加了编译开销。

更关键的问题：LLM 提取记忆时**不知道已有记忆**，去重完全靠后处理 `find_similar_memory()` 语义匹配。这导致：
1. LLM 可能提取明显重复的记忆（如已有"用户喜欢猫"，又提取"用户喜欢猫"）
2. 无法检测矛盾（用户改了偏好），merge 逻辑只会 boost 旧记忆的权重——旧记忆反而是错的

## 改动

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
- 在 `create_app(friend)` 闭包内定义，捕获 `friend` 参数

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

`_parse_extraction_result()` 在过滤后加 `item.setdefault('action', 'add')`，确保向后兼容。

### 4. 合并逻辑增加 update 分支

**文件**: `backend/web/views/friend/message/memory/update.py`

`_merge_memories()` 新增 `action == "update"` 分支：

```
1. 优先用 old_content 调 find_similar_memory() 查找旧记忆
2. 找到 → 更新 content/category/importance/weight/embedding（重新生成 embedding）
3. 找不到 → 回退用新 content 查找
4. 都找不到 → 当新增处理（安全回退）
```

原有的 add 逻辑不变。

### 5. 摘要更新改用直接调用

**文件**: `backend/web/utils/context_builder.py`

`update_conversation_summary()` 原来用 `MemoryGraph.create_app()` 做单次摘要，不需要工具。改为直接 `llm.invoke()`：
- 删除 `MemoryGraph` import
- 用 `ChatOpenAI(...)` 直接调用
- `app.invoke(inputs) → res['messages'][-1].content` 改为 `llm.invoke(messages) → res.content`

理由：摘要是单次 LLM 调用，用 StateGraph 增加编译开销无意义。同时避免 `create_app()` 新增 `friend` 参数后需传参的问题。

## 架构对比

### 改动前

```
update_memory()
  → MemoryGraph.create_app()        # 伪 Agent，无工具
      → agent node: llm.invoke(messages)  # 盲提取，不知道已有记忆
      → END
  → _merge_memories()               # 后处理去重：只能 boost 权重，无法处理矛盾
```

### 改动后

```
update_memory()
  → MemoryGraph.create_app(friend)  # ReAct Agent，有工具
      → agent node: llm.invoke(messages)  # 先调 query_memories 查已有记忆
      → should_continue: 有 tool_calls?
          → tools node: 执行 query_memories    # 返回已有记忆
          → agent node: 基于已有记忆做提取     # 避免重复 + 检测矛盾
          → should_continue: 无 tool_calls → END
  → _merge_memories()               # 处理 add/update 两种 action
```

## 验证

1. `update_memory()` 端到端：确认 LLM 先调用 `query_memories`，再输出 JSON 提取结果
2. add 场景：新记忆正常创建，已有相似记忆 boost 权重
3. update 场景：已有记忆内容被替换，embedding 重新生成
4. 摘要更新：`update_conversation_summary()` 正常工作，不依赖 MemoryGraph
5. 无记忆场景：`query_memories` 返回"未找到相关记忆"，LLM 正常提取
6. 向后兼容：LLM 不输出 action 字段时默认为 add
