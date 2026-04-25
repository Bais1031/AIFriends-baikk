"""
长期记忆更新模块
增量提取 + 去重合并，替代全量替换
"""
import json
from django.utils.timezone import now
from langchain_core.messages import SystemMessage, HumanMessage

from web.models.friend import SystemPrompt, Message, Friend, MemoryItem
from web.views.friend.message.memory.graph import MemoryGraph
from web.utils.embedding import get_embedding
from web.utils.memory_retrieval import find_similar_memory, decay_memory_weights, archive_low_weight_memories
from web.utils.prompt_template import PromptTemplateEngine


EXTRACTION_SYSTEM_PROMPT = """你是一个记忆提取助手。请从对话中提取值得长期记住的信息。

输出格式（严格JSON数组，不要输出其他内容）：
[
  {"content": "记忆内容", "category": "preference|event|fact|emotion|general", "importance": 0.0-1.0}
]

规则：
- 只提取重要的、值得长期保留的信息
- preference: 用户偏好、喜好、习惯
- event: 重要事件、经历
- fact: 客观事实、身份信息
- emotion: 情感状态、心理特征
- general: 其他重要信息
- importance 越高表示越重要（0.0-1.0）
- 如果没有值得记住的信息，输出空数组: []
- 日常寒暄、无意义闲聊不要提取"""


def _build_extraction_input(friend: Friend) -> tuple[SystemMessage, HumanMessage]:
    """构建增量提取的输入消息"""
    # 取最近 MEMORY_UPDATE_INTERVAL 条对话
    messages = list(Message.objects.filter(friend=friend).order_by('-id')[:10])
    messages.reverse()

    conversation_lines = []
    for m in messages:
        safe_user = PromptTemplateEngine._safe_escape(m.user_message)
        safe_output = PromptTemplateEngine._safe_escape(m.output)
        conversation_lines.append(f"user: {safe_user}")
        conversation_lines.append(f"ai: {safe_output}")

    conversation_text = '\n'.join(conversation_lines)

    system_msg = SystemMessage(content=EXTRACTION_SYSTEM_PROMPT)
    human_msg = HumanMessage(content=f"【最近对话】\n{conversation_text}\n\n请提取值得长期记住的信息。")

    return system_msg, human_msg


def _parse_extraction_result(text: str) -> list[dict]:
    """解析 LLM 输出的记忆提取结果"""
    try:
        # 尝试直接解析
        items = json.loads(text)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict) and 'content' in item]
    except json.JSONDecodeError:
        pass

    # 尝试从 markdown 代码块中提取
    import re
    match = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
    if match:
        try:
            items = json.loads(match.group(1).strip())
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict) and 'content' in item]
        except json.JSONDecodeError:
            pass

    return []


def _merge_memories(friend: Friend, new_items: list[dict]):
    """将提取的新记忆与已有记忆去重合并"""
    for item in new_items:
        content = item.get('content', '').strip()
        if not content:
            continue

        category = item.get('category', 'general')
        importance = float(item.get('importance', 0.5))
        importance = max(0.0, min(1.0, importance))

        # 查找语义相似的已有记忆
        similar = find_similar_memory(friend, content)

        if similar:
            # 合并：重复提及提升权重
            similar.weight = min(similar.weight + 0.1, 1.0)
            similar.importance = max(similar.importance, importance)
            similar.save(update_fields=['weight', 'importance'])
            print(f"[Memory] 合并已有记忆: {similar.content[:50]} (权重提升至 {similar.weight:.2f})")
        else:
            # 追加新记忆
            embedding = get_embedding(content)
            MemoryItem.objects.create(
                friend=friend,
                content=content,
                category=category,
                importance=importance,
                weight=importance,
                embedding=embedding,
            )
            print(f"[Memory] 新增记忆: [{category}] {content[:50]}")


def update_memory(friend: Friend):
    """
    增量更新长期记忆：
    1. 从最近对话中提取新记忆点
    2. 与已有记忆语义去重
    3. 合并或追加
    """
    system_msg, human_msg = _build_extraction_input(friend)

    app = MemoryGraph.create_app()
    inputs = {'messages': [system_msg, human_msg]}
    res = app.invoke(inputs)

    llm_output = res['messages'][-1].content
    new_items = _parse_extraction_result(llm_output)

    if new_items:
        _merge_memories(friend, new_items)
        print(f"[Memory] 提取到 {len(new_items)} 条新记忆")
    else:
        print("[Memory] 本次无新记忆提取")

    # 同步更新 friend.memory 为缓存字段（拼接当前所有记忆）
    _refresh_memory_cache(friend)

    # 执行权重衰减和低权重归档
    decay_memory_weights(friend)
    archive_low_weight_memories(friend)


def _refresh_memory_cache(friend: Friend):
    """将 MemoryItem 拼接为文本缓存到 friend.memory，保持向后兼容"""
    memories = friend.memories.all()[:20]
    if memories:
        lines = []
        for m in memories:
            lines.append(f"- [{m.category}] {m.content}")
        friend.memory = '\n'.join(lines)
    else:
        friend.memory = ''
    friend.update_time = now()
    friend.save()
