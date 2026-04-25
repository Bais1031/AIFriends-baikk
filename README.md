# VoxMind - 多模态语音 Agent 系统

一个基于 Django + Vue 3 的全栈 AI 聊天应用，支持创建虚拟角色、与它们聊天、语音合成和图片对话等功能。

## 核心功能

- **角色创建**: 自定义 AI 角色的性格、外观和背景
- **智能对话**: 基于 LangChain/LangGraph 的双 Agent 架构（对话 Agent + 记忆 Agent）
- **语音交互**: 支持语音输入（ASR）和语音输出（TTS）
- **图片消息**: 支持发送图片进行对话，自动分析图片内容
- **Redis 缓存**: Token 缓存和会话存储，提升响应速度
- **混合检索**: 向量检索 + BM25 关键词检索，提升 RAG 检索准确率

## 技术栈

### 后端
- Django 6.0 + REST Framework
- JWT 认证
- LangChain + LangGraph（Agent 编排）
- SQLite + Redis（缓存和会话存储）
- SSE 流式响应
- MCP 工具（图片分析）

### 前端
- Vue 3.5 + Vite
- Pinia 状态管理
- TailwindCSS + DaisyUI
- WebSocket（TTS 语音流）

## Redis 架构

```
DB0: Token 缓存 + 查询缓存
DB1: 会话存储
```

## 快速开始

### 1. 启动 Redis
```bash
docker run -d --name aifriends-redis -p 6379:6379 redis:alpine
```

### 2. 后端
```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### 3. 前端
```bash
cd frontend
npm install
npm run dev
```

## 项目结构

```
AIFriends/
├── backend/              # Django 后端
│   ├── web/
│   │   ├── models/       # 数据模型（Friend, Message, MemoryItem, SystemPrompt）
│   │   ├── views/        # API 视图
│   │   │   └── friend/message/
│   │   │       ├── chat/         # 聊天视图（文本 + 多模态）
│   │   │       └── memory/       # 记忆更新（MemoryGraph + 增量提取）
│   │   ├── utils/
│   │   │   ├── context_builder.py    # 上下文构建器（短期记忆核心）
│   │   │   ├── token_cache.py        # Token 估算与预算管理
│   │   │   ├── embedding.py          # 向量嵌入（阿里云 text-embedding-v3）
│   │   │   ├── memory_retrieval.py   # 语义检索 + 权重衰减
│   │   │   └── prompt_template.py    # Prompt 模板引擎（防注入）
│   │   └── graphs/       # LangGraph Agent 定义
│   ├── mcp/              # MCP 工具集成
│   └── docs/             # 技术文档
└── frontend/             # Vue 3 前端
    ├── src/
    │   ├── components/   # 可复用组件
    │   ├── views/        # 页面视图
    │   └── stores/       # Pinia 状态
    └── package.json
```

## 环境变量

后端需要配置 `.env` 文件：

```bash
# 阿里云 API（LLM / TTS / Embeddings）
API_KEY="sk-..."
API_BASE="https://dashscope.aliyuncs.com/compatible-mode/v1"
WSS_URL="wss://dashscope.aliyuncs.com/api-ws/v1/inference"

# Redis（用于缓存和会话）
REDIS_URL="redis://127.0.0.1:6379"
```

## 其他功能

### 图片聊天
- 支持 `/api/friend/message/chat/multimodal` 端点
- 图片上传后自动分析（MCP 工具）
- 分析结果作为系统提示注入对话上下文

### 混合检索（Hybrid Search）
- 向量检索（语义相似度）+ BM25 关键词检索，加权融合
- 中文分词（jieba），中文语义分隔符优化切分
- 默认权重：70% 语义 + 30% 关键词（alpha 可调）

### 短期记忆
- Token 预算管理：总预算 4096，分区预留（系统提示 1500 / 摘要 500 / 消息 2096）
- 动态消息窗口：从最新往前取，累计 token 不超预算，替代固定 10 条窗口
- 自动对话摘要：每 20 条新消息触发 LLM 摘要，与已有摘要合并
- 中英文 Token 估算：中文 1token≈1.5字 / 英文按词×1.3 / 标点字符÷2

### 长期记忆
- 结构化存储：`MemoryItem` 模型，每条记忆独立存储（content / category / importance / weight / embedding）
- 记忆分类：preference(偏好) / event(事件) / fact(事实) / emotion(情感) / general(通用)
- 增量提取 + 语义去重：LLM 提取 JSON 记忆点，余弦相似度 ≥ 0.85 视为重复，重复提及自动提升权重
- 语义检索注入：每次对话只注入 top-K 条相关记忆，替代全量灌入
- 权重衰减：半衰期 30 天，权重低于 0.05 自动归档删除
