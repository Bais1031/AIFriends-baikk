## 长期记忆结构化重构文档

### 升级背景

原有长期记忆基于 `Friend.memory` 单一 TextField，每 5 条消息由 LLM 全量重写一次，存在以下问题：

| 问题 | 详情 |
|---|---|
| 全量替换 | LLM 每次重写整块记忆，可能遗漏旧记忆中的重要细节；输出超 5000 字会被截断丢失 |
| 无结构 | 记忆是纯文本块，无法区分"用户偏好"、"重要事件"、"日常闲聊"等不同类型 |
| 全量注入 | `friend.memory` 作为 `{{ memory }}` 整体灌入 system prompt，随记忆增长挤占上下文预算（5000 字 ≈ 3000+ token） |
| 无语义筛选 | 所有记忆一视同仁地参与上下文，无法区分"当前相关"和"很久以前的无关细节" |
| 无去重机制 | LLM 重写时可能产生重复内容，且重复提及的信息不会被强化 |
| 无衰减机制 | 无论多久之前的记忆，只要没被覆盖就永远保持同等权重 |

### 改进前后对比

| 维度 | 改进前 | 改进后 |
|---|---|---|
| **存储模型** | `Friend.memory` 单一 TextField (5000字) | `MemoryItem` 独立模型，1:N 关联 Friend，每条记忆独立存储 |
| **记忆结构** | 纯文本块，无分类 | 结构化：content / category / importance / weight / access_count / embedding |
| **记忆分类** | 无 | preference(偏好) / event(事件) / fact(事实) / emotion(情感) / general(通用) |
| **更新方式** | 全量替换：LLM 输出 → 直接覆盖 `friend.memory` | 增量提取：LLM 从新对话提取记忆点 → 语义去重 → 合并或追加 |
| **LLM 调用成本** | 每次要处理全部旧记忆 + 最近对话 | 只处理新增对话片段，输出结构化 JSON |
| **去重机制** | 无，依赖 LLM 自行避免重复 | 语义相似度比对（余弦相似度 > 0.85 视为重复），重复提及自动提升权重 |
| **上下文注入** | `friend.memory` 全量文本灌入 `{{ memory }}` | 语义检索 top-K 条相关记忆注入，只取与当前话题相关的 |
| **Token 消耗** | 固定 3000+ token（5000字全文） | 可控，5 条记忆约 200~500 token |
| **可扩展性** | 记忆越多越挤占上下文预算 | 记忆数量不影响每次注入量，只影响检索范围 |
| **信息保留** | 旧记忆依赖 LLM 不遗漏，一次覆盖即丢失 | 旧记忆不会被覆盖，仅权重衰减 |
| **重复提及强化** | 无，重复信息可能被冲掉 | 重复提及自动提升 weight +0.1，importance 取最大值 |
| **时间衰减** | 无 | 指数衰减公式，半衰期 30 天，低权重记忆自动归档删除 |
| **向量检索** | 无 | 阿里云 text-embedding-v3 生成 1024 维向量，余弦相似度排序 |
| **兼容性** | — | `Friend.memory` 保留为缓存字段，拼接当前 MemoryItem 生成，向后兼容 |

### 升级后的架构

```
改进前: [SystemPrompt(含 friend.memory 全文)] + [摘要层] + [近期对话] + [当前消息]

改进后: [SystemPrompt(含语义检索记忆)] + [语义记忆层] + [摘要层] + [近期对话] + [当前消息]
```

### 改动文件清单

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `web/models/friend.py` | 修改 | 新增 `MemoryItem` 模型定义 |
| `web/migrations/0012_memoryitem.py` | 新增 | MemoryItem 数据库迁移文件 |
| `web/utils/embedding.py` | 新增 | 阿里云 text-embedding-v3 向量生成 + 余弦相似度计算 |
| `web/utils/memory_retrieval.py` | 新增 | 语义检索 top-K、去重查找、权重衰减、低权重归档 |
| `web/views/friend/message/memory/update.py` | 重写 | 全量替换 → 增量提取 JSON + 语义去重合并 + 衰减归档 |
| `web/utils/context_builder.py` | 修改 | 新增语义记忆层，system prompt 使用 `memory_override` |
| `web/utils/prompt_template.py` | 修改 | `create_system_prompt()` 支持 `memory_override` 参数 |

