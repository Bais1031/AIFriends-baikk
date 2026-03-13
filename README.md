# A huge begining!
# AIFriends项目代码结构说明

## 项目概述

这是一个基于 **Django 6.0** + **Vue 3** 的全栈 AI 聊天应用项目，支持创建虚拟角色、好友聊天、语音合成等功能。

---

## 技术栈

### 后端 (Backend)
- **框架**: Django 6.0
- **认证**: JWT (SimpleJWT)
- **API**: Django REST Framework
- **数据库**: SQLite3
- **AI 集成**: LangChain
- **实时通信**: WebSocket (TTS 语音合成)

### 前端 (Frontend)
- **框架**: Vue 3.5.28
- **状态管理**: Pinia 3.0.4
- **路由**: Vue Router 5.0.2
- **HTTP 客户端**: Axios
- **构建工具**: Vite 7.3.1
- **UI 框架**: TailwindCSS 4.x + DaisyUI
- **语音处理**: @ricky0123/vad-web
- **SSE 流式接收**: @microsoft/fetch-event-source

---

## 完整目录结构

PythonProject1/  
├── backend/                          # 后端项目根目录  
│   ├── backend/                      # Django 配置目录  
│   │   ├── asgi.py                   # ASGI 入口  
│   │   ├── settings.py               # Django 配置文件  
│   │   ├── urls.py                   # 主路由配置  
│   │   └── wsgi.py                   # WSGI 入口  
│   ├── web/                          # 核心业务应用  
│   │   ├── models/                   # 数据模型  
│   │   │   ├── character.py          # 角色模型  
│   │   │   ├── friend.py             # 好友和消息模型  
│   │   │   └── user.py               # 用户模型  
│   │   ├── views/                    # 视图层  
│   │   │   ├── create/character/     # 角色创建相关  
│   │   │   │   ├── create.py         # 创建角色  
│   │   │   │   ├── get_list.py       # 获取角色列表  
│   │   │   │   ├── get_single.py     # 获取单个角色  
│   │   │   │   ├── remove.py         # 删除角色  
│   │   │   │   └── update.py         # 更新角色  
│   │   │   ├── friend/               # 好友相关  
│   │   │   │   ├── message/          # 消息处理  
│   │   │   │   │   ├── asr/          # 语音识别  
│   │   │   │   │   ├── chat/         # 聊天功能  
│   │   │   │   │   │   ├── chat.py   # 流式聊天 API  
│   │   │   │   │   │   └── graph.py  # 聊天图编排  
│   │   │   │   │   ├── memory/       # 记忆管理  
│   │   │   │   │   │   ├── graph.py  # 记忆图  
│   │   │   │   │   │   └── update.py # 更新记忆  
│   │   │   │   │   └── get_history.py# 获取聊天记录  
│   │   │   │   ├── get_list.py       # 获取好友列表  
│   │   │   │   ├── get_or_create.py  # 获取或创建好友  
│   │   │   │   └── remove.py         # 删除好友  
│   │   │   ├── homepage/             # 首页  
│   │   │   │   └── index.py          # 首页视图  
│   │   │   ├── profile/              # 个人资料  
│   │   │   │   └── update.py         # 更新资料  
│   │   │   ├── user/account/         # 用户账户  
│   │   │   │   ├── get_user_info.py  # 获取用户信息  
│   │   │   │   ├── login.py          # 登录  
│   │   │   │   ├── logout.py         # 登出  
│   │   │   │   ├── refresh_token.py  # 刷新 Token  
│   │   │   │   └── register.py       # 注册  
│   │   │   ├── user/utils/           # 用户工具类  
│   │   │   │   └── photo.py          # 头像处理  
│   │   │   └── index.py              # 索引页  
│   │   ├── documents/utils/          # 文档处理工具  
│   │   │   ├── custom_embeddings.py  # 自定义嵌入  
│   │   │   └── insert_documents.py   # 插入文档  
│   │   ├── migrations/               # 数据库迁移文件  
│   │   ├── templates/                # Django 模板  
│   │   │   └── index.html            # 主页模板  
│   │   ├── admin.py                  # Django Admin 配置  
│   │   ├── apps.py                   # 应用配置  
│   │   ├── tests.py                  # 测试文件  
│   │   ├── urls.py                   # Web 应用路由  
│   │   └── views.py                  # 视图入口  
│   └── manage.py                     # Django 管理脚本  
│  
├── frontend/                         # 前端项目根目录  
│   ├── src/                          # 源代码目录  
│   │   ├── assets/                   # 静态资源  
│   │   │   └── main.css              # 全局样式  
│   │   ├── components/               # 可复用组件  
│   │   │   ├── character/            # 角色相关组件  
│   │   │   │   ├── chat_field/       # 聊天输入区域  
│   │   │   │   │   ├── character_photo_field/  
│   │   │   │   │   │   └── CharacterPhotoField.vue  # 角色照片上传  
│   │   │   │   │   ├── chat_history/ # 聊天记录展示  
│   │   │   │   │   │   ├── message/  # 消息组件  
│   │   │   │   │   │   └── ChatHistory.vue         # 聊天历史  
│   │   │   │   │   ├── input_field/  # 输入框组件  
│   │   │   │   │   └── ChatField.vue # 聊天字段主组件  
│   │   │   │   └── Character.vue     # 角色主组件  
│   │   │   └── navbar/               # 导航栏组件  
│   │   │       ├── icon/             # 图标组件集  
│   │   │       │   ├── CameraIcon.vue        # 相机图标  
│   │   │       │   ├── CreateIcon.vue        # 创建图标  
│   │   │       │   ├── FriendIcon.vue        # 好友图标  
│   │   │       │   ├── HomePageIcon.vue      # 首页图标  
│   │   │       │   ├── KeyboardIcon.vue      # 键盘图标  
│   │   │       │   ├── LoginIcon.vue         # 登录图标  
│   │   │       │   ├── MenuIcon.vue          # 菜单图标  
│   │   │       │   ├── MicIcon.vue           # 麦克风图标  
│   │   │       │   ├── RemoveIcon.vue        # 删除图标  
│   │   │       │   ├── SearchIcon.vue        # 搜索图标  
│   │   │       │   ├── SendIcon.vue          # 发送图标  
│   │   │       │   ├── UpdateIcon.vue        # 更新图标  
│   │   │       │   ├── UserLogoutIcon.vue    # 登出图标  
│   │   │       │   ├── UserProfileIcon.vue   # 用户资料图标  
│   │   │       │   └── UserSpaceIcon.vue     # 用户空间图标  
│   │   │       ├── NavBar.vue        # 导航栏主组件  
│   │   │       └── UserMenu.vue      # 用户菜单  
│   │   ├── js/                       # JavaScript 工具  
│   │   │   ├── http/                 # HTTP 请求封装  
│   │   │   │   ├── api.js            # API 接口封装  
│   │   │   │   └── streamApi.js      # 流式 API 封装  
│   │   │   └── utils/                # 工具函数  
│   │   │       └── base_64-file.js   # Base64 与文件转换  
│   │   ├── router/                   # Vue Router 配置  
│   │   │   └── index.js              # 路由定义  
│   │   ├── stores/                   # Pinia 状态管理  
│   │   │   ├── counter.js            # 计数器示例  
│   │   │   └── user.js               # 用户状态  
│   │   ├── views/                    # 页面视图  
│   │   │   ├── create/               # 创建页面  
│   │   │   │   ├── character/        # 角色创建  
│   │   │   │   │   ├── components/   # 子组件  
│   │   │   │   │   ├── CreateCharater.vue  # 创建角色页  
│   │   │   │   │   └── UpdateCharacter.vue # 更新角色页  
│   │   │   │   └── CreateIndex.vue   # 创建索引页  
│   │   │   ├── error/                # 错误页面  
│   │   │   │   └── NotFoundIndex.vue # 404 页面  
│   │   │   ├── friend/               # 好友页面  
│   │   │   │   └── FriendIndex.vue   # 好友列表页  
│   │   │   ├── homepage/             # 首页  
│   │   │   │   └── HomepageIndex.vue # 首页视图  
│   │   │   └── user/                 # 用户相关页面  
│   │   │       ├── account/          # 账户管理  
│   │   │       │   ├── LoginIndex.vue    # 登录页  
│   │   │       │   └── RegisterIndex.vue # 注册页  
│   │   │       ├── profile/          # 个人资料  
│   │   │       │   ├── components/   # 子组件  
│   │   │       │   └── ProfileIndex.vue  # 资料页  
│   │   │       └── space/            # 用户空间  
│   │   │           ├── components/   # 子组件  
│   │   │           └── SpaceIndex.vue    # 空间页  
│   │   ├── App.vue                   # Vue 根组件  
│   │   └── main.js                   # Vue 入口文件  
│   ├── .gitignore                    # Git 忽略配置  
│   ├── README.md                     # 前端说明  
│   ├── index.html                    # HTML 模板  
│   ├── jsconfig.json                 # JS 配置  
│   ├── package-lock.json             # 依赖锁定文件  
│   ├── package.json                  # 依赖配置  
│   └── vite.config.js                # Vite 配置  
│  
├── .gitignore                        # 项目 Git 忽略配置  
└── EANME.md                         # 项目说明  

