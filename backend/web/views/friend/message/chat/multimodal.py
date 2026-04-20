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
from langchain_core.messages import BaseMessageChunk

from web.models.friend import Friend, Message, SystemPrompt
from web.views.friend.message.chat.graph import ChatGraph
from web.views.friend.message.memory.update import update_memory
from web.utils.token_cache import TokenCache
from web.utils.prompt_template import PromptTemplateManager
from web.mcp.init_tools import get_global_registry


class SSERenderer(BaseRenderer):
    media_type = 'text/event-stream'
    format = 'txt'
    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


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
            print(f"[Multimodal] 收到请求: {request.data}")
            print(f"[Multimodal] 图片文件: {request.FILES.get('image')}")

            friend_id = request.data.get('friend_id')
            message = request.data.get('message', '').strip()
            image_file = request.FILES.get('image')

            if not friend_id or (not message and not image_file):
                print(f"[Multimodal] 参数验证失败: friend_id={friend_id}, message={message}, image_file={image_file}")
                return Response({
                    'error': 'friend_id、message或image至少需要提供一项'
                }, status=400)

            # 验证好友关系
            friends = Friend.objects.filter(pk=friend_id, me__user=request.user)
            if not friends.exists():
                print(f"[Multimodal] 好友不存在: friend_id={friend_id}")
                return Response({
                    'error': '好友不存在'
                }, status=404)

            friend = friends.first()
            print(f"[Multimodal] 找到好友: {friend}")

            # 处理图片
            image_url = None
            image_caption = None
            image_analysis = None

            if image_file:
                print(f"[Multimodal] 开始处理图片: {image_file.name}")
                # 保存图片
                image_url, image_analysis = self._save_and_analyze_image(image_file, friend)
                # 修复：MCP工具返回的是'analysis'字段，不是'description'
                image_caption = image_analysis.get('analysis', '') if image_analysis else ''
                print(f"[Multimodal] 图片处理完成: url={image_url}, caption={image_caption[:50] if image_caption else 'None'}...")

            # 准备聊天输入
            user_message = message or f"[图片] {image_caption}" if image_caption else "[图片]"
            print(f"[Multimodal] 用户消息: {user_message}")

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
        from django.utils.timezone import now

        print(f"[Image] 开始保存和分析图片: {image_file.name}, 大小: {image_file.size}")

        # 创建临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(image_file.name)[1]) as tmp_file:
            for chunk in image_file.chunks():
                tmp_file.write(chunk)
            tmp_file_path = tmp_file.name

        print(f"[Image] 临时文件创建: {tmp_file_path}")

        try:
            # 保存图片到media目录
            upload_dir = os.path.join('media', 'images', str(friend.id))
            os.makedirs(upload_dir, exist_ok=True)
            print(f"[Image] 上传目录: {upload_dir}")

            filename = f"{uuid.uuid4().hex}_{image_file.name}"
            file_path = os.path.join(upload_dir, filename)

            with open(tmp_file_path, 'rb') as src, open(file_path, 'wb') as dst:
                dst.write(src.read())

            image_url = f"/media/images/{friend.id}/{filename}"
            print(f"[Image] 图片保存成功: {file_path}, URL: {image_url}")

            # 使用MCP工具分析图片（使用同步调用）
            try:
                print(f"[Image] 开始调用MCP工具分析图片...")
                analysis_result = self.mcp_registry.call_tool_sync("image_analysis", {
                    "image_path": tmp_file_path
                })
                print(f"[Image] MCP工具返回结果: {analysis_result}")

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
            # 删除临时文件
            if os.path.exists(tmp_file_path):
                os.remove(tmp_file_path)
                print(f"[Image] 临时文件已删除")

    def event_stream(self, friend, user_message, image_url, image_caption, image_analysis):
        """生成流式响应"""
        print(f"[EventStream] 开始生成流式响应")

        from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

        # 构建输入消息
        messages = [HumanMessage(user_message)]
        print(f"[EventStream] 初始消息: {user_message}")

        # 添加图片分析结果到系统提示
        if image_analysis:
            analysis_text = image_analysis.get('analysis', '')
            if analysis_text:
                image_prompt = f"用户发送了一张图片，分析如下：{analysis_text}\n\n请根据这个图片内容来回答用户的问题。"
                messages.insert(0, SystemMessage(image_prompt))
                print(f"[EventStream] 添加图片分析提示")

        # 添加角色系统提示（使用模板隔离）
        image_analysis_text = image_analysis.get('analysis', '') if image_analysis else ""
        prompt_data = PromptTemplateManager.create_system_prompt(
            friend=friend,
            user_message=user_message,
            image_analysis=image_analysis_text
        )

        messages.insert(0, SystemMessage(content=prompt_data['system_instructions']))
        print(f"[EventStream] 使用模板隔离添加系统提示")

        # 添加最近消息历史
        recent_messages = list(Message.objects.filter(friend=friend).order_by('-id')[:10])
        recent_messages.reverse()

        for m in recent_messages:
            messages.append(HumanMessage(m.user_message))
            messages.append(AIMessage(m.output))

        print(f"[EventStream] 消息历史数量: {len(recent_messages)}")

        inputs = {'messages': messages}

        # 创建聊天图
        app = ChatGraph.create_app()
        print(f"[EventStream] 创建聊天图")

        # 使用work方法运行TTS任务
        mq = Queue()
        print(f"[EventStream] 创建消息队列")

        thread = threading.Thread(target=self.work, args=(app, inputs, mq))
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
        self._save_message(friend, user_message, full_output, image_url, image_caption, image_analysis)

    async def tts_sender(self, app, inputs, mq, ws, task_id):
        print(f"[TTSSender] 开始发送消息")
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
                        print(f"[TTSSender] 发送内容: {content[:20]}...")
                    if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                        mq.put_nowait({'usage': msg.usage_metadata})

            print(f"[TTSSender] 发送完成，发送结束信号")
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

    async def run_tts_tasks(self, app, inputs, mq):
        print(f"[TTS] 开始TTS任务")
        task_id = uuid.uuid4().hex
        api_key = os.getenv('API_KEY')
        wss_url = os.getenv('WSS_URL')
        print(f"[TTS] WSS URL: {wss_url}")

        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        try:
            async with websockets.connect(wss_url, additional_headers=headers) as ws:
                print(f"[TTS] WebSocket连接成功")

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
                        print(f"[TTS] 任务启动成功")
                        break

                print(f"[TTS] 开始并行执行发送和接收")
                await asyncio.gather(
                    self.tts_sender(app, inputs, mq, ws, task_id),
                    self.tts_receiver(mq, ws),
                )
                print(f"[TTS] TTS任务完成")

        except Exception as e:
            print(f"[TTS] TTS任务异常: {e}")
            import traceback
            traceback.print_exc()
            raise

    def work(self, app, inputs, mq):
        print(f"[Work] 开始执行工作线程")
        try:
            asyncio.run(self.run_tts_tasks(app, inputs, mq))
            print(f"[Work] 工作线程完成")
        except Exception as e:
            print(f"[Work] 工作线程异常: {e}")
            import traceback
            traceback.print_exc()
            mq.put({'content': f"处理过程中出现了错误：{str(e)}"})
        finally:
            mq.put_nowait(None)
            print(f"[Work] 工作线程结束")

    def _save_message(self, friend, user_message, ai_output, image_url, image_caption, image_analysis):
        """保存消息到数据库"""
        try:
            # 估算token数
            input_tokens = TokenCache.estimate_tokens(user_message)
            output_tokens = TokenCache.estimate_tokens(ai_output)
            total_tokens = input_tokens + output_tokens

            # 构建输入消息JSON
            input_data = {
                "user_message": user_message,
                "image_url": image_url,
                "image_caption": image_caption,
                "image_analysis": image_analysis
            }

            # 保存消息
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

            # 定期更新记忆
            if Message.objects.filter(friend=friend).count() % 5 == 0:
                update_memory(friend)

        except Exception as e:
            print(f"保存消息失败: {e}")