---

### 各模块详细说明

#### 1. MemoryItem 模型

```python
# web/models/friend.py
class MemoryItem(models.Model):
    friend = models.ForeignKey(Friend, on_delete=models.CASCADE, related_name='memories')
    content = models.TextField()                                # 记忆内容
    category = models.CharField(max_length=32, default='general', choices=CATEGORY_CHOICES)
    importance = models.FloatField(default=0.5)                 # 初始重要性 (0~1, 由LLM打分)
    weight = models.FloatField(default=0.5)                     # 当前权重 (0~1, 随时间衰减)
    access_count = models.IntegerField(default=0)               # 被检索/引用次数
    embedding = models.JSONField(default=None, null=True, blank=True)  # 1024维向量
    created_at = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(default=now)
```

**记忆分类**：

| category | 含义 | 示例 |
|---|---|---|
| preference | 用户偏好、喜好、习惯 | "用户喜欢猫，养了一只叫小橘的橘猫" |
| event | 重要事件、经历 | "用户今天升职了，非常开心" |
| fact | 客观事实、身份信息 | "用户是一名软件工程师" |
| emotion | 情感状态、心理特征 | "用户最近压力很大" |
| general | 其他重要信息 | "用户下周要去北京出差" |

**与 Friend 的关系**：

```
改进前: Friend.memory = "一整块文本" (1:1)

改进后: Friend → MemoryItem (1:N)
       friend.memories.all()                            # 获取所有记忆
       friend.memories.filter(category='preference')    # 按类别筛选
       friend.memories.order_by('-weight')[:10]         # 取权重最高的10条
```

---

#### 2. 向量嵌入工具

```python
# web/utils/embedding.py

def get_embedding(text: str) -> Optional[list[float]]:
    """调用阿里云 text-embedding-v3 生成 1024 维向量"""
    client = OpenAI(api_key=..., base_url=...)
    resp = client.embeddings.create(
        model="text-embedding-v3",
        input=text[:2048],      # 截断超长文本
        dimensions=1024,
    )
    return resp.data[0].embedding

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """纯 Python 余弦相似度计算，无外部依赖"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b)
```

- 使用阿里云 DashScope 的 `text-embedding-v3` 模型，与项目已有的 API_KEY / API_BASE 共用
- 输入截断 2048 字符，输出 1024 维浮点向量
- OpenAI 客户端懒加载单例，避免重复初始化
- 余弦相似度纯 Python 实现，无需 numpy 依赖

---

#### 3. 记忆检索与衰减

```python
# web/utils/memory_retrieval.py

DEFAULT_TOP_K = 5             # 每次检索返回的记忆条数
SIMILARITY_THRESHOLD = 0.85   # 去重判定阈值
DECAY_HALF_LIFE = 30          # 权重衰减半衰期（天）
ARCHIVE_WEIGHT_THRESHOLD = 0.05  # 低权重归档阈值
```

**语义检索** (`retrieve_relevant_memories`)：

```
输入: friend + 当前用户消息
  │
  ├── 1. 对当前消息生成 embedding
  ├── 2. 遍历 friend 所有有向量的记忆，计算余弦相似度
  ├── 3. 按相似度降序排序，取 top-K 条
  └── 4. 更新被检索记忆的 access_count 和 last_accessed
  │
  ▼
输出: 最相关的 5 条 MemoryItem
```

- embedding 不可用时回退到按权重排序取 top-K
- 被检索到的记忆自动更新 `access_count`（影响衰减公式中的引用系数）

**语义去重** (`find_similar_memory`)：

