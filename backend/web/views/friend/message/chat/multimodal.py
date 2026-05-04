"""
多模态聊天视图
支持文本和图片的混合对话
"""
import os
import uuid
import json
import asyncio
import threading
import base64
import websockets
from queue import Queue
from django.http import StreamingHttpResponse
from rest_framework.renderers import BaseRenderer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from langchain_core.messages import BaseMessageChunk, HumanMessage, SystemMessage, AIMessage

from web.models.friend import Friend, Message
from web.views.friend.message.chat.graph import ChatGraph
from web.views.friend.message.memory.update import update_memory
from web.utils.token_cache import TokenCache
from web.utils.context_builder import ContextBuilder, should_update_summary, update_conversation_summary
from web.mcp.init_tools import get_global_registry


class SSERenderer(BaseRenderer):
    media_type = 'text/event-stream'
    format = 'txt'
    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


# 记忆更新触发频率
MEMORY_UPDATE_INTERVAL = 5


class MultiModalChatView(APIView):
    """多模态聊天视图"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    renderer_classes = [SSERenderer]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mcp_registry = get_global_registry()

    def post(self, request):
        """处理多模态消息"""
        try:
            friend_id = request.data.get('friend_id')
            message = request.data.get('message', '').strip()
            image_file = request.FILES.get('image')

            if not friend_id or (not message and not image_file):
                return Response({
                    'error': 'friend_id、message或image至少需要提供一项'
                }, status=400)

            friends = Friend.objects.filter(pk=friend_id, me__user=request.user)
            if not friends.exists():
                return Response({
                    'error': '好友不存在'
                }, status=404)

            friend = friends.first()

            # 处理图片
            image_url = None
            image_caption = None
            image_analysis = None

            if image_file:
                image_url, image_analysis = self._save_and_analyze_image(image_file, friend)
                image_caption = image_analysis.get('analysis', '') if image_analysis else ''

            # 准备聊天输入
            user_message = message or f"[图片] {image_caption}" if image_caption else "[图片]"

            # 流式响应生成器
            response = StreamingHttpResponse(
                self.event_stream(friend, user_message, image_url, image_caption, image_analysis),
                content_type='text/event-stream',
            )
            response['Cache-Control'] = 'no-cache'
            response['X-Accel-Buffering'] = 'no'
            return response

        except Exception as e:
            import traceback
            print(f"[Multimodal] 处理异常: {str(e)}")
            traceback.print_exc()
            return Response({
                'error': f'处理失败: {str(e)}'
            }, status=500)

    def _save_and_analyze_image(self, image_file, friend):
        """保存图片并分析"""
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(image_file.name)[1]) as tmp_file:
            for chunk in image_file.chunks():
                tmp_file.write(chunk)
            tmp_file_path = tmp_file.name

        try:
            upload_dir = os.path.join('media', 'images', str(friend.id))
            os.makedirs(upload_dir, exist_ok=True)

            filename = f"{uuid.uuid4().hex}_{image_file.name}"
            file_path = os.path.join(upload_dir, filename)

            with open(tmp_file_path, 'rb') as src, open(file_path, 'wb') as dst:
                dst.write(src.read())

            image_url = f"/media/images/{friend.id}/{filename}"

            try:
                analysis_result = self.mcp_registry.call_tool_sync("image_analysis", {
                    "image_path": tmp_file_path
                })

                if analysis_result.get('success', False):
                    image_analysis = analysis_result
                else:
                    image_analysis = None
            except Exception as e:
                print(f"[Image] 图片分析失败: {e}")
                import traceback
                traceback.print_exc()
                image_analysis = None

            return image_url, image_analysis

        except Exception as e:
            print(f"[Image] 图片保存失败: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            if os.path.exists(tmp_file_path):
                os.remove(tmp_file_path)

    def event_stream(self, friend, user_message, image_url, image_caption, image_analysis):
        """生成流式响应"""
        # 使用 ContextBuilder 构建上下文
        image_analysis_text = image_analysis.get('analysis', '') if image_analysis else ""
        builder = ContextBuilder(
            friend=friend,
            current_message=user_message,
            image_analysis=image_analysis_text
        )
        messages = builder.build()

        # 如果有图片分析，在系统提示词之后插入图片描述
        if image_analysis_text:
            image_prompt = f"用户发送了一张图片，分析如下：{image_analysis_text}\n\n请根据这个图片内容来回答用户的问题。"
            # 插入到系统提示词之后（位置 1）
            messages.insert(1, SystemMessage(content=image_prompt))

        inputs = {'messages': messages}

        # 创建聊天图
        app = ChatGraph.create_app()

        mq = Queue()
        thread = threading.Thread(target=self.work, args=(app, inputs, mq, friend.character.speaker))
        thread.start()

        full_output = ''
        full_usage = {}
        while True:
            msg = mq.get()
            if msg is None:
                break

            if msg.get('content'):
                full_output += msg['content']
                yield f'data: {json.dumps({"content": msg["content"]}, ensure_ascii=False)}\n\n'

            if msg.get('audio'):
                yield f'data: {json.dumps({"audio": msg["audio"]}, ensure_ascii=False)}\n\n'

            if msg.get('usage'):
                full_usage = msg['usage']

        yield 'data: [DONE]\n\n'

        # 保存消息到数据库
        self._save_message(friend, user_message, full_output, image_url, image_caption, image_analysis, full_usage)

    async def tts_sender(self, app, inputs, mq, ws, task_id):
        try:
            async for msg, metadata in app.astream(inputs, stream_mode="messages"):
                if isinstance(msg, BaseMessageChunk):
                    if msg.content:
                        content = msg.content
                        await ws.send(json.dumps({
                            "header": {
                                "action": "continue-task",
                                "task_id": task_id,
                                "streaming": "duplex"
                            },
                            "payload": {
                                "input": {
                                    "text": content,
                                }
                            }
                        }))
                        mq.put_nowait({'content': content})
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
        except Exception as e:
            print(f"[TTSSender] 发送异常: {e}")
            import traceback
            traceback.print_exc()
            raise

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

    async def run_tts_tasks(self, app, inputs, mq, speaker):
        task_id = uuid.uuid4().hex
        api_key = os.getenv('API_KEY')
        wss_url = os.getenv('WSS_URL')

        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        try:
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
                    self.tts_sender(app, inputs, mq, ws, task_id),
                    self.tts_receiver(mq, ws),
                )

        except Exception as e:
            print(f"[TTS] TTS任务异常: {e}")
            import traceback
            traceback.print_exc()
            raise

    def work(self, app, inputs, mq, speaker):
        try:
            asyncio.run(self.run_tts_tasks(app, inputs, mq, speaker))
        except Exception as e:
            print(f"[Work] 工作线程异常: {e}")
            import traceback
            traceback.print_exc()
            mq.put({'content': f"处理过程中出现了错误：{str(e)}"})
        finally:
            mq.put_nowait(None)

    def _save_message(self, friend, user_message, ai_output, image_url, image_caption, image_analysis, full_usage=None):
        """保存消息到数据库"""
        try:
            full_usage = full_usage or {}

            # 优先使用 LLM 返回的实际 token 用量
            input_tokens = full_usage.get('input_tokens', 0) or TokenCache.estimate_tokens(user_message)
            output_tokens = full_usage.get('output_tokens', 0) or TokenCache.estimate_tokens(ai_output)
            total_tokens = input_tokens + output_tokens

            input_data = {
                "user_message": user_message,
                "image_url": image_url,
                "image_caption": image_caption,
                "image_analysis": image_analysis
            }

            Message.objects.create(
                friend=friend,
                user_message=user_message[:500],
                input=json.dumps(input_data, ensure_ascii=False)[:10000],
                output=ai_output[:500],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                image_url=image_url,
                image_caption=image_caption,
                image_analysis=image_analysis
            )

            # 每隔 N 条消息更新长期记忆
            msg_count = Message.objects.filter(friend=friend).count()
            if msg_count % MEMORY_UPDATE_INTERVAL == 0:
                update_memory(friend)

            # 检查是否需要更新对话摘要
            if should_update_summary(friend):
                update_conversation_summary(friend)

        except Exception as e:
            print(f"保存消息失败: {e}")
