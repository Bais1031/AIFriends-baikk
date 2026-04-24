"""
Token 缓存工具类
用于缓存 Token 计算结果，减少重复计算开销
"""
import re
from django.core.cache import cache
from typing import Optional


class TokenCache:
    """Token 缓存管理"""

    CACHE_PREFIX = "token_count"
    CACHE_TIMEOUT = 60 * 60 * 24  # 24小时

    # 上下文窗口 token 预算
    CONTEXT_BUDGET = 4096
    # 各部分优先级分配
    SYSTEM_PROMPT_RESERVE = 1500
    SUMMARY_RESERVE = 500

    @classmethod
    def get_token_count(cls, text: str, model: str = "default") -> Optional[int]:
        """获取缓存的 Token 数量"""
        cache_key = f"{cls.CACHE_PREFIX}:{model}:{hash(text)}"
        return cache.get(cache_key)

    @classmethod
    def set_token_count(cls, text: str, count: int, model: str = "default") -> None:
        """缓存 Token 数量"""
        cache_key = f"{cls.CACHE_PREFIX}:{model}:{hash(text)}"
        cache.set(cache_key, count, timeout=cls.CACHE_TIMEOUT)

    @classmethod
    def estimate_tokens(cls, text: str, model: str = "default") -> int:
        """
        估算 Token 数量（带缓存）
        中英文混合文本：按字符类型分别估算
        """
        if not text or not text.strip():
            return 0

        cached = cls.get_token_count(text, model)
        if cached is not None:
            return cached

        count = cls._count_mixed(text)
        cls.set_token_count(text, count, model)
        return count

    @classmethod
    def _count_mixed(cls, text: str) -> int:
        """
        中英文混合文本的 token 估算
        中文约 1 token ≈ 1.5 字符
        英文约 1 token ≈ 4 字符
        标点/数字约 1 token ≈ 2 字符
        """
        chinese_chars = len(re.findall(r'[一-鿿㐀-䶿]', text))
        remaining = text
        for pattern in [r'[一-鿿㐀-䶿]']:
            remaining = re.sub(pattern, '', remaining)

        english_words = len(re.findall(r'[a-zA-Z]+', remaining))
        for pattern in [r'[a-zA-Z]+']:
            remaining = re.sub(pattern, '', remaining)

        punctuation_count = len(remaining)

        tokens = (
            chinese_chars / 1.5 +
            english_words * 1.3 +
            punctuation_count / 2
        )
        return max(int(tokens), 1)

    @classmethod
    def get_message_budget(cls) -> int:
        """获取对话历史可用的 token 预算"""
        return cls.CONTEXT_BUDGET - cls.SYSTEM_PROMPT_RESERVE - cls.SUMMARY_RESERVE


# 使用示例
if __name__ == "__main__":
    text = "这是一段测试文本，with some English mixed in."
    tokens = TokenCache.estimate_tokens(text)
    print(f"Token 数量: {tokens}")
