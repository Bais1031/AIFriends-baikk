"""
图片分析工具集
提供场景理解（Vision API）、OCR 文字识别、图片元数据获取
"""
import os
import base64
import time
from typing import Dict, Any

from PIL import Image
from httpx import AsyncClient
from tenacity import retry, stop_after_attempt, wait_exponential


class ImageAnalysisTools:

    def __init__(self):
        self.api_key = os.getenv("API_KEY")
        self.api_base = os.getenv("API_BASE")
        self.vision_model = "qwen2.5-vl-3b-instruct"

    async def analyze_image_vision(self, image_path: str, prompt: str = "") -> Dict[str, Any]:
        """使用阿里云 OpenAI 兼容模式 + qwen2.5-vl 视觉模型分析图片内容"""
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
                image_base64 = base64.b64encode(image_data).decode()

            import imghdr
            img_format = imghdr.what(image_path)
            if img_format in ('jpeg', 'jpg'):
                mime_type = 'image/jpeg'
            elif img_format == 'png':
                mime_type = 'image/png'
            elif img_format == 'gif':
                mime_type = 'image/gif'
            else:
                mime_type = 'image/jpeg'

            image_url = f"data:{mime_type};base64,{image_base64}"
            user_prompt = prompt or "请详细描述这张图片的内容，包括人物、场景、动作、颜色等关键信息。"

            try:
                description = await self._call_vision_api(image_url, user_prompt)
            except Exception as e:
                print(f"[Vision] API 重试耗尽，使用 fallback: {e}")
                description = await self._generate_fallback_description(image_path)

            return {
                "analysis": description,
                "model": self.vision_model,
                "timestamp": time.time(),
                "success": True
            }

        except Exception as e:
            print(f"[Vision] 图片分析异常: {e}")
            return {
                "error": f"图像分析失败: {str(e)}",
                "success": False
            }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _call_vision_api(self, image_url: str, prompt: str) -> str:
        """调用 Vision API，带重试"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        request_body = {
            "model": self.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
        }
        url = f"{self.api_base}/chat/completions"

        async with AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, json=request_body)
            if response.status_code != 200:
                raise Exception(f"status={response.status_code}, body={response.text[:200]}")
            return response.json()['choices'][0]['message']['content']

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def extract_text_from_image(self, image_path: str) -> Dict[str, Any]:
        """使用阿里云 OCR API 提取图片中的文字"""
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
                image_base64 = base64.b64encode(image_data).decode()

            ocr_url = "https://dashscope.aliyuncs.com/api/v1/services/ocr/ocr-general-text/recognize"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            request = {
                "model": "ocr-general-text-v2",
                "input": {
                    "image": f"data:image/jpeg;base64,{image_base64}"
                }
            }

            async with AsyncClient(timeout=30) as client:
                response = await client.post(
                    ocr_url,
                    headers=headers,
                    json=request
                )

                if response.status_code == 200:
                    result = response.json()
                    if 'output' in result:
                        text_blocks = result['output']['text_blocks']
                        extracted_text = ' '.join([block['text'] for block in text_blocks])

                        return {
                            "text": extracted_text,
                            "blocks_count": len(text_blocks),
                            "language": "zh-CN",
                            "success": True
                        }

            return {
                "text": "",
                "blocks_count": 0,
                "success": True
            }

        except Exception as e:
            print(f"[OCR] 提取失败: {e}")
            return {
                "error": f"OCR提取失败: {str(e)}",
                "success": False
            }

    async def get_image_metadata(self, image_path: str) -> Dict[str, Any]:
        """获取图片元数据（本地 PIL 处理，无 API 调用）"""
        try:
            with Image.open(image_path) as img:
                metadata = {
                    "width": img.width,
                    "height": img.height,
                    "format": img.format,
                    "mode": img.mode,
                    "size": os.path.getsize(image_path),
                    "aspect_ratio": round(img.width / img.height, 2)
                }

                return {
                    "metadata": metadata,
                    "success": True
                }

        except Exception as e:
            return {
                "error": f"无法读取图片元数据: {str(e)}",
                "success": False
            }

    async def _generate_fallback_description(self, image_path: str) -> str:
        """生成备用描述（Vision API 不可用时）"""
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                format_name = img.format or "JPEG"

                description = f"这是一张{format_name}格式的图片，尺寸为{width}x{height}像素"

                if img.mode == 'RGBA':
                    description += "，具有透明背景"

                if width > height * 1.5:
                    description += "，可能是风景照片"
                elif height > width * 1.5:
                    description += "，可能是人物照片"

                return description

        except Exception:
            return "无法读取图片信息"
