"""
上下文构建器
实现 token 感知的动态消息窗口、自动摘要、语义记忆检索
"""
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from web.models.friend import Friend, Message, MemoryItem
from web.utils.token_cache import TokenCache
from web.utils.prompt_template import PromptTemplateEngine
from web.utils.memory_retrieval import retrieve_relevant_memories


# 触发摘要的消息累积阈值
SUMMARY_THRESHOLD = 20
# 语义检索返回的记忆条数
MEMORY_TOP_K = 8
# 各层 token 预算
MEMORY_BUDGET = 800
SUMMARY_BUDGET = 500


class ContextBuilder:
    """
    构建发送给 LLM 的完整上下文

    结构: [SystemPrompt] + [语义记忆层] + [摘要层] + [近期对话(token预算约束)] + [当前消息]
    """

    def __init__(self, friend: Friend, current_message: str,
                 image_analysis: str = ""):
        self.friend = friend
        self.current_message = current_message
        self.image_analysis = image_analysis
        self.token_cache = TokenCache()

    def build(self) -> list:
        """构建完整的消息列表"""
        messages = []

        # 检索语义相关记忆（一次调用，两处复用）
        relevant_memories = retrieve_relevant_memories(
            self.friend, self.current_message, top_k=MEMORY_TOP_K
        )

        # 1. 系统提示词
        system_prompt = self._build_system_prompt(relevant_memories)
        messages.append(system_prompt)

        # 2. 对话摘要层
        summary = self.friend.conversation_summary
        if summary:
            summary = self._truncate_to_budget(summary, SUMMARY_BUDGET)
            messages.append(SystemMessage(
                content=f"【之前的对话摘要】\n{summary}"
            ))

        # 4. 近期对话（受 token 预算约束）
        history_messages = self._build_recent_messages()
        messages.extend(history_messages)

        # 5. 当前用户消息
        messages.append(HumanMessage(content=self.current_message))

        return messages

    def _build_system_prompt(self, relevant_memories: list) -> SystemMessage:
        """构建系统提示词"""
        from web.utils.prompt_template import PromptTemplateManager

        memory_lines = [f"- {m.content}" for m in relevant_memories] if relevant_memories else []
        memory_text = self._truncate_to_budget('\n'.join(memory_lines), MEMORY_BUDGET)

        prompt_data = PromptTemplateManager.create_system_prompt(
            friend=self.friend,
            user_message=self.current_message,
            image_analysis=self.image_analysis,
            memory_override=memory_text,
        )
        print(f"[ContextBuilder] 系统提示词字段数: {len(prompt_data['context_data'])}, 记忆条数: {len(relevant_memories)}")
        return SystemMessage(content=prompt_data['system_instructions'])

    def _build_recent_messages(self) -> list:
        """
        构建近期消息，受 token 预算约束
        从最新消息往前取，直到 token 预算用完
        """
        budget = TokenCache.get_message_budget()
        all_messages = list(
            Message.objects.filter(friend=self.friend).order_by('-id')
        )
        # 只取摘要之后的消息（如果有摘要的话）
        if self.friend.summary_message_count > 0:
            all_messages = all_messages[:len(all_messages) - self.friend.summary_message_count]

        selected = []
        used_tokens = 0

        for m in all_messages:
            # 估算这一对消息的 token 数
            pair_tokens = (
                TokenCache.estimate_tokens(m.user_message) +
                TokenCache.estimate_tokens(m.output)
            )
            if used_tokens + pair_tokens > budget:
                break
            selected.append(m)
            used_tokens += pair_tokens

        selected.reverse()

        result = []
        for m in selected:
            safe_msg = PromptTemplateEngine._safe_escape(m.user_message)
            result.append(HumanMessage(content=safe_msg))
            result.append(AIMessage(content=m.output))

        print(f"[ContextBuilder] 近期消息: {len(selected)} 对, 使用 {used_tokens}/{budget} tokens")
        return result

    @staticmethod
    def _truncate_to_budget(text: str, budget: int) -> str:
        """按行粒度裁剪文本，使 token 数不超过预算"""
        if not text:
            return text
        tokens = TokenCache.estimate_tokens(text)
        if tokens <= budget:
            return text

        lines = text.split('\n')
        while lines and TokenCache.estimate_tokens('\n'.join(lines)) > budget:
            lines.pop()

        result = '\n'.join(lines)
        print(f"[ContextBuilder] 文本超预算裁剪: {tokens} -> {TokenCache.estimate_tokens(result)} (预算: {budget})")
        return result


def should_update_summary(friend: Friend) -> bool:
    """
    判断是否需要更新对话摘要

    触发条件: 自上次摘要以来的新消息数 >= SUMMARY_THRESHOLD
    """
    total = Message.objects.filter(friend=friend).count()
    new_since_summary = total - friend.summary_message_count
    return new_since_summary >= SUMMARY_THRESHOLD


def update_conversation_summary(friend: Friend):
    """
    更新对话摘要：将已摘要范围之外的消息交给 LLM 摘要，
    然后追加到已有摘要中
    """
    from web.views.friend.message.memory.graph import MemoryGraph
    from langchain_core.messages import SystemMessage, HumanMessage

    total = Message.objects.filter(friend=friend).count()
    if total == 0:
        return

    # 取需要摘要的消息（从上次摘要之后到最近 SUMMARY_THRESHOLD 条之前）
    recent_keep = 5  # 保留最近 5 条不参与摘要
    all_messages = list(
        Message.objects.filter(friend=friend).order_by('id')
    )

    summary_end = max(0, total - recent_keep)
    to_summarize = all_messages[friend.summary_message_count:summary_end]

    if not to_summarize:
        return

    # 构建要摘要的对话文本
    conversation_lines = []
    for m in to_summarize:
        safe_user = PromptTemplateEngine._safe_escape(m.user_message)
        safe_output = PromptTemplateEngine._safe_escape(m.output)
        conversation_lines.append(f"user: {safe_user}")
        conversation_lines.append(f"ai: {safe_output}")

    conversation_text = '\n'.join(conversation_lines)

    # 构建摘要请求
    existing_summary = friend.conversation_summary
    system_content = (
        "你是一个对话摘要助手。请将给定的对话内容生成一段简洁的摘要，"
        "保留关键信息、用户偏好和重要事件。"
        "不要遗漏任何重要细节。直接输出摘要内容，不要加标题。"
    )

    user_parts = []
    if existing_summary:
        user_parts.append(f"【已有摘要】\n{existing_summary}\n")
    user_parts.append(f"【新增对话】\n{conversation_text}\n")
    user_parts.append("请将已有摘要和新增对话合并，生成一份更新后的完整摘要。")

    inputs = {
        'messages': [
            SystemMessage(content=system_content),
            HumanMessage(content='\n'.join(user_parts)),
        ]
    }

    app = MemoryGraph.create_app()
    res = app.invoke(inputs)
    friend.conversation_summary = res['messages'][-1].content
    friend.summary_message_count = summary_end
    friend.save()

    print(f"[ContextBuilder] 摘要已更新，覆盖 {summary_end} 条消息")
