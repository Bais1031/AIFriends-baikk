"""
图片分析工具注册入口
"""
from web.utils.local_tool_registry import LocalToolRegistry
from web.utils.image_tools import ImageAnalysisTools


def register_image_tools(registry: LocalToolRegistry):
    image_tools = ImageAnalysisTools()
    registry.register_tool("image_analysis", "全面分析图片内容", image_tools.analyze_image_vision)
    registry.register_tool("ocr_extraction", "从图片中提取文字内容", image_tools.extract_text_from_image)
    registry.register_tool("image_metadata", "获取图片元数据", image_tools.get_image_metadata)


_registry = None


def get_global_registry() -> LocalToolRegistry:
    global _registry
    if _registry is None:
        _registry = LocalToolRegistry()
        register_image_tools(_registry)
        print(f"[LocalTool] 已注册 {len(_registry.list_tools())} 个工具: {_registry.list_tools()}")
    return _registry