```
输入: friend + 新记忆内容
  │
  ├── 1. 对新记忆生成 embedding
  ├── 2. 遍历已有记忆，找最高余弦相似度
  └── 3. 相似度 ≥ 0.85 → 返回该条记忆（视为重复）
      相似度 < 0.85 → 返回 None（视为新记忆）
```

**权重衰减** (`decay_memory_weights`)：

```
公式: weight = importance × e^(-0.693 × 天数/30) × (1 + 0.05 × 引用次数)

特性:
- 重要性高的记忆衰减更慢（importance 作为乘数系数）
- 被频繁检索的记忆权重更高（access_count 作为加成）
- 半衰期 30 天：一个月不被提及，权重减半
- 权重限定在 [0, 1] 范围内
```

衰减示例（importance=0.8, access_count=0）：

| 天数 | 衰减系数 | 权重 |
|---|---|---|
| 0 天 | 1.000 | 0.80 |
| 7 天 | 0.850 | 0.68 |
| 30 天 | 0.500 | 0.40 |
| 60 天 | 0.250 | 0.20 |
| 90 天 | 0.125 | 0.10 |
| 120 天 | 0.063 | 0.05 (归档线) |

**低权重归档** (`archive_low_weight_memories`)：

- 权重低于 0.05 的记忆自动删除
- 在每次 `update_memory()` 调用时执行

---

#### 4. 增量记忆更新（核心重构）

**改进前的全量替换流程**：

```
旧记忆全文 + 最近10条对话 → LLM → 全新记忆文本 → friend.memory = 新文本
```

**改进后的增量提取+合并流程**：

```
最近10条对话 → LLM(提取prompt) → JSON记忆列表 → 语义去重 → 合并/追加 → 衰减归档
```

**Step 1 — 增量提取**：

LLM 使用专用的提取 prompt，输出结构化 JSON 而非自由文本：

```
[SystemMessage]
你是一个记忆提取助手。请从对话中提取值得长期记住的信息。
输出格式（严格JSON数组）：
[
  {"content": "记忆内容", "category": "preference|event|fact|emotion|general", "importance": 0.0-1.0}
]

[HumanMessage]
【最近对话】
user: ...
ai: ...

请提取值得长期记住的信息。
```

**Step 2 — 解析 LLM 输出** (`_parse_extraction_result`)：

- 优先直接 JSON 解析
- 失败则尝试从 markdown 代码块 ````json ... ``` `` 中提取
- 无有效提取结果返回空列表

**Step 3 — 去重合并** (`_merge_memories`)：

```
新记忆: "用户喜欢猫"
    │
    ├── find_similar_memory() 相似度 ≥ 0.85
    │   → 合并：weight + 0.1, importance 取最大值
    │
    └── find_similar_memory() 相似度 < 0.85
        → 追加：创建新 MemoryItem，生成 embedding，weight = importance
```

**Step 4 — 缓存刷新** (`_refresh_memory_cache`)：

- 将当前 MemoryItem 拼接为文本写入 `friend.memory`，保持向后兼容
- 拼接格式: `- [category] content`，取权重最高的前 20 条

**Step 5 — 衰减归档**：

- 执行 `decay_memory_weights()` 更新所有记忆权重
- 执行 `archive_low_weight_memories()` 删除权重 < 0.05 的记忆

**全量替换 vs 增量合并对比**：

| 维度 | 全量替换 | 增量提取+合并 |
|---|---|---|
| 信息保留 | 依赖 LLM 不遗漏 | 旧记忆不会被覆盖 |
| 写入方式 | `friend.memory = 新文本` | 逐条 `MemoryItem.create()` 或 `.save()` |
| 去重 | 无 | embedding 余弦相似度比对 |
| 重复提及强化 | 无，可能被冲掉 | 重复提及自动提升权重 |
| LLM 输出格式 | 自由文本 | 结构化 JSON |
| LLM 调用成本 | 每次要处理全部旧记忆 | 只处理新增对话片段 |

---

#### 5. ContextBuilder 重构

上下文结构变化：

```
改进前: [SystemPrompt(friend.memory全量)] + [摘要层] + [近期对话] + [当前消息]

