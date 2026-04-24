import asyncio
import base64
import json
import os
import threading
import uuid
from queue import Queue

import websockets
from django.http import StreamingHttpResponse
from langchain_core.messages import HumanMessage, BaseMessageChunk, AIMessage
from rest_framework.renderers import BaseRenderer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from web.models.friend import Friend, Message
from web.views.friend.message.chat.graph import ChatGraph
from web.views.friend.message.memory.update import update_memory
from web.utils.token_cache import TokenCache
from web.utils.context_builder import ContextBuilder, should_update_summary, update_conversation_summary


class SSERenderer(BaseRenderer):
    media_type = 'text/event-stream'
    format = 'txt'
    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


# 记忆更新触发频率：每 N 条消息触发一次
MEMORY_UPDATE_INTERVAL = 5


class MessageChatView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [SSERenderer]

    def post(self, request):
        friend_id = request.data['friend_id']
        message = request.data['message'].strip()
        if not message:
            return Response({
                'result': '消息不能为空'
            })
        friends = Friend.objects.filter(pk=friend_id, me__user=request.user)
        if not friends.exists():
            return Response({
                'result': '好友不存在'
            })
        friend = friends.first()

        # 使用 ContextBuilder 构建完整上下文
        builder = ContextBuilder(friend=friend, current_message=message)
        inputs = {'messages': builder.build()}

        app = ChatGraph.create_app()

        response = StreamingHttpResponse(
            self.event_stream(app, inputs, friend, message),
            content_type='text/event-stream',
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response


    async def tts_sender(self, app, inputs, mq, ws, task_id):
        async for msg, metadata in app.astream(inputs, stream_mode="messages"):
            if isinstance(msg, BaseMessageChunk):
                if msg.content:
                    await ws.send(json.dumps({
                        "header": {
                            "action": "continue-task",
                            "task_id": task_id,
                            "streaming": "duplex"
                        },
                        "payload": {
                            "input": {
                                "text": msg.content,
                            }
                        }
                    }))
                    mq.put_nowait({'content': msg.content})
                if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                    mq.put_nowait({'usage': msg.usage_metadata})
        await ws.send(json.dumps({
            "header": {
                "action": "finish-task",
                "task_id": task_id,
                "streaming": "duplex"
            },
            "payload": {
                "input": {}
            }
        }))


    async def tts_receiver(self, mq, ws):
        async for msg in ws:
            if isinstance(msg, bytes):
                audio = base64.b64encode(msg).decode('utf-8')
                mq.put_nowait({'audio': audio})
            else:
                data = json.loads(msg)
                event = data['header']['event']
                if event in ['task-finished', 'task-failed']:
                    break


    async def run_tts_tasks(self, app, inputs, mq):
        task_id = uuid.uuid4().hex
        api_key = os.getenv('API_KEY')
        wss_url = os.getenv('WSS_URL')
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        async with websockets.connect(wss_url, additional_headers=headers) as ws:
            await ws.send(json.dumps({
                "header": {
                    "action": "run-task",
                    "task_id": task_id,
                    "streaming": "duplex"
                },
                "payload": {
                    "task_group": "audio",
                    "task": "tts",
                    "function": "SpeechSynthesizer",
                    "model": "cosyvoice-v3-flash",
                    "parameters": {
                        "text_type": "PlainText",
                        "voice": "longanyang",
                        "format": "mp3",
                        "sample_rate": 22050,
                        "volume": 50,
                        "rate": 1.25,
                        "pitch": 1
                    },
                    "input": {}
                }
            }))
            async for msg in ws:
                if json.loads(msg)['header']['event'] == 'task-started':
                    break
            await asyncio.gather(
                self.tts_sender(app, inputs, mq, ws, task_id),
                self.tts_receiver(mq, ws),
            )


    def work(self, app, inputs, mq):
        try:
            asyncio.run(self.run_tts_tasks(app, inputs, mq))
        finally:
            mq.put_nowait(None)


    def event_stream(self, app, inputs, friend, message):
        mq = Queue()
        thread = threading.Thread(target=self.work, args=(app, inputs, mq))
        thread.start()

        full_output = ''
        full_usage = {}
        while True:
            msg = mq.get()
            if not msg:
                break
            if msg.get('content', None):
                full_output += msg['content']
                yield f'data: {json.dumps({'content': msg['content']}, ensure_ascii=False)}\n\n'
            if msg.get('audio', None):
                yield f'data: {json.dumps({'audio': msg['audio']}, ensure_ascii=False)}\n\n'
            if msg.get('usage', None):
                full_usage = msg['usage']

        yield 'data: [DONE]\n\n'

        # 优先使用 LLM 返回的实际 token 用量，回退到估算
        input_tokens = full_usage.get('input_tokens', 0) or TokenCache.estimate_tokens(
            ' '.join([m.content for m in inputs['messages'] if hasattr(m, 'content')])
        )
        output_tokens = full_usage.get('output_tokens', 0) or TokenCache.estimate_tokens(full_output)
        total_tokens = input_tokens + output_tokens

        Message.objects.create(
            friend=friend,
            user_message=message[:500],
            input=json.dumps(
                [m.model_dump() for m in inputs['messages']],
                ensure_ascii=False,
            )[:10000],
            output=full_output[:500],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

        # 每隔 N 条消息更新长期记忆（修复原 % 1 bug）
        msg_count = Message.objects.filter(friend=friend).count()
        if msg_count % MEMORY_UPDATE_INTERVAL == 0:
            update_memory(friend)

        # 检查是否需要更新对话摘要
        if should_update_summary(friend):
            update_conversation_summary(friend)
