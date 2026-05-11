# 清理仿 MCP + 重构本地工具 + 串联 OCR/metadata

## 背景

项目中存在两套独立的工具系统：

1. **真 MCP**：`MCPClientManager`（client/mcp_client.py）+ `FastMCP` Server（server/web_search_server.py），走 SSE 协议，ChatGraph 通过它动态发现 `web_search` 工具
2. **仿 MCP**：`MCPToolRegistry` + `ImageAnalysisTools`，纯本地 Python 调用，放在 `web/mcp/` 目录下但跟 MCP 协议无关

仿 MCP 的问题：
- **命名误导**：放在 `mcp/` 目录、叫 `MCPToolRegistry`，但跟 MCP 协议无关，面试时可能被质疑对 MCP 协议的理解
- **5/6 死代码**：6 个注册工具中只有 `image_analysis` 被 `MultiModalChatView` 调用，其余 5 个从未被任何代码调用
- **硬编码存根**：`classify_image_content` 永远返回 `["风景", "自然"]`
- **功能重叠**：`generate_image_description` 和 `classify_image_content` 都只是调 `analyze_image_vision` 再做后处理
- **有价值但未激活**：`ocr_extraction`（OCR 文字识别）和 `image_metadata`（图片元数据）有独立能力，但从未被调用

## 改动

### 1. 删 4 个无用/重叠工具 + 1 个未注册方法

从 `ImageAnalysisTools` 类中删除：

| 方法 | 删除原因 |
|---|---|
| `generate_image_description` | 就是调 `analyze_image_vision` 再按风格改写文本，与 `image_analysis` 重叠 |
| `classify_image_content` | 硬编码存根，也调 `analyze_image_vision`，与 `image_analysis` 重叠 |
| `create_thumbnail` | 缩略图生成，AI 聊天场景无使用需求 |
| `detect_objects` | 连注册都没注册，与 `image_analysis` 功能重叠 |

保留 3 个有独立价值的方法：
- `analyze_image_vision` — 场景理解（阿里云 Vision API）
- `extract_text_from_image` — OCR 文字识别（阿里云 OCR API，场景理解和文字识别是不同能力）
- `get_image_metadata` — 图片元数据（本地 PIL，零 API 成本）

### 2. 重构：MCPToolRegistry → LocalToolRegistry

**新建** `backend/web/utils/local_tool_registry.py`

从 `web/mcp/tool_registry.py` 搬运并：
- 类名 `MCPToolRegistry` → `LocalToolRegistry`
- 删掉 `_generate_schema`（stub 实现，返回空 schema，无人使用）
- `ToolInfo` 删掉 `schema` 字段
- 日志前缀 `[MCP]` → `[LocalTool]`

### 3. 重构：image_tools 迁移到 web/utils/

**新建** `backend/web/utils/image_tools.py`

从 `web/mcp/tools/image_tools.py` 搬运并精简：
- 只保留 3 个公开方法 + `_generate_fallback_description` 辅助方法
- 删除 `detect_objects` 及 `object_detect_url` 属性
- 删除 4 个无用方法

**新建** `backend/web/utils/image_tool_init.py`

替代 `web/mcp/init_tools.py`，只注册 3 个工具：

```python
def register_image_tools(registry: LocalToolRegistry):
    image_tools = ImageAnalysisTools()
    registry.register_tool("image_analysis", "全面分析图片内容", image_tools.analyze_image_vision)
    registry.register_tool("ocr_extraction", "从图片中提取文字内容", image_tools.extract_text_from_image)
    registry.register_tool("image_metadata", "获取图片元数据", image_tools.get_image_metadata)
```

### 4. 修 multimodal.py：串联 OCR + metadata

**文件**: `backend/web/views/friend/message/chat/multimodal.py`

#### 4a: 更新 import

```python
# 改动前
from web.mcp.init_tools import get_global_registry

# 改动后
from web.utils.image_tool_init import get_global_registry
```

