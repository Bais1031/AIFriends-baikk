"""
向量嵌入工具
使用阿里云 text-embedding-v3 生成文本向量
"""
import os
from typing import Optional

from openai import OpenAI


_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv('API_KEY'),
            base_url=os.getenv('API_BASE'),
        )
    return _client


def get_embedding(text: str) -> Optional[list[float]]:
    """生成文本的向量嵌入"""
    if not text or not text.strip():
        return None
    try:
        client = _get_client()
        resp = client.embeddings.create(
            model="text-embedding-v3",
            input=text[:2048],
            dimensions=1024,
        )
        return resp.data[0].embedding
    except Exception as e:
        print(f"[Embedding] 生成向量失败: {e}")
        return None
