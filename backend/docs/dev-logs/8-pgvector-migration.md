## PostgreSQL + pgvector 迁移实施记录

### 改进背景

原记忆系统的向量检索采用 **SQLite + JSONField + Python 内存余弦相似度**：

```python
# 改进前 memory_retrieval.py
from web.utils.embedding import get_embedding, cosine_similarity

def retrieve_relevant_memories(friend, query, top_k=5):
    query_embedding = get_embedding(query)
    memories = friend.memories.exclude(embedding__isnull=True)
    scored = []
    for m in memories:                                    # 逐条遍历
        if m.embedding:
            sim = cosine_similarity(query_embedding, m.embedding)  # Python 计算余弦
            scored.append((m, sim))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [m for m, _ in scored[:top_k]]
```

每次检索都要将所有 MemoryItem 的 embedding 加载到 Python 内存，逐条计算余弦相似度，复杂度 **O(N)**。

迁移到 PostgreSQL + pgvector 后，利用 HNSW 向量索引实现近似最近邻搜索，复杂度降至 **O(log N)**。

---

### 改进前后对比

#### 架构层面

| 维度 | 改进前 | 改进后 |
|---|---|---|
| 数据库 | SQLite（单文件，单写锁） | PostgreSQL（多连接并发） |
| embedding 存储 | `JSONField`（JSON 文本存 1024 维浮点数组） | `VectorField`（原生 `vector(1024)` 类型） |
| 相似度计算位置 | Python 应用层 | PostgreSQL 数据库侧 |
| 检索方式 | 全表扫描 + Python 逐条计算 | HNSW 索引近似最近邻 |
| 检索复杂度 | O(N) | O(log N) |
| 向量索引 | 无 | HNSW (m=16, ef_construction=64) |
| Admin 管理 | MemoryItem 未注册 | 已注册，排除 embedding 字段 |

#### 代码层面

**模型定义**：

```python
# 改进前
embedding = models.JSONField(default=None, null=True, blank=True)

# 改进后
from pgvector.django import VectorField, HnswIndex

embedding = VectorField(dimensions=1024, null=True, blank=True)

class Meta:
    ordering = ['-weight']
    indexes = [
        HnswIndex(
            name='web_memoryitem_embedding_hnsw',
            fields=['embedding'],
            opclasses=['vector_cosine_ops'],
            m=16,
            ef_construction=64,
        ),
    ]
```

**检索逻辑**：

```python
# 改进前：Python 循环 + 余弦相似度
scored = []
for m in memories:
    if m.embedding:
        sim = cosine_similarity(query_embedding, m.embedding)
        scored.append((m, sim))
scored.sort(key=lambda x: x[1], reverse=True)
result = [m for m, _ in scored[:top_k]]

# 改进后：pgvector CosineDistance ORM 查询
result = list(
    memories.annotate(distance=CosineDistance('embedding', query_embedding))
    .order_by('distance')[:top_k]
)
```

**去重逻辑**：

```python
# 改进前：遍历全部记忆找最高分
best_match = None
best_score = 0.0
for m in memories:
    if m.embedding:
        sim = cosine_similarity(embedding, m.embedding)
        if sim > best_score:
            best_score = sim
            best_match = m
if best_score >= threshold:
    return best_match

# 改进后：数据库侧 ORDER BY 利用索引取最近邻
distance_threshold = 1.0 - threshold  # similarity >= 0.85 → distance <= 0.15
best = friend.memories.exclude(embedding__isnull=True).annotate(
    distance=CosineDistance('embedding', embedding)
).order_by('distance').first()
if best and best.distance <= distance_threshold:
    return best
```

**工具函数**：

```python
# 改进前 embedding.py：保留 get_embedding + cosine_similarity
def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

# 改进后 embedding.py：仅保留 get_embedding
# cosine_similarity 已删除，由 pgvector CosineDistance 替代
```

---

### 改动文件清单

| 文件 | 改动 |
|---|---|
| `requirements.txt` | 添加 `psycopg2-binary`、`pgvector`、`django-redis`、`django-cors-headers` |
| `backend/settings.py` | DATABASES 从 SQLite 改为 PostgreSQL；INSTALLED_APPS 添加 `django.contrib.postgres` 和 `pgvector` |
| `.env` | 添加 PG_DATABASE / PG_USER / PG_PASSWORD / PG_HOST / PG_PORT |
| `web/models/friend.py` | `embedding` 从 JSONField 改为 `VectorField(1024)`；Meta 添加 HNSW 索引 |
| `web/utils/embedding.py` | 删除 `cosine_similarity` 函数 |
| `web/utils/memory_retrieval.py` | Python 循环替换为 pgvector `CosineDistance` ORM 查询 |
| `web/admin.py` | 注册 MemoryItem（排除 embedding 字段） |
| `web/migrations/0013_*.py` | 自定义 SQL：`jsonb → text → vector(1024)` 类型转换 + HnswIndex |

无需改动：`context_builder.py`、`update.py`、任何视图文件。

---

### 实施步骤与踩坑记录

#### Step 1: 启动 PostgreSQL + pgvector 容器