#### 4b: `_save_and_analyze_image()` 串联调用

改动前：只调 `image_analysis`，OCR 和 metadata 从不调用。

改动后：`image_analysis` 成功后，自动串联 OCR 和 metadata，结果合并到同一个 dict：

```python
if analysis_result.get('success', False):
    # 串联 OCR
    try:
        ocr_result = self.mcp_registry.call_tool_sync("ocr_extraction", {"image_path": tmp_file_path})
        if ocr_result.get('success', False) and ocr_result.get('text', '').strip():
            analysis_result['ocr_text'] = ocr_result['text']
    except Exception as e:
        print(f"[Image] OCR提取失败: {e}")

    # 串联 metadata（零 API 成本）
    try:
        meta_result = self.mcp_registry.call_tool_sync("image_metadata", {"image_path": tmp_file_path})
        if meta_result.get('success', False):
            analysis_result['metadata'] = meta_result['metadata']
    except Exception as e:
        print(f"[Image] 元数据提取失败: {e}")
```

#### 4c: `event_stream()` 合并 OCR 文字到提示词

```python
# 改动前
image_analysis_text = image_analysis.get('analysis', '') if image_analysis else ""

# 改动后
if image_analysis:
    image_analysis_text = image_analysis.get('analysis', '')
    ocr_text = image_analysis.get('ocr_text', '').strip()
    if ocr_text:
        image_analysis_text += f"\n\n图片中包含的文字内容：{ocr_text}"
else:
    image_analysis_text = ""
```

metadata 不传给 LLM（对对话无用），只存在 DB 中供后续分析。

### 5. 清理 web/mcp/ 目录

**删除文件**：
- `web/mcp/tool_registry.py` → 已迁移到 `web/utils/local_tool_registry.py`
- `web/mcp/init_tools.py` → 已迁移到 `web/utils/image_tool_init.py`
- `web/mcp/tools/image_tools.py` → 已迁移到 `web/utils/image_tools.py`
- `web/mcp/tools/__init__.py`
- `web/mcp/tools/` 目录

**更新** `web/mcp/__init__.py`：注释只保留 client + server 说明，注明本地工具已迁移到 `web/utils/`

**保留文件**（真 MCP）：
- `web/mcp/client/mcp_client.py`
- `web/mcp/server/web_search_server.py`

## 改动前后对比

### 目录结构

```
# 改动前
web/mcp/
  __init__.py
  tool_registry.py              ← 仿 MCP
  init_tools.py                 ← 仿 MCP
  tools/
    image_tools.py              ← 仿 MCP（6 个工具，5 个死代码）
  client/
    mcp_client.py               ← 真 MCP
  server/
    web_search_server.py        ← 真 MCP

# 改动后
web/mcp/
  __init__.py                   ← 只含真 MCP 说明
  client/
    mcp_client.py               ← 真 MCP
  server/
    web_search_server.py        ← 真 MCP

web/utils/
  local_tool_registry.py        ← 本地工具注册表
  image_tools.py                ← 3 个工具
  image_tool_init.py            ← 注册入口
```

### 工具数量

| 改动前 | 改动后 |
|---|---|
| 6 个注册 + 1 个未注册 | 3 个注册 |
| 5 个死代码 | 0 个死代码 |
| 1 个硬编码存根 | 0 个存根 |
| OCR 未激活 | OCR 自动串联 |
| metadata 未激活 | metadata 自动串联 |

## 验证

1. 上传图片聊天，确认 `image_analysis` 正常调用，LLM 回复包含图片内容
2. 上传含文字的截图，确认 OCR 结果出现在 LLM 提示词中
3. 上传图片，确认 DB 中 Message 的 `image_analysis` 字段包含 `ocr_text` 和 `metadata`
4. 上传纯风景照（无文字），确认 OCR 失败不影响主流程
5. ChatGraph 的 `web_search` MCP 工具正常工作（不受影响）
6. 确认 `web/mcp/tools/` 目录已删除
