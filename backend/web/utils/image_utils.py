"""
图片处理工具
"""
import os
import uuid
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from PIL import Image
import hashlib


class ImageProcessor:
    """图片处理器"""

    def __init__(self, upload_dir="images"):
        """
        初始化图片处理器

        Args:
            upload_dir: 上传目录，相对于MEDIA_ROOT
        """
        self.upload_dir = upload_dir
        self.media_root = settings.MEDIA_ROOT

    def save_image(self, image_file, friend_id, filename=None):
        """
        保存上传的图片

        Args:
            image_file: 文件对象
            friend_id: 好友ID
            filename: 自定义文件名（可选）

        Returns:
            dict: {
                'url': 图片访问URL,
                'path': 保存路径,
                'filename': 文件名,
                'size': 文件大小
            }
        """
        # 创建目录
        upload_path = os.path.join(self.upload_dir, str(friend_id))
        full_upload_dir = os.path.join(self.media_root, upload_path)
        os.makedirs(full_upload_dir, exist_ok=True)

        # 生成文件名
        if not filename:
            ext = os.path.splitext(image_file.name)[1]
            filename = f"{uuid.uuid4().hex}{ext}"

        # 完整保存路径
        save_path = os.path.join(full_upload_dir, filename)

        # 保存文件
        with open(save_path, 'wb') as f:
            for chunk in image_file.chunks():
                f.write(chunk)

        # 计算文件大小
        file_size = os.path.getsize(save_path)

        # 返回信息
        url = f"/{os.path.join(settings.MEDIA_URL, upload_path, filename)}"
        return {
            'url': url,
            'path': save_path,
            'filename': filename,
            'size': file_size,
            'relative_path': os.path.join(upload_path, filename)
        }

    def create_thumbnail(self, image_path, size=(200, 200)):
        """
        创建缩略图

        Args:
            image_path: 原图片路径
            size: 缩略图尺寸

        Returns:
            dict: {
                'thumbnail_url': 缩略图URL,
                'size': 缩略图尺寸,
                'save_path': 保存路径
            }
        """
        try:
            # 读取原图片
            with Image.open(image_path) as img:
                # 转换为RGB模式（处理RGBA等）
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')

                # 创建缩略图
                img.thumbnail(size)

                # 生成缩略图文件名
                base_name = os.path.splitext(os.path.basename(image_path))[0]
                thumb_filename = f"{base_name}_thumb.jpg"
                thumb_dir = os.path.dirname(image_path)
                thumb_path = os.path.join(thumb_dir, thumb_filename)

                # 保存缩略图
                img.save(thumb_path, 'JPEG', quality=85)

                # 计算相对路径
                relative_path = os.path.relpath(thumb_path, self.media_root)
                thumbnail_url = f"/{os.path.join(settings.MEDIA_URL, relative_path)}"

                return {
                    'thumbnail_url': thumbnail_url,
                    'size': size,
                    'save_path': thumb_path,
                    'relative_path': relative_path
                }

        except Exception as e:
            raise Exception(f"创建缩略图失败: {str(e)}")

    def get_image_hash(self, image_path):
        """
        获取图片哈希值（用于去重）

        Args:
            image_path: 图片路径

        Returns:
            str: 图片哈希值
        """
        with open(image_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def validate_image(self, image_file):
        """
        验证图片文件

        Args:
            image_file: 文件对象

        Returns:
            tuple: (is_valid, error_message)
        """
        # 检查文件大小
        max_size = 10 * 1024 * 1024  # 10MB
        if image_file.size > max_size:
            return False, "文件大小不能超过10MB"

        # 检查文件类型
        valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        ext = os.path.splitext(image_file.name)[1].lower()
        if ext not in valid_extensions:
            return False, "只支持JPG、PNG、GIF、WebP格式的图片"

        # 检查图片是否有效
        try:
            Image.open(image_file)
            return True, None
        except Exception as e:
            return False, f"图片格式无效: {str(e)}"

    def get_image_metadata(self, image_path):
        """
        获取图片元数据

        Args:
            image_path: 图片路径

        Returns:
            dict: 图片元数据
        """
        try:
            with Image.open(image_path) as img:
                return {
                    'width': img.width,
                    'height': img.height,
                    'format': img.format,
                    'mode': img.mode,
                    'size': os.path.getsize(image_path)
                }
        except Exception as e:
            return {
                'error': f"无法读取图片信息: {str(e)}"
            }

    def delete_image(self, image_path):
        """
        删除图片

        Args:
            image_path: 图片路径
        """
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            print(f"删除图片失败: {str(e)}")

    def compress_image(self, image_path, quality=85, max_size=(1024, 1024)):
        """
        压缩图片

        Args:
            image_path: 图片路径
            quality: 压缩质量 (1-100)
            max_size: 最大尺寸

        Returns:
            dict: {
                'compressed_path': 压缩后的路径,
                'original_size': 原始大小,
                'compressed_size': 压缩后大小,
                'compression_ratio': 压缩率
            }
        """
        try:
            with Image.open(image_path) as img:
                # 转换为RGB
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')

                # 调整大小
                if img.width > max_size[0] or img.height > max_size[1]:
                    img.thumbnail(max_size)

                # 生成压缩后的文件名
                base_name = os.path.splitext(os.path.basename(image_path))[0]
                compressed_filename = f"{base_name}_compressed.jpg"
                compressed_dir = os.path.dirname(image_path)
                compressed_path = os.path.join(compressed_dir, compressed_filename)

                # 保存压缩图片
                img.save(compressed_path, 'JPEG', quality=quality)

                # 计算压缩率
                original_size = os.path.getsize(image_path)
                compressed_size = os.path.getsize(compressed_path)
                compression_ratio = (1 - compressed_size / original_size) * 100

                return {
                    'compressed_path': compressed_path,
                    'original_size': original_size,
                    'compressed_size': compressed_size,
                    'compression_ratio': compression_ratio
                }

        except Exception as e:
            raise Exception(f"压缩图片失败: {str(e)}")


def get_image_processor(upload_dir="images"):
    """
    获取图片处理器实例

    Args:
        upload_dir: 上传目录
    """
    return ImageProcessor(upload_dir)