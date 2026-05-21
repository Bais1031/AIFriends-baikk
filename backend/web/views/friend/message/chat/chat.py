import asyncio
import base64
import json
import os
import threading
import uuid
from queue import Queue, Full

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
from web.throttles import ChatThrottle


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
    throttle_classes = [ChatThrottle]

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


    async def tts_sender(self, app, inputs, mq, ws, task_id, cancel):
        try:
            async for msg, metadata in app.astream(inputs, stream_mode="messages"):
                if cancel.is_set():
                    print("[TTS] 用户已断开，提前终止流式输出")
                    break
                if isinstance(msg, BaseMessageChunk):
                    if msg.content:
                        try:
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
                        except Exception as e:
                            print(f"[TTS] 发送文本到 TTS 失败，降级为纯文本: {e}")
                        try:
                            mq.put({'content': msg.content}, timeout=5)
                        except Full:
                            print("[TTS] 队列已满，跳过当前 chunk")
                            break
                    if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                        try:
                            mq.put({'usage': msg.usage_metadata}, timeout=5)
                        except Full:
                            break
            try:
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
            except Exception:
                pass
        except Exception as e:
            print(f"[TTS] LLM 流式输出异常: {e}")
            raise


    async def tts_receiver(self, mq, ws, cancel):
        try:
            async for msg in ws:
                if cancel.is_set():
                    break
                if isinstance(msg, bytes):
                    try:
                        mq.put({'audio': base64.b64encode(msg).decode('utf-8')}, timeout=5)
                    except Full:
                        break
                else:
                    data = json.loads(msg)
                    event = data['header']['event']
                    if event in ['task-finished', 'task-failed']:
                        break
        except Exception as e:
            print(f"[TTS] 音频接收异常，跳过音频: {e}")


    async def run_tts_tasks(self, app, inputs, mq, speaker, cancel):
        if cancel.is_set():
            return
        try:
            task_id = uuid.uuid4().hex
            api_key = os.getenv('API_KEY')
            wss_url = os.getenv('WSS_URL')
            headers = {
                "Authorization": f"Bearer {api_key}"
            }
            async with websockets.connect(wss_url, additional_headers=headers,
                                          open_timeout=10, close_timeout=5, ping_timeout=20) as ws:
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
                            "voice": speaker,
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
                    self.tts_sender(app, inputs, mq, ws, task_id, cancel),
                    self.tts_receiver(mq, ws, cancel),
                )
        except Exception as e:
            if cancel.is_set():
                return
            print(f"[TTS] 连接失败，降级为纯文本流: {e}")
            await self._text_only_stream(app, inputs, mq, cancel)

    async def _text_only_stream(self, app, inputs, mq, cancel):
        """TTS 不可用时的降级方案：只输出文本，不合成语音"""
        async for msg, metadata in app.astream(inputs, stream_mode="messages"):
            if cancel.is_set():
                break
            if isinstance(msg, BaseMessageChunk):
                if msg.content:
                    try:
                        mq.put({'content': msg.content}, timeout=5)
                    except Full:
                        break
                if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                    try:
                        mq.put({'usage': msg.usage_metadata}, timeout=5)
                    except Full:
                        break


    def work(self, app, inputs, mq, speaker, cancel):
        try:
            asyncio.run(self.run_tts_tasks(app, inputs, mq, speaker, cancel))
        except Exception as e:
            print(f"[Work] 工作线程异常: {e}")
            import traceback
            traceback.print_exc()
            try:
                mq.put({'content': '抱歉，处理过程中遇到了问题，请稍后重试。'}, timeout=5)
            except Full:
                pass
        finally:
            try:
                mq.put_nowait(None)
            except Full:
                pass


    def event_stream(self, app, inputs, friend, message):
        cancel = threading.Event()
        mq = Queue(maxsize=100)
        thread = threading.Thread(
            target=self.work,
            args=(app, inputs, mq, friend.character.speaker, cancel),
            daemon=True,
        )
        thread.start()

        full_output = ''
        full_usage = {}
        try:
            while True:
                try:
                    msg = mq.get(timeout=30)
                except Exception:
                    break
                if not msg:
                    break
                if msg.get('content', None):
                    full_output += msg['content']
                    yield f'data: {json.dumps({'content': msg['content']}, ensure_ascii=False)}\n\n'
                if msg.get('audio', None):
                    yield f'data: {json.dumps({'audio': msg['audio']}, ensure_ascii=False)}\n\n'
                if msg.get('usage', None):
                    full_usage = msg['usage']
        except Exception:
            pass
        finally:
            cancel.set()

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
