import json
import threading
from queue import Queue, Full

from django.http import StreamingHttpResponse
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from rest_framework.renderers import BaseRenderer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from web.models.agent_conversation import AgentConversation
from web.views.schedule.agent.graph import ScheduleGraph, get_system_prompt


class SSERenderer(BaseRenderer):
    media_type = 'text/event-stream'
    format = 'txt'
    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


class ScheduleAgentChatView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [SSERenderer]

    def post(self, request):
        message = request.data.get('message', '').strip()
        if not message:
            return Response({'result': '消息不能为空'})

        user_profile = request.user.userprofile

        # 加载对话历史（最近 20 条）
        history = AgentConversation.objects.filter(
            user=user_profile
        ).order_by('-create_time')[:20]
        history = list(reversed(history))

        # 构建消息列表
        messages = [SystemMessage(content=get_system_prompt())]
        for h in history:
            if h.role == 'human':
                messages.append(HumanMessage(content=h.content))
            else:
                messages.append(AIMessage(content=h.content))
        messages.append(HumanMessage(content=message))

        # 保存用户消息
        AgentConversation.objects.create(
            user=user_profile,
            role='human',
            content=message,
        )

        # 设置当前用户 ID 供 tool 使用（线程安全）
        ScheduleGraph._current_user_id = request.user.id

        inputs = {'messages': messages}

        app = ScheduleGraph.create_app()
        cancel = threading.Event()
        mq = Queue(maxsize=100)

        thread = threading.Thread(
            target=self.work,
            args=(app, inputs, mq, cancel, user_profile),
            daemon=True,
        )
        thread.start()

        response = StreamingHttpResponse(
            self.event_stream(mq, cancel),
            content_type='text/event-stream',
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response

    def event_stream(self, mq, cancel):
        full_output = ''
        try:
            while True:
                try:
                    msg = mq.get(timeout=30)
                except Exception:
                    break
                if msg is None:
                    break
                if msg.get('content'):
                    full_output += msg['content']
                    yield f'data: {json.dumps({"content": msg["content"]}, ensure_ascii=False)}\n\n'
        except Exception:
            pass
        finally:
            cancel.set()

        # 保存 AI 回复到对话历史
        if full_output:
            try:
                user_profile = self._save_user_profile
                AgentConversation.objects.create(
                    user=user_profile,
                    role='ai',
                    content=full_output,
                )
            except Exception:
                pass

        yield 'data: [DONE]\n\n'

    def work(self, app, inputs, mq, cancel, user_profile):
        try:
            import asyncio
            self._save_user_profile = user_profile
            asyncio.run(self._stream(app, inputs, mq, cancel))
        except Exception as e:
            print(f"[ScheduleAgent] 异常: {e}")
            try:
                mq.put({'content': '抱歉，处理过程中遇到了问题。'}, timeout=5)
            except Full:
                pass
        finally:
            try:
                mq.put_nowait(None)
            except Full:
                pass

    async def _stream(self, app, inputs, mq, cancel):
        prev_count = 0
        async for event in app.astream(inputs, stream_mode="values"):
            if cancel.is_set():
                break
            messages = event.get('messages', [])
            new_msgs = messages[prev_count:]
            prev_count = len(messages)

            for msg in new_msgs:
                if isinstance(msg, (SystemMessage, HumanMessage, ToolMessage)):
                    continue
                if hasattr(msg, 'content') and msg.content:
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        try:
                            mq.put({'content': '\n\n正在处理中...'}, timeout=5)
                        except Full:
                            return
                    else:
                        try:
                            mq.put({'content': msg.content}, timeout=5)
                        except Full:
                            return
