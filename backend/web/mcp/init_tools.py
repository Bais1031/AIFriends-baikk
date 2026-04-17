"""
初始化MCP工具
注册所有可用的工具
"""
import os
from web.mcp.tool_registry import MCPToolRegistry
from web.mcp.tools.image_tools import ImageAnalysisTools


def register_image_tools(tool_registry: MCPToolRegistry):
    """注册图像相关工具"""
    image_tools = ImageAnalysisTools()

    # 注册图像分析工具
    tool_registry.register_tool(
        "image_analysis",
        "全面分析图片内容，包括场景、物体、情感等",
        image_tools.analyze_image_vision
    )

    # 注册OCR文字提取工具
    tool_registry.register_tool(
        "ocr_extraction",
        "从图片中提取文字内容",
        image_tools.extract_text_from_image
    )

    # 注册图片描述生成工具
    tool_registry.register_tool(
        "generate_description",
        "为图片生成描述，支持多种风格（brief/detailed/poetic）",
        image_tools.generate_image_description
    )

    # 注册图片元数据获取工具
    tool_registry.register_tool(
        "image_metadata",
        "获取图片的基本元数据（尺寸、格式等）",
        image_tools.get_image_metadata
    )

    # 注册图片分类工具
    tool_registry.register_tool(
        "classify_image",
        "对图片内容进行分类",
        image_tools.classify_image_content
    )

    # 注册缩略图生成工具
    tool_registry.register_tool(
        "create_thumbnail",
        "创建图片缩略图",
        image_tools.create_thumbnail
    )


def get_tool_registry() -> MCPToolRegistry:
    """获取并初始化工具注册表"""
    registry = MCPToolRegistry()

    # 注册所有工具
    register_image_tools(registry)

    print(f"[MCP] 已注册 {len(registry.list_tools())} 个工具")
    for tool_name in registry.list_tools():
        print(f"  - {tool_name}")

    return registry


# 全局工具注册表实例
_tool_registry = None


def get_global_registry() -> MCPToolRegistry:
    """获取全局工具注册表"""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = get_tool_registry()
    return _tool_registry