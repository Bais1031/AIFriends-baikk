"""
Token 缓存工具类
用于缓存 Token 计算结果，减少重复计算开销
"""
from django.core.cache import cache
from typing import Optional


class TokenCache:
    """Token 缓存管理"""

    CACHE_PREFIX = "token_count"
    CACHE_TIMEOUT = 60 * 60 * 24  # 24小时

    @classmethod
    def get_token_count(cls, text: str, model: str = "qwen2.5:3b") -> Optional[int]:
        """获取缓存的 Token 数量"""
        cache_key = f"{cls.CACHE_PREFIX}:{model}:{hash(text)}"
        return cache.get(cache_key)

    @classmethod
    def set_token_count(cls, text: str, count: int, model: str = "qwen2.5:3b") -> None:
        """缓存 Token 数量"""
        cache_key = f"{cls.CACHE_PREFIX}:{model}:{hash(text)}"
        cache.set(cache_key, count, timeout=cls.CACHE_TIMEOUT)

    @classmethod
    def estimate_tokens(cls, text: str, model: str = "qwen2.5:3b") -> int:
        """估算 Token 数量（带缓存）"""
        if not text or not text.strip():
            return 0

        # 1. 尝试从缓存获取
        cached = cls.get_token_count(text, model)
        if cached is not None:
            return cached

        # 2. 粗略估算
        # 中文约 1 token ≈ 1.5 字符，英文约 1 token ≈ 4 字符
        # 这里采用保守估算: 1 token ≈ 2 字符
        count = len(text) // 2

        # 3. 写入缓存
        cls.set_token_count(text, count, model)

        return count


# 使用示例
if __name__ == "__main__":
    text = "这是一段测试文本"
    tokens = TokenCache.estimate_tokens(text)
    print(f"Token 数量: {tokens}")
