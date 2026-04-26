## PostgreSQL + pgvector 迁移方案

### 改进背景

当前记忆系统的向量检索采用全表扫描 + Python 内存计算余弦相似度：

```python
# memory_retrieval.py 现状
for m in memories:
    sim = cosine_similarity(query_embedding, m.embedding)  # 逐条 Python 计算
```

随 MemoryItem 条数增长，每次检索都需加载所有记忆并逐条计算，复杂度 O(N)。

迁移到 PostgreSQL + pgvector 后，可利用 HNSW 向量索引实现近似最近邻搜索，复杂度降至 O(log N)。

---

### 当前方案的性能分析

| 记忆条数 | Python 余弦相似度耗时 | 是否构成瓶颈 |
|---|---|---|
| < 100 条 | < 10ms | 否 |
| 100~500 条 | 10~50ms | 否 |
| 500~2000 条 | 50~200ms | 开始影响响应时间 |
| > 2000 条 | > 200ms | 明显拖慢聊天响应 |

**结论**：当前项目规模（每个 Friend 的记忆条数通常不超过几百条），SQLite + Python 内存计算完全够用。此迁移为**前瞻性优化**，建议在记忆条数达到 500+ 时再实施。

---

### 改动文件清单

| 文件 | 改动 |
|---|---|
| `requirements.txt` | 添加 `psycopg2-binary`、`pgvector`，补上缺失的 `django-redis`、`django-cors-headers` |
| `backend/settings.py` | DATABASES 从 SQLite 改为 PostgreSQL；INSTALLED_APPS 添加 `pgvector` |
| `.env` | 添加 PG_DATABASE/USER/PASSWORD/HOST/PORT |
| `web/models/friend.py` | `embedding` 从 JSONField 改为 VectorField(dimensions=1024)；Meta 添加 HNSW 索引 |
| `web/utils/embedding.py` | 删除 `cosine_similarity` 函数 |
| `web/utils/memory_retrieval.py` | Python 循环替换为 pgvector CosineDistance ORM 查询 |
| `web/admin.py` | 注册 MemoryItem（排除 embedding 字段） |
| `web/migrations/0013_*.py` | 自动生成：AlterField + HnswIndex |

无需改动：`context_builder.py`、`update.py`、任何视图文件。

---

### Step 1: 启动 PostgreSQL + pgvector 容器

```bash
docker run -d --name aifriends-postgres -p 5432:5432 \
  -e POSTGRES_DB=aifriends -e POSTGRES_USER=aifriends \
  -e POSTGRES_PASSWORD=aifriends_dev \
  -v aifriends-pgdata:/var/lib/postgresql/data \
  pgvector/pgvector:pg17

# 启用 vector 扩展
docker exec aifriends-postgres psql -U aifriends -d aifriends \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

使用 `pgvector/pgvector:pg17` 镜像，已内置 vector 扩展，无需单独安装。

---

### Step 2: 更新 requirements.txt

添加：
```
psycopg2-binary==2.9.10
pgvector==0.4.1
django-redis==5.4.0       # 已在项目中使用但缺失于 requirements.txt
django-cors-headers==4.7.0  # 同上
```

---

### Step 3: 更新 settings.py

DATABASES 从 SQLite 改为 PostgreSQL：
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('PG_DATABASE', 'aifriends'),
        'USER': os.getenv('PG_USER', 'aifriends'),
        'PASSWORD': os.getenv('PG_PASSWORD', 'aifriends_dev'),
        'HOST': os.getenv('PG_HOST', '127.0.0.1'),
        'PORT': os.getenv('PG_PORT', '5432'),
    }
}
```

INSTALLED_APPS 添加 `'pgvector'`。

---

### Step 4: 更新 .env

添加：
```bash
PG_DATABASE=aifriends
PG_USER=aifriends
PG_PASSWORD=aifriends_dev
PG_HOST=127.0.0.1
PG_PORT=5432
```

---

### Step 5: 更新 MemoryItem 模型

```python
from pgvector.django import VectorField, HnswIndex

class MemoryItem(models.Model):
    # ...其他字段不变...
    embedding = VectorField(dimensions=1024, null=True, blank=True)  # 替换 JSONField

    class Meta:
        ordering = ['-weight']
        indexes = [
            HnswIndex(
                name='web_memoryitem_embedding_hnsw',
                fields=['embedding'],
                opclasses=['vector_cosine_ops'],
                m=16,               # 每层最大连接数（默认值）
                ef_construction=64,  # 构建时搜索宽度（兼顾质量和速度）
            ),
        ]
```

HNSW 参数说明：
- `m=16`：每个节点在每层的最大连接数，值越大索引越精确但占用内存越多
- `ef_construction=64`：构建索引时的搜索宽度，值越大构建越慢但索引质量越好
- 这两个值是 HNSW 的标准默认值，适合千级到十万级向量规模

---

### Step 6: 更新 memory_retrieval.py