```bash
docker run -d --name aifriends-postgres -p 5432:5432 \
  -e POSTGRES_DB=aifriends -e POSTGRES_USER=aifriends \
  -e POSTGRES_PASSWORD=aifriends_dev \
  -v aifriends-pgdata:/var/lib/postgresql/data \
  pgvector/pgvector:pg17

docker exec aifriends-postgres psql -U aifriends -d aifriends \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

#### Step 2: 导出 SQLite 数据（必须在切换数据库之前）

```bash
python manage.py dumpdata --natural-foreign --output=full_data.json
```

> **踩坑**：Django 6.0 已移除 `--natural-key` 参数，只保留 `--natural-foreign`，使用旧参数会报错。

#### Step 3: 执行代码改动

按文件清单完成所有代码修改（settings.py、.env、models、utils、admin）。

#### Step 4: 安装依赖并运行迁移

```bash
pip install psycopg2-binary pgvector django-redis django-cors-headers
python manage.py migrate
```

> **踩坑 1**：`HnswIndex` 要求 `django.contrib.postgres` 在 INSTALLED_APPS 中，否则报错：
> `postgres.E005: 'django.contrib.postgres' must be in INSTALLED_APPS in order to use HnswIndex.`
>
> 解决：在 INSTALLED_APPS 中添加 `'django.contrib.postgres'`。

> **踩坑 2**：Django 自动生成的迁移使用 `embedding::vector(1024)` 做类型转换，但 PostgreSQL 不支持 `jsonb → vector` 直接转换，报错：
> `cannot cast type jsonb to vector`
>
> 解决：修改迁移文件为自定义 SQL，使用两步转换 `embedding::text::vector(1024)`：
> ```python
> migrations.RunSQL(
>     sql='''
>         ALTER TABLE web_memoryitem
>         ALTER COLUMN embedding TYPE vector(1024)
>         USING embedding::text::vector(1024);
>     ''',
>     reverse_sql='''
>         ALTER TABLE web_memoryitem
>         ALTER COLUMN embedding TYPE jsonb
>         USING embedding::text::jsonb;
>     ''',
> )
> ```

#### Step 5: 导入数据到 PostgreSQL

```bash
python manage.py loaddata web_data.json
```

> **踩坑 3**：`loaddata full_data.json` 会与 `migrate` 已创建的 Django 内置数据（contenttypes、permissions）冲突，报 `UniqueViolation`。
>
> 解决：从导出文件中过滤出 `web.*` 和 `auth.user` 数据，排除 `contenttypes` 和 `auth.permission`（migrate 已自动创建）。

---

### 记忆检索工作流

迁移后的完整记忆检索工作流：

```
用户发送消息
    │
    ▼
┌─────────────────────────────────┐
│  1. 生成查询向量                 │
│  get_embedding(query)            │
│  → 阿里云 text-embedding-v3     │
│  → 返回 1024 维 float 列表      │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  2. 数据库侧相似度检索           │
│  CosineDistance('embedding',     │
│                query_embedding)  │
│  → PostgreSQL 计算               │
│  → HNSW 索引加速 O(log N)       │
│  → ORDER BY distance LIMIT 5    │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  3. 更新访问统计                 │
│  access_count += 1              │
│  last_accessed = now()          │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  4. 注入 LLM 上下文             │
│  context_builder 组装            │
│  → 系统提示 + 对话历史 + 记忆    │
└────────────┬────────────────────┘
             │
             ▼
        LLM 生成回复
```

**记忆去重流程**（新记忆入库前）：

```
LLM 从对话中提取记忆点
    │
    ▼
┌─────────────────────────────────┐
│  find_similar_memory()          │
│  → CosineDistance ORDER BY      │
│  → HNSW 索引取最近邻            │
│  → distance ≤ 0.15 ?            │
│    (等价 similarity ≥ 0.85)     │
└───────┬─────────────┬───────────┘
        │             │
    相似              不相似
        │             │
        ▼             ▼
  合并/更新权重    创建新 MemoryItem
```

**记忆衰减流程**（每次对话后）：

```
对话结束
    │
    ▼
┌──────────────────────────────┐
│  decay_memory_weights()      │
│  weight = importance         │
│    × e^(-0.693 × 天数/30)   │
│    × (1 + 0.05 × 引用次数)  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  archive_low_weight_memories()│
│  删除 weight < 0.05 的记忆    │
└──────────────────────────────┘
```

> 衰减和归档函数不涉及向量检索，迁移后无需改动。

---

### HNSW 索引说明

HNSW（Hierarchical Navigable Small World）是项目使用的向量索引类型，核心概念：

- **结构**：多层图，上层稀疏（快速跳转），下层稠密（精确定位）
- **搜索**：从顶层入口贪心走向最近邻，逐层下降，最终在底层找到结果
- **近似**：不保证绝对最近邻，但以极大概率找到足够接近的结果，换取 O(log N) 速度

项目中的参数：

| 参数 | 值 | 含义 |
|---|---|---|
| `m` | 16 | 每个节点每层最大连接数，值越大越精确但内存越多 |
| `ef_construction` | 64 | 构建索引时的搜索宽度，值越大构建越慢但索引质量越好 |
| `opclasses` | `vector_cosine_ops` | 使用余弦距离度量，与语义相似度匹配 |

适合千级到十万级向量规模，是 HNSW 的经验最佳平衡点。

---

### 验证方式

1. `python manage.py check` 确认无配置错误
2. `python manage.py runserver` 启动后发送消息，确认记忆提取和检索正常
3. 访问 `/admin/` 确认 MemoryItem 可查看，embedding 字段不显示
4. 查询 PostgreSQL 确认索引存在：
   ```bash
   docker exec aifriends-postgres psql -U aifriends -d aifriends \
     -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='web_memoryitem';"
   ```
   预期输出包含 `web_memoryitem_embedding_hnsw ... USING hnsw (embedding vector_cosine_ops)`

---

### 回退方案

旧 `db.sqlite3` 文件仍保留在磁盘上。如需回退：

1. `settings.py` 的 DATABASES 改回 SQLite 配置
2. INSTALLED_APPS 移除 `django.contrib.postgres` 和 `pgvector`
3. `friend.py` 的 embedding 改回 `JSONField`，移除 HNSW 索引
4. `memory_retrieval.py` 恢复 Python 循环 + `cosine_similarity`
5. `docker stop aifriends-postgres` 停止容器
