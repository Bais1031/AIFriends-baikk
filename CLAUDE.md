# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作时提供指导。

## 项目结构

AIFriends 是一个使用 Django 后端和 Vue 3 前端的全栈 AI 聊天应用。用户可以创建 AI 角色、与它们聊天，并管理具备语音合成功能的对话。

### 架构概览
- **后端**: Django 6.0 + REST Framework + JWT 认证
- **前端**: Vue 3.5.28 + Vite + Pinia 状态管理
- **AI 集成**: LangChain + LangGraph 用于 Agent 编排
- **数据库**: SQLite（生产计划：迁移到 PostgreSQL）
- **缓存**: Redis 用于 Token 缓存和会话存储
- **实时通信**: SSE 用于聊天流式传输，WebSocket 用于 TTS

## 常用命令

### 后端 (Django)
```bash
cd backend
# 启动开发服务器
python manage.py runserver

# 运行测试（如果有）
python manage.py test

# 创建迁移
python manage.py makemigrations
python manage.py migrate

# 创建 Django 管理员账号
python manage.py createsuperuser
```

### 前端 (Vue/Vite)
```bash
cd frontend
# 安装依赖
npm install

# 开发服务器（端口 5173）
npm run dev


# 生产构建
npm run build
```

### Ollama (LLM 服务)
```bash
# 启动 Ollama 服务器
ollama serve

# 拉取模型
ollama pull qwen2.5:3b  # 3B 参数中文模型
```

### Redis
```bash
# 启动 Redis (Docker)
docker run -d --name aifriends-redis -p 6379:6379 redis:alpine

# 测试连接
redis-cli ping

# 查看 Redis 信息
redis-cli INFO
```

## 核心组件

### 后端视图
- **认证** (`/api/user/account/`): JWT 登录、注册、刷新 Token
- **角色** (`/api/create/character/`): AI 角色的 CRUD 操作
- **好友** (`/api/friend/`): 用户-AI 角色关系管理
- **聊天** (`/api/friend/message/chat/`): SSE 流式聊天接口
- **记忆** (`/api/friend/message/memory/`): 长期记忆管理

### AI Agents
- **聊天图**: LangGraph Agent，带时间查询和知识库搜索工具
- **记忆图**: 独立的 Agent 用于更新角色记忆
- **Token 缓存**: 基于 Redis 的 Token 估算，避免重复计算

### 前端流式处理
- 聊天响应使用 Server-Sent Events (SSE)，通过 `@microsoft/fetch-event-source`
- TTS 使用 WebSocket 流式传输，配合阿里云 SpeechSynthesizer

## 环境配置

### 后端 (.env)
```bash
# 阿里云 API 用于 TTS 和 Embeddings
API_KEY="sk-..."
API_BASE="https://dashscope.aliyuncs.com/compatible-mode/v1"
WSS_URL="wss://dashscope.aliyuncs.com/api-ws/v1/inference"

# Ollama 用于聊天和记忆
OLLAMA_BASE_URL="http://localhost:11434"
OLLAMA_MODEL="qwen2.5:3b"

# Redis 用于缓存
REDIS_URL="redis://127.0.0.1:6379"
```

## 数据库模型

### UserProfile
- 用户资料扩展，包含头像处理
- 作为创建者与 Friend 关联

### Character
- AI 角色定义（名称、简介、头像）
- 性格和外观设置

### Friend
- 连接 UserProfile 和 Character 的中间模型
- 存储长期记忆和对话上下文

### Message
- 带有 Token 计数的聊天历史
- 分别存储输入/输出及其 Token 数量

### SystemPrompt
- AI 响应的可配置系统提示词
- 支持排序的多个提示词

## 开发模式

### API 视图
- 所有视图使用 Django REST Framework 类
- 除登录/注册外，所有端点都需要认证
- 视图遵循一致的错误响应格式

### 流式响应
- 使用 `StreamingHttpResponse` 配合 text/event-stream 内容类型
- 设置 Cache-Control: no-cache 和 X-Accel-Buffering: no
- 以正确的 SSE 格式 yield JSON 数据

### Agent 集成
- LangGraph agents 在每次请求时创建
- 工具必须在编译前绑定到 LLM
- 通过 TypedDict 和 add_messages 注解进行状态管理

### Token 缓存
- 所有 Token 估算使用 `web.utils.token_cache.TokenCache`
- 缓存键格式: "token_count:{model}:{hash(text)}"
- 缓存值 24 小时过期
- 未命中时回退到简单的基于长度的估算

## 重要说明

- 聊天和记忆 agents 目前配置使用阿里云的 DeepSeek v3.2 API
- TTS 服务通过 WebSocket 使用阿里云 CosyVoice-v3-flash 模型
- 使用阿里云 API 实现了知识库的自定义 embeddings
- Redis 配置了独立的数据库：DB0 用于缓存，DB1 用于会话
- 前端已启用开发模式热重载
- CORS 配置允许来自 http://localhost:5173 的请求

## 文件组织

- 后端逻辑在 `backend/web/`，遵循 Django 应用约定
- 前端组件在 `frontend/src/components/`，按功能分类
- 技术文档在 `backend/docs/`
- 静态资源在 `frontend/public/` 和 `backend/static/`
- 上传的媒体文件在 `backend/media/`