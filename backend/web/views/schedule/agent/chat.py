import json
import threading
from queue import Queue, Full

from django.http import StreamingHttpResponse
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessageChunk
from rest_framework.renderers import BaseRenderer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from web.views.schedule.agent.graph import ScheduleGraph, SYSTEM_PROMPT


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

        # 设置当前用户 ID 供 tool 使用
        ScheduleGraph._current_user_id = request.user.id

        inputs = {
            'messages': [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=message),
            ]
        }

        app = ScheduleGraph.create_app()
        cancel = threading.Event()
        mq = Queue(maxsize=100)

        thread = threading.Thread(
            target=self.work,
            args=(app, inputs, mq, cancel),
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

        yield 'data: [DONE]\n\n'

    def work(self, app, inputs, mq, cancel):
        try:
            import asyncio
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
        async for msg, metadata in app.astream(inputs, stream_mode="messages"):
            if cancel.is_set():
                break
            if isinstance(msg, BaseMessageChunk):
                if msg.content:
                    try:
                        mq.put({'content': msg.content}, timeout=5)
                    except Full:
                        break
                elif msg.tool_calls:
                    try:
                        mq.put({'content': '\n\n正在处理中...'}, timeout=5)
                    except Full:
                        break