改进后: [SystemPrompt(语义检索记忆)] + [语义记忆层] + [摘要层] + [近期对话] + [当前消息]
```

**`_build_system_prompt()` 变更**：

- 调用 `retrieve_relevant_memories()` 获取语义相关记忆
- 将检索结果拼接为文本，通过 `memory_override` 参数传入 `PromptTemplateManager`
- `PromptTemplateManager.create_system_prompt()` 新增 `memory_override` 参数：非空时替代 `friend.memory`

**新增 `_build_memory_context()`**：

- 独立的语义记忆层，以 `SystemMessage` 形式插入
- 格式: `【相关记忆】\n- [category] content`
- 与系统提示中的记忆内容互补，确保记忆信息充分注入

**`PromptTemplateManager` 变更**：

```python
# 改进前
def create_system_prompt(cls, friend, user_message, image_analysis):
    context = {'memory': friend.memory, ...}

# 改进后
def create_system_prompt(cls, friend, user_message, image_analysis, memory_override=""):
    memory_text = memory_override if memory_override else friend.memory
    context = {'memory': memory_text, ...}
```

---

### 配置参数

```python
# web/utils/memory_retrieval.py
DEFAULT_TOP_K = 5                 # 每次语义检索返回的记忆条数
SIMILARITY_THRESHOLD = 0.85       # 去重判定阈值（余弦相似度）
DECAY_HALF_LIFE = 30              # 权重衰减半衰期（天）
ARCHIVE_WEIGHT_THRESHOLD = 0.05   # 低权重归档阈值

# web/utils/context_builder.py
SUMMARY_THRESHOLD = 20            # 每多少条新消息触发一次摘要更新
MEMORY_TOP_K = 5                  # ContextBuilder 中语义检索条数

# web/views/friend/message/chat/chat.py
MEMORY_UPDATE_INTERVAL = 5        # 每多少条消息触发一次长期记忆更新

# web/utils/embedding.py
# text-embedding-v3, dimensions=1024  (硬编码在 get_embedding 中)
```

---

### 数据流全景（升级后）

```
用户发消息
    │
    ▼
ContextBuilder.build()
    ├── 1. SystemMessage: 角色设定 + 语义检索记忆 (PromptTemplateManager + memory_override)
    ├── 2. SystemMessage: 语义记忆层 (retrieve_relevant_memories top-K)
    ├── 3. SystemMessage: 对话摘要 (friend.conversation_summary)
    ├── 4. 近期对话 (受 token 预算约束，动态条数)
    └── 5. HumanMessage: 当前用户消息
    │
    ▼
ChatGraph (LLM + tools) → 流式返回 + TTS
    │
    ▼
保存 Message 到 DB
    │
    ├── Token 记录: 优先 usage_metadata，回退估算
    │
    ├── 每 5 条: update_memory(friend)
    │       │
    │       ├── 1. _build_extraction_input(): 最近10条对话 → 提取prompt
    │       ├── 2. MemoryGraph (LLM) → JSON 记忆列表
    │       ├── 3. _parse_extraction_result(): 解析 JSON
    │       ├── 4. _merge_memories(): 语义去重 + 合并/追加
    │       │       ├── find_similar_memory() ≥ 0.85 → 合并(权重+0.1)
    │       │       └── find_similar_memory() < 0.85 → 新增 MemoryItem + 生成 embedding
    │       ├── 5. _refresh_memory_cache(): 拼接 MemoryItem → friend.memory (兼容)
    │       ├── 6. decay_memory_weights(): 时间衰减更新权重
    │       └── 7. archive_low_weight_memories(): 删除权重 < 0.05 的记忆
    │
    └── 每 20 条: update_conversation_summary(friend) (不变)
```

---

### 迁移操作

```bash
cd backend
python manage.py migrate   # 应用 0012_memoryitem 迁移
```

`Friend.memory` 字段保留为缓存字段，已有数据不受影响。新增的 `MemoryItem` 表为空，将在后续对话中由增量提取逐步填充。
