## 图片聊天与 MCP 工具集成

### 架构概览

图片聊天采用 **"MCP 工具注册中心 + 阿里云视觉 API + 上下文注入"** 的架构：

```
用户上传图片 → 保存到本地 → MCP 工具调用阿里云视觉API分析 → 分析结果注入上下文 → LLM 结合图片内容回复
```

与标准 MCP 协议（stdio/SSE 传输）不同，本项目实现了 **进程内工具注册中心**（MCPToolRegistry），在 Django 进程内统一管理和调用工具。

---

### 核心模块

| 模块 | 文件 | 职责 |
|---|---|---|
| 多模态聊天视图 | `web/views/friend/message/chat/multimodal.py` | 接收图片上传、编排分析流程、构建上下文、流式返回 |
| 工具注册中心 | `web/mcp/tool_registry.py` | 注册/调用工具，记录使用统计 |
| 工具初始化 | `web/mcp/init_tools.py` | 注册 6 个图片分析工具，维护全局单例 |
| 图片分析工具 | `web/mcp/tools/image_tools.py` | 调用阿里云视觉/OCR API 的具体实现 |

---

### MCPToolRegistry 工具注册中心

自定义的进程内工具注册中心，核心能力：

- **工具注册**：`register_tool(name, description, implementation)` — 存储 `ToolInfo`（名称、描述、JSON Schema、Python 可调用对象）
- **异步调用**：`call_tool(name, params)` — await 调用注册的异步方法
- **同步调用**：`call_tool_sync(name, params)` — 处理 asyncio 事件循环兼容：已有循环时通过 `ThreadPoolExecutor` 在新线程中运行，否则直接 `asyncio.run`
- **使用统计**：每个工具记录 `usage_count` 和 `total_time`

采用全局单例模式：`get_global_registry()` 首次调用时初始化并缓存，后续复用同一实例。

---

### 注册的工具

| 工具名 | 功能 | 实现方法 | 调用方式 |
|---|---|---|---|
| `image_analysis` | 全面分析图片内容（场景、物体、情感） | `analyze_image_vision` | 阿里云 image-description-vision API |
| `ocr_extraction` | 从图片提取文字 | `extract_text_from_image` | 阿里云 ocr-general-text-v2 API |
| `generate_description` | 生成图片描述（brief/detailed/poetic） | `generate_image_description` | 复用 analyze_image_vision + 风格处理 |
| `image_metadata` | 获取图片元数据（尺寸、格式） | `get_image_metadata` | 本地 PIL 读取 |
| `classify_image` | 图片内容分类 | `classify_image_content` | 复用 analyze_image_vision + 分类提示词 |
| `create_thumbnail` | 创建缩略图 | `create_thumbnail` | 本地 PIL 缩放 + base64 |

**当前聊天流程中只调用了 `image_analysis`**，其余工具已注册但未在对话链路中使用。

---

### 图片分析核心流程

`ImageAnalysisTools.analyze_image_vision` 的实现：

```
1. 读取图片文件 → base64 编码
2. 检测 MIME 类型（jpeg/png/gif，默认 jpeg）
3. POST 请求阿里云 DashScope 视觉 API：
   - URL: https://dashscope.aliyuncs.com/api/v1/services/vision/image-recognition/image-description
   - Model: image-description-vision
   - Input: data:{mime_type};base64,{image_base64}
4. 提取 result['output']['text'] 作为图片描述
5. API 失败时回退到 _generate_fallback_description：
   用 PIL 读取尺寸/格式，根据宽高比猜测类型（宽 > 高×1.5 → 风景，高 > 宽×1.5 → 人物）
6. 返回 {"analysis": 描述文本, "model": "aliyun-vision", "success": True}
```

---

### 完整数据流

