"""
记忆检索与衰减模块
基于语义相似度检索与当前对话最相关的记忆，并提供权重衰减
"""
import math

from django.utils.timezone import now as timezone_now
from pgvector.django import CosineDistance

from web.models.friend import MemoryItem, Friend
from web.utils.embedding import get_embedding


# 默认检索参数
DEFAULT_TOP_K = 5
SIMILARITY_THRESHOLD = 0.85
# 权重衰减半衰期（天）
DECAY_HALF_LIFE = 30
# 低权重归档阈值
ARCHIVE_WEIGHT_THRESHOLD = 0.05


def retrieve_relevant_memories(friend: Friend, query: str,
                               top_k: int = DEFAULT_TOP_K) -> list[MemoryItem]:
    """检索与当前消息语义最相关的 top-K 条记忆"""
    query_embedding = get_embedding(query)
    if query_embedding is None:
        return list(friend.memories.all()[:top_k])

    memories = friend.memories.exclude(embedding__isnull=True)
    if not memories.exists():
        return list(friend.memories.all()[:top_k])

    result = list(
        memories.annotate(distance=CosineDistance('embedding', query_embedding))
        .order_by('distance')[:top_k]
    )

    if result:
        for m in result:
            m.access_count += 1
            m.last_accessed = timezone_now()
        MemoryItem.objects.bulk_update(result, ['access_count', 'last_accessed'])

    return result


def find_similar_memory(friend: Friend, content: str,
                        threshold: float = SIMILARITY_THRESHOLD) -> MemoryItem | None:
    """查找与给定内容语义相似的已有记忆，用于去重"""
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


def decay_memory_weights(friend: Friend):
    """
    对记忆权重执行时间衰减
    公式: weight = importance × e^(-0.693 × 天数/半衰期) × (1 + 0.05 × 引用次数)
    """
    now = timezone_now()
    decay_constant = 0.693 / DECAY_HALF_LIFE  # ln(2) / 半衰期

    memories = list(friend.memories.all())
    for m in memories:
        days_since = (now - m.last_accessed).days
        decay = math.exp(-decay_constant * days_since)
        m.weight = m.importance * decay * (1 + 0.05 * m.access_count)
        m.weight = max(0.0, min(1.0, m.weight))

    if memories:
        MemoryItem.objects.bulk_update(memories, ['weight'])


def archive_low_weight_memories(friend: Friend, threshold: float = ARCHIVE_WEIGHT_THRESHOLD):
    """删除权重低于阈值的记忆条目"""
    deleted, _ = friend.memories.filter(weight__lt=threshold).delete()
    if deleted:
        print(f"[Memory] 归档 {deleted} 条低权重记忆 (权重 < {threshold})")
