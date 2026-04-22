# AIFriends

一个基于 Django + Vue 3 的全栈 AI 聊天应用，支持创建虚拟角色、与它们聊天、语音合成和图片对话等功能。

## 核心功能

- **角色创建**: 自定义 AI 角色的性格、外观和背景
- **智能对话**: 基于 LangChain/LangGraph 的双 Agent 架构（对话 Agent + 记忆 Agent）
- **长期记忆**: AI 会记住对话内容，随着时间积累更了解你
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

### 1. 启动 Ollama
```bash
ollama serve
ollama pull qwen2.5:3b
```

### 2. 启动 Redis
```bash
docker run -d --name aifriends-redis -p 6379:6379 redis:alpine
```

### 3. 后端
```bash
cd backend
pip install django-redis
python manage.py migrate
python manage.py runserver
```

### 4. 前端
```bash
cd frontend
npm install
npm run dev
```

## 项目结构

```
AIFriends/
├── backend/          # Django 后端
│   ├── web/          # 核心业务逻辑
│   │   ├── models/   # 数据模型
│   │   ├── views/    # API 视图
│   │   │   └── friend/message/chat/multimodal.py  # 图片聊天
│   │   └── utils/token_cache.py  # Token 缓存工具
│   ├── mcp/          # MCP 工具集成
│   └── docs/         # 技术文档
└── frontend/         # Vue 3 前端
    ├── src/
    │   ├── components/  # 可复用组件
    │   ├── views/      # 页面视图
    │   └── stores/     # Pinia 状态
    └── package.json
```

## 环境变量

后端需要配置 `.env` 文件：

```bash
# 阿里云 API（TTS 和 Embeddings）
API_KEY="sk-..."
API_BASE="https://dashscope.aliyuncs.com/compatible-mode/v1"
WSS_URL="wss://dashscope.aliyuncs.com/api-ws/v1/inference"

# Ollama
OLLAMA_BASE_URL="http://localhost:11434"
OLLAMA_MODEL="qwen2.5:3b"

# Redis（用于缓存和会话）
REDIS_URL="redis://127.0.0.1:6379"
```

## 新增功能

### 图片聊天
- 支持 `/api/friend/message/chat/multimodal` 端点
- 图片上传后自动分析（MCP 工具）
- 分析结果作为系统提示注入对话上下文
- 图片和消息一并保存到数据库

### Redis 缓存
- Token 缓存：避免重复计算文本 Token 数量
- 会话存储：用户登录状态和会话数据
- 查询缓存：常用查询结果缓存

### 混合检索（Hybrid Search）
- 向量检索（语义相似度）+ BM25 关键词检索，加权融合
- 中文分词（jieba），中文语义分隔符优化切分
- 默认权重：70% 语义 + 30% 关键词（alpha 可调）
