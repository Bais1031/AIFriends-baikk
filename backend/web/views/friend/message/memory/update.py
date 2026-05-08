"""
长期记忆更新模块
增量提取 + 去重合并，替代全量替换
"""
import json
from langchain_core.messages import SystemMessage, HumanMessage

from web.models.friend import SystemPrompt, Message, Friend, MemoryItem
from web.views.friend.message.memory.graph import MemoryGraph
from web.utils.embedding import get_embedding
from web.utils.memory_retrieval import find_similar_memory, decay_memory_weights, archive_low_weight_memories
from web.utils.prompt_template import PromptTemplateEngine


EXTRACTION_SYSTEM_PROMPT = """你是一个记忆提取助手。请从对话中提取值得长期记住的信息。

## 工具使用
你有 `query_memories` 工具可以搜索已有的长期记忆。在提取新记忆前，**必须先调用此工具**检查是否已有相似记忆，以便：
- 避免重复提取已有的记忆
- 发现矛盾：如果用户改变了偏好，应标记为 "update" 而非新增

## 输出格式（严格JSON数组，不要输出其他内容）
[
  {"content": "记忆内容", "category": "preference|event|fact|emotion|general", "importance": 0.0-1.0, "action": "add"}
]

当发现用户的新说法与已有记忆矛盾时（如用户之前说喜欢辣，现在说不吃辣），使用 update 动作：
[
  {"content": "更新后的记忆内容", "category": "preference|event|fact|emotion|general", "importance": 0.0-1.0, "action": "update", "old_content": "旧记忆的原文"}
]

## action 字段说明
- "add": 新增记忆（默认值，可省略）
- "update": 更新已有记忆（必须提供 old_content 字段，值为已有记忆的原文内容，用于匹配旧记忆）

## 规则
- 只提取重要的、值得长期保留的信息
- preference: 用户偏好、喜好、习惯
- event: 重要事件、经历
- fact: 客观事实、身份信息
- emotion: 情感状态、心理特征
- general: 其他重要信息
- importance 越高表示越重要（0.0-1.0）
- 如果没有值得记住的信息，输出空数组: []
- 日常寒暄、无意义闲聊不要提取
- 提取前先用 query_memories 工具搜索已有记忆，避免重复
- 如果已有记忆与新信息矛盾，用 "update" 动作替换旧记忆，而非重复添加"""


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
            valid = [item for item in items if isinstance(item, dict) and 'content' in item]
            for item in valid:
                item.setdefault('action', 'add')
            return valid
    except json.JSONDecodeError:
        pass

    # 尝试从 markdown 代码块中提取
    import re
    match = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
    if match:
        try:
            items = json.loads(match.group(1).strip())
            if isinstance(items, list):
                valid = [item for item in items if isinstance(item, dict) and 'content' in item]
                for item in valid:
                    item.setdefault('action', 'add')
                return valid
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
        action = item.get('action', 'add')

        if action == 'update':
            # LLM 识别到矛盾，需要更新已有记忆
            old_content = item.get('old_content', '').strip()
            target = None

            # 优先用 old_content 精确查找
            if old_content:
                target = find_similar_memory(friend, old_content)

            # 回退：用新内容查找相似记忆
            if target is None:
                target = find_similar_memory(friend, content)

            if target:
                # 更新旧记忆的内容和嵌入
                target.content = content
                target.category = category
                target.importance = max(target.importance, importance)
                target.weight = max(target.weight, importance)
                new_embedding = get_embedding(content)
                if new_embedding is not None:
                    target.embedding = new_embedding
                target.save(update_fields=['content', 'category', 'importance', 'weight', 'embedding'])
                print(f"[Memory] 更新已有记忆: {content[:50]} (原: {old_content[:50] if old_content else 'N/A'})")
            else:
                # 找不到旧记忆，当作新增处理
                embedding = get_embedding(content)
                MemoryItem.objects.create(
                    friend=friend,
                    content=content,
                    category=category,
                    importance=importance,
                    weight=importance,
                    embedding=embedding,
                )
                print(f"[Memory] 未找到旧记忆，新增: [{category}] {content[:50]}")
        else:
            # action == "add"：原有逻辑
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

    app = MemoryGraph.create_app(friend)
    inputs = {'messages': [system_msg, human_msg]}
    res = app.invoke(inputs)

    llm_output = res['messages'][-1].content
    new_items = _parse_extraction_result(llm_output)

    if new_items:
        _merge_memories(friend, new_items)
        print(f"[Memory] 提取到 {len(new_items)} 条新记忆")
    else:
        print("[Memory] 本次无新记忆提取")

    # 执行权重衰减和低权重归档
    decay_memory_weights(friend)
    archive_low_weight_memories(friend)

