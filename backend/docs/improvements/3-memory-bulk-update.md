# 记忆操作批量更新：消除 N+1 查询

## 背景

`memory_retrieval.py` 中两个函数存在 N+1 写入问题：

| 函数 | 问题 | 影响 |
|---|---|---|
| `decay_memory_weights()` | 逐条 `save()` 更新 weight | 500 条记忆 = 500 次 DB 写入 |
| `retrieve_relevant_memories()` | 逐条 `save()` 更新 access_count/last_accessed | 检索 5 条 = 5 次 DB 写入 |

## 改动

**文件**: `backend/web/utils/memory_retrieval.py`

### 1. `decay_memory_weights()` — N 次 save → 1 次 bulk_update

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

### 2. `retrieve_relevant_memories()` — K 次 save → 1 次 bulk_update

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

### 为什么不用原生 SQL

优化文档中给出了原生 SQL 方案，但项目当前用 SQLite 开发，`EXTRACT(EPOCH FROM ...)` 是 PG 专有语法，开发环境无法运行。`bulk_update` 跨数据库兼容，性能已足够（1 次 UPDATE vs N 次 UPDATE）。

## 验证

1. 触发记忆衰减，确认权重正常衰减，DB 只执行 1 次 UPDATE
2. 聊天触发记忆检索，确认 access_count 正常递增，DB 只执行 1 次 UPDATE
3. 检查无回归：低权重归档、语义检索等功能正常