核心变化：Python 循环余弦相似度 → pgvector CosineDistance ORM 查询。

**retrieve_relevant_memories**：
```python
from pgvector.django import CosineDistance

def retrieve_relevant_memories(friend, query, top_k=5):
    query_embedding = get_embedding(query)
    if query_embedding is None:
        return list(friend.memories.all()[:top_k])

    memories = friend.memories.exclude(embedding__isnull=True)
    if not memories.exists():
        return list(friend.memories.all()[:top_k])

    # pgvector 余弦距离：0=完全相同，2=完全相反
    result = list(
        memories.annotate(distance=CosineDistance('embedding', query_embedding))
        .order_by('distance')[:top_k]
    )
    for m in result:
        m.access_count += 1
        m.save(update_fields=['access_count', 'last_accessed'])
    return result
```

**find_similar_memory**：
```python
def find_similar_memory(friend, content, threshold=0.85):
    embedding = get_embedding(content)
    if embedding is None:
        return None

    distance_threshold = 1.0 - threshold  # similarity >= 0.85 → distance <= 0.15
    best = friend.memories.exclude(embedding__isnull=True).annotate(
        distance=CosineDistance('embedding', embedding)
    ).order_by('distance').first()

    if best and best.distance <= distance_threshold:
        return best
    return None
```

注意：`CosineDistance` 返回距离（1 - 相似度），所以 similarity >= 0.85 等价于 distance <= 0.15。先用 ORDER BY 利用 HNSW 索引取最近邻，再在 Python 侧判断阈值。

**decay_memory_weights** 和 **archive_low_weight_memories** 无需改动。

---

### Step 7: 删除 cosine_similarity

从 `embedding.py` 中删除 `cosine_similarity` 函数（唯一调用方 memory_retrieval.py 已改用 pgvector）。仅保留 `get_embedding`。

---

### Step 8: 注册 MemoryItem Admin

```python
@admin.register(MemoryItem)
class MemoryItemAdmin(admin.ModelAdmin):
    list_display = ('content', 'category', 'importance', 'weight', 'access_count', 'created_at')
    list_filter = ('category',)
    search_fields = ('content',)
    exclude = ('embedding',)  # 1024维向量在Admin中无意义，排除
    raw_id_fields = ('friend',)
```

---

### Step 9: 数据迁移

需要保留 SQLite 中的现有数据，采用 dumpdata/loaddata 方式。

**重要：导出必须在切换数据库配置之前完成（还在用 SQLite 时）。**

```bash
# 1. 在 SQLite 配置下（代码还未改），导出所有数据
python manage.py dumpdata --natural-foreign --natural-key --output=full_data.json

# 2. 执行 Step 2-8 的代码改动，切换到 PostgreSQL

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动 PG 容器 + 启用 vector 扩展（Step 1）

# 5. 生成并运行迁移（在新 PostgreSQL 上建表）
python manage.py makemigrations web
python manage.py migrate

# 6. 导入数据
python manage.py loaddata full_data.json

# 7. 创建超级用户（dumpdata 不包含密码哈希，需手动创建）
python manage.py createsuperuser
```

注意事项：
- `--natural-foreign --natural-key` 使用自然键而非主键，避免外键冲突
- MemoryItem 的 embedding 字段：JSONField 导出为 JSON 数组 `[0.1, 0.2, ...]`，pgvector 的 VectorField 可接受同样格式，自动转为 `vector(1024)` 类型
- 如果 loaddata 报错，可先只导出核心数据：`python manage.py dumpdata web.Friend web.Message web.MemoryItem web.SystemPrompt --output=web_data.json`
- 旧 `db.sqlite3` 文件保留在磁盘上不受影响，可随时回退

---

### 改进前后对比

| 维度 | 改进前 | 改进后 |
|---|---|---|
| 数据库 | SQLite | PostgreSQL |
| embedding 存储 | JSONField（JSON 文本） | VectorField（原生 vector 类型） |
| 相似度计算 | Python 内存逐条计算 | PostgreSQL 数据库侧 CosineDistance |
| 检索复杂度 | O(N) 全表扫描 | O(log N) HNSW 近似最近邻 |
| 索引 | 无 | HNSW (m=16, ef_construction=64) |
| 并发写入 | SQLite 单写锁 | PostgreSQL 多连接并发 |
| Admin 查看 MemoryItem | 未注册 | 已注册，排除 embedding 字段 |

---

### 验证方式

1. `python manage.py runserver` 启动后发送消息，确认记忆提取和检索正常
2. 访问 `/admin/` 确认 MemoryItem 可查看，embedding 字段不显示
3. 直接查询 PostgreSQL 确认向量索引存在：
   ```bash
   docker exec aifriends-postgres psql -U aifriends -d aifriends \
     -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='web_memoryitem';"
   ```
4. 对比检索性能：在有多条记忆后，`retrieve_relevant_memories` 应走 HNSW 索引而非全表扫描