---

## 核心功能模块(建议写成对话Agent和记忆Agent协作)

### 1. 用户认证系统 (`/backend/web/views/user/`)
- **注册**: `register.py` - 用户注册功能
- **登录**: `login.py` - JWT 登录认证
- **登出**: `logout.py` - 用户登出
- **Token 刷新**: `refresh_token.py` - 刷新访问令牌
- **用户信息**: `get_user_info.py` - 获取当前用户信息

### 2. 角色管理系统 (`/backend/web/views/create/character/`)
- **创建角色**: `create.py` - 创建新的虚拟角色
- **角色列表**: `get_list.py` - 获取角色列表
- **单个角色**: `get_single.py` - 获取角色详情
- **更新角色**: `update.py` - 修改角色信息
- **删除角色**: `remove.py` - 删除角色

### 3. 好友聊天系统 (`/backend/web/views/friend/`)
- **好友管理**:
  - `get_list.py` - 好友列表
  - `get_or_create.py` - 获取或创建好友
  - `remove.py` - 删除好友
  
- **消息处理**:
  - **聊天** (`/message/chat/`):
    - `chat.py` - 流式聊天 API，支持 SSE 实时推送
    - `graph.py` - LangChain 聊天图编排
  
  - **记忆管理** (`/message/memory/`):
    - `update.py` - 更新长期记忆
    - `graph.py` - 记忆处理流程
  
  - **语音功能** (`/message/asr/`):
    - `asr.py` - 自动语音识别
  
  - **历史记录** (`/message/get_history.py`):
    - 获取聊天历史记录

### 4. 数据模型 (`/backend/web/models/`)
- **character.py**: 角色模型定义（性格、外观等）
- **friend.py**: 好友关系、消息记录、系统提示词
- **user.py**: 用户资料模型

### 5. 前端核心组件
- **导航系统**: `NavBar.vue` + 图标组件集
- **聊天界面**: `ChatField.vue` + `ChatHistory.vue`
- **角色管理**: `Character.vue` + 创建/更新表单
- **用户菜单**: `UserMenu.vue`

---

## API 路由架构

### 后端路由 (`/backend/web/urls.py`)
### 前端路由 (`/frontend/src/router/index.js`)

## 运行方式
### 后端启动
cd backend
python manage.py runserver
### 前端启动
cd frontend
npm run dev