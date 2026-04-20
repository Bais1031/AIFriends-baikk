"""
Prompt 模板隔离工具类
实现数据和指令分离，防止 prompt 注入攻击
"""
import json
import re
from typing import Dict, Any, Optional
from django.core.exceptions import ValidationError
from django.utils.html import escape


class PromptTemplateEngine:
    """安全的模板渲染引擎"""

    # 允许的上下文数据字段
    ALLOWED_CONTEXT_FIELDS = {
        'character_profile', 'memory', 'recent_messages',
        'user_message', 'image_analysis'
    }

    # 危险指令模式
    DANGEROUS_PATTERNS = [
        r'IGNORE\s+PREVIOUS\s+INSTRUCTIONS',
        r'DISREGARD\s+ALL\s+PRIOR\s+COMMANDS',
        r'OVERRIDE\s+SYSTEM\s+PROMPT',
        r'SET\s+SYSTEM\s+ROLE\s+TO',
        r'YOU\s+ARE\s+NOW',
        r'BECOME',
        r'ACT\s+AS',
        r'PROMPT\s+INJECTION',
        r'SYSTEM\s+:',
        r'ROLE\s*:',
    ]

    @classmethod
    def render_template(cls, template: str, context: Dict[str, Any]) -> str:
        """
        安全渲染模板

        Args:
            template: 模板字符串，支持 {{ field }} 语法
            context: 上下文数据

        Returns:
            渲染后的字符串

        Raises:
            ValidationError: 包含危险模式或无效字段
        """
        # 验证上下文数据
        cls._validate_context(context)

        # 转义上下文数据
        escaped_context = cls._escape_context(context)

        # 渲染模板
        try:
            result = template
            for key, value in escaped_context.items():
                placeholder = f"{{{{ {key} }}}}"
                result = result.replace(placeholder, str(value))

            # 验证渲染结果
            cls._validate_rendered_result(result)

            return result

        except Exception as e:
            raise ValidationError(f"模板渲染失败: {str(e)}")

    @classmethod
    def _validate_context(cls, context: Dict[str, Any]) -> None:
        """验证上下文数据"""
        if not isinstance(context, dict):
            raise ValidationError("上下文必须是字典类型")

        # 检查字段是否允许
        for field in context.keys():
            if field not in cls.ALLOWED_CONTEXT_FIELDS:
                raise ValidationError(f"不允许的上下文字段: {field}")

        # 检查危险模式
        for field, value in context.items():
            if isinstance(value, str):
                cls._check_dangerous_patterns(value, field)

    @classmethod
    def _check_dangerous_patterns(cls, text: str, field_name: str) -> None:
        """检查文本中是否包含危险模式"""
        text_upper = text.upper()
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, text_upper, re.IGNORECASE):
                raise ValidationError(
                    f"字段 '{field_name}' 包含潜在的危险模式: {pattern}"
                )

    @classmethod
    def _escape_context(cls, context: Dict[str, Any]) -> Dict[str, Any]:
        """转义上下文数据"""
        escaped = {}
        for key, value in context.items():
            if isinstance(value, str):
                # HTML 转义
                escaped[key] = escape(value)
                # 额外的安全转义
                escaped[key] = cls._safe_escape(escaped[key])
            else:
                escaped[key] = value
        return escaped

    @classmethod
    def _safe_escape(cls, text: str) -> str:
        """额外的安全转义"""
        # 替换潜在的注入字符
        text = text.replace('{', '&#123;')
        text = text.replace('}', '&#125;')
        text = text.replace('[', '&#91;')
        text = text.replace(']', '&#93;')
        # 限制长度
        if len(text) > 10000:
            text = text[:10000] + '...'
        return text

    @classmethod
    def _validate_rendered_result(cls, result: str) -> None:
        """验证渲染结果"""
        # 检查是否包含未替换的占位符
        if '{{' in result or '}}' in result:
            raise ValidationError("模板包含未替换的占位符")

        # 检查最终的危险模式
        cls._check_dangerous_patterns(result, "rendered_result")


class PromptTemplateManager:
    """提示词模板管理器"""

    @classmethod
    def create_system_prompt(cls, friend, user_message: str = "",
                          image_analysis: str = "") -> Dict[str, Any]:
        """
        创建结构化的系统提示词

        Args:
            friend: Friend 对象
            user_message: 用户当前消息
            image_analysis: 图片分析结果

        Returns:
            包含系统指令和上下文数据的字典
        """
        # 获取基础系统提示词
        system_prompts = list(SystemPrompt.objects.filter(title='回复').order_by('order_number'))

        # 构建模板
        template_parts = []
        for sp in system_prompts:
            template_parts.append(sp.prompt)

        template = '\n'.join(template_parts)

        # 构建上下文数据
        context = {
            'character_profile': friend.character.profile,
            'memory': friend.memory,
            'user_message': user_message,
            'image_analysis': image_analysis or ""
        }

        # 渲染模板
        rendered_prompt = PromptTemplateEngine.render_template(template, context)

        return {
            'system_instructions': rendered_prompt,
            'context_data': context,
            'template_used': template
        }

    @classmethod
    def create_memory_update_prompt(cls, friend) -> Dict[str, Any]:
        """创建记忆更新提示词"""
        system_prompts = list(SystemPrompt.objects.filter(title='记忆').order_by('order_number'))

        template = '\n'.join([sp.prompt for sp in system_prompts])

        context = {
            'character_profile': friend.character.profile,
            'memory': friend.memory
        }

        rendered_prompt = PromptTemplateEngine.render_template(template, context)

        return {
            'system_instructions': rendered_prompt,
            'context_data': context,
            'template_used': template
        }