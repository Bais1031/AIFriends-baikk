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


class ImageAnalysisTools:

    def __init__(self):
        self.api_key = os.getenv("API_KEY")
        self.api_base = os.getenv("API_BASE")
        self.vision_url = "https://dashscope.aliyuncs.com/api/v1/services/vision/image-recognition/image-description"

    async def analyze_image_vision(self, image_path: str, prompt: str = "") -> Dict[str, Any]:
        """使用阿里云视觉 API 分析图片内容"""
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

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            description_request = {
                "model": "image-description-vision",
                "input": {
                    "image": f"data:{mime_type};base64,{image_base64}"
                }
            }

            async with AsyncClient() as client:
                response = await client.post(
                    self.vision_url,
                    headers=headers,
                    json=description_request
                )

                if response.status_code == 200:
                    result = response.json()
                    if 'output' in result:
                        description = result['output']['text']
                    else:
                        description = "未获取到图像描述"
                else:
                    description = await self._generate_fallback_description(image_path)

            if prompt:
                description += f"\n\n分析要求: {prompt}"

            return {
                "analysis": description,
                "model": "aliyun-vision",
                "timestamp": time.time(),
                "success": True
            }

        except Exception as e:
            return {
                "error": f"图像分析失败: {str(e)}",
                "success": False
            }

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

            async with AsyncClient() as client:
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
