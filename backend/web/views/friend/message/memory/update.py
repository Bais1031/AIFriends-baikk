from django.utils.timezone import now
from langchain_core.messages import SystemMessage, HumanMessage

from web.models.friend import SystemPrompt, Message, Friend
from web.views.friend.message.memory.graph import MemoryGraph
from web.utils.prompt_template import PromptTemplateManager


def create_system_message():
    """使用模板隔离创建系统提示词"""
    from web.models.friend import Friend

    # 假设可以通过某种方式获取 friend 对象
    # 这里先创建一个空的上下文
    system_prompts = SystemPrompt.objects.filter(title='记忆').order_by('order_number')
    template = '\n'.join([sp.prompt for sp in system_prompts])

    # 使用模板引擎渲染
    from web.utils.prompt_template import PromptTemplateEngine
    rendered_prompt = PromptTemplateEngine.render_template(
        template,
        {'memory': '', 'character_profile': ''}
    )

    return SystemMessage(rendered_prompt)


def create_human_message(friend):
    """使用模板隔离创建人类消息"""
    from web.utils.prompt_template import PromptTemplateEngine

    # 安全地获取最近消息
    messages = list(Message.objects.filter(friend=friend).order_by('-id')[:10])
    messages.reverse()

    # 构建消息历史，并进行安全处理
    conversation_history = []
    for m in messages:
        safe_user_message = PromptTemplateEngine._safe_escape(m.user_message)
        safe_ai_output = PromptTemplateEngine._safe_escape(m.output)
        conversation_history.append(f'user: {safe_user_message}')
        conversation_history.append(f'ai: {safe_ai_output}')

    # 使用模板渲染
    context = {
        'memory': friend.memory,
        'recent_conversation': '\n'.join(conversation_history)
    }

    template = '''【原始记忆】
{{memory}}

【最近对话】
{{recent_conversation}}'''

    rendered_content = PromptTemplateEngine.render_template(template, context)

    return HumanMessage(content=rendered_content)


def update_memory(friend):
    app = MemoryGraph.create_app()

    inputs = {
        'messages': [
            create_system_message(),
            create_human_message(friend),
        ]
    }

    res = app.invoke(inputs)
    friend.memory = res['messages'][-1].content

    friend.update_time = now()
    friend.save()