```
客户端 POST (multipart/form-data: friend_id, message, image)
    │
    ▼
MultiModalChatView.post()
    ├── 校验: friend_id + (message 或 image) 至少一个
    ├── 查询 Friend 对象（鉴权）
    │
    ├── [有图片] _save_and_analyze_image()
    │       ├── 写入临时文件
    │       ├── 复制到 media/images/{friend_id}/{uuid}_{filename}
    │       ├── image_url = "/media/images/{friend_id}/{filename}"
    │       ├── mcp_registry.call_tool_sync("image_analysis", {"image_path": tmp_path})
    │       │       └── ImageAnalysisTools.analyze_image_vision()
    │       │           └── 阿里云视觉 API → 图片描述文本
    │       ├── image_analysis = 返回结果 dict
    │       ├── image_caption = image_analysis['analysis']
    │       └── 删除临时文件
    │
    ├── 组合用户消息: message 或 "[图片] {image_caption}" 或 "[图片]"
    │
    ▼
event_stream()
    ├── ContextBuilder(friend, user_message, image_analysis=分析文本)
    │       └── build() 构建消息列表:
    │           [0] SystemMessage（角色设定 + {{ image_analysis }} 模板渲染）
    │           [1] SystemMessage（语义记忆层）
    │           [2] SystemMessage（对话摘要，如有）
    │           [3..N-1] HumanMessage/AIMessage（近期对话，token 预算约束）
    │           [N] HumanMessage（当前用户消息）
    │
    ├── [有图片分析] 在位置 1 插入:
    │       SystemMessage("用户发送了一张图片，分析如下：{分析文本}
    │                       请根据这个图片内容来回答用户的问题。")
    │
    ├── ChatGraph.create_app() → LangGraph Agent 执行
    │       └── LLM (deepseek-v3.2) + tools (get_time, search_knowledge_base)
    │
    ├── SSE 流式返回:
    │       {"content": "..."}  — 文本内容
    │       {"audio": "base64"} — TTS 音频（WebSocket 双工流式）
    │       [DONE]
    │
    └── _save_message() 保存到数据库:
            Message(image_url, image_caption, image_analysis=JSONField, ...)
```

---

### 图片分析结果的上下文注入

分析文本通过 **两个途径** 注入 LLM 上下文：

**途径 1 — 系统提示词模板渲染**：
`ContextBuilder._build_system_prompt()` 将 `image_analysis` 传入 `PromptTemplateManager.create_system_prompt()`，渲染模板中的 `{{ image_analysis }}` 占位符。经过 HTML 转义 + 安全转义后注入，防止 prompt 注入。

**途径 2 — 独立 SystemMessage 插入**：
`event_stream()` 中在系统提示词之后（位置 1）显式插入一条 SystemMessage，格式为 `"用户发送了一张图片，分析如下：{分析文本}\n\n请根据这个图片内容来回答用户的问题。"`，确保 LLM 明确注意到图片内容。

---

### 数据模型

`Message` 模型中与图片相关的字段：

| 字段 | 类型 | 内容 |
|---|---|---|
| `image_url` | CharField(500) | 图片访问路径 `/media/images/{friend_id}/{filename}` |
| `image_caption` | TextField | 图片分析描述文本（字符串） |
| `image_analysis` | JSONField | 完整分析结果 dict（含 analysis/model/timestamp/success） |

`input` 字段也以 JSON 形式存储了完整的图片信息（user_message + image_url + image_caption + image_analysis）。

---

### MCP 工具与 LangGraph Agent 的关系

当前架构中，MCP 工具和 LangGraph Agent 是 **解耦** 的：

```
MCP 工具: 在视图层命令式调用（call_tool_sync），结果注入上下文
LangGraph Agent: 只绑定 get_time 和 search_knowledge_base 工具
```

MCP 工具不由 LangGraph Agent 自主决定调用，而是在视图层预先执行，将结果作为上下文的一部分传给 LLM。这种设计确保图片分析在 LLM 生成前完成，避免 Agent 需要多轮 tool_call 才能获取图片信息。

---

### 文件存储

```
media/
└── images/
    └── {friend_id}/
        └── {uuid}_{original_filename}   # 永久保存的图片文件
```

上传流程使用临时文件作为中转：先写入 `tempfile.NamedTemporaryFile`，复制到永久路径后再删除临时文件。永久文件名使用 UUID 前缀避免冲突。
