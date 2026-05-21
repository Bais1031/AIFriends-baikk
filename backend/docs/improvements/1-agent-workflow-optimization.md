# 1 生产环境就绪改进

## 问题

项目当前处于开发阶段，多处配置和代码仅适用于本地开发，直接投入生产环境存在安全、稳定性和可运维性风险。以下按优先级梳理所有必须修复的环节。

---

## P0 — 不修就上不了线

### 1.1 SECRET_KEY 硬编码

**现状**：`settings.py` 第 27 行写死 `SECRET_KEY = 'django-insecure-ypz026...'`，未从环境变量读取。

**风险**：任何人可伪造 session、密码重置 token、CSRF token。

**修复**：

```python
# settings.py
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY 环境变量未设置")
```

`.env` 和生产环境中设置强随机值：

```bash
# 生成方法
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

### 1.2 DEBUG = True 硬编码

**现状**：`settings.py` 第 30 行写死 `DEBUG = True`，未从环境变量读取。

**风险**：生产环境暴露完整堆栈、settings 内容、SQL 查询。

**修复**：

```python
DEBUG = os.getenv('DJANGO_DEBUG', 'False').lower() in ('true', '1', 'yes')
```

---

### 1.3 ALLOWED_HOSTS 为空

**现状**：`settings.py` 第 32 行 `ALLOWED_HOSTS = []`。

**风险**：DEBUG=False 时 Django 拒绝所有请求；DEBUG=True 时接受所有 Host 头（Host 头注入风险）。

**修复**：

```python
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', '').split(',')
# 生产：DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
```

---

### 1.4 .env 含真实 API Key 且可能已泄露到 git 历史

**现状**：`.env` 包含 `API_KEY="sk-aac9..."`、`TAVILY_API_KEY="tvly-dev-..."`。虽然 `.gitignore` 已排除 `.env`，但若曾经 commit 过则 key 已进入 git 历史。

**修复**：

1. 检查 git 历史：`git log --all --full-history -- '*.env'`
2. 如果曾提交过，用 `git filter-repo` 清除历史或直接轮换所有 key
3. 确认 `.gitignore` 包含 `.env`

---

## P1 — 上线前必修

### 2.1 无 WSGI 服务器

**现状**：使用 `manage.py runserver`（Django 开发服务器），单线程，无并发能力。

**修复**：添加 gunicorn，支持多 worker：

```bash
pip install gunicorn
```

```bash
# 启动命令
gunicorn backend.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 120
```

`--timeout 120` 给 SSE 流式响应留足时间。

---

### 2.2 JWT 黑名单未生效

**现状**：`SIMPLE_JWT` 配置了 `BLACKLIST_AFTER_ROTATION = True`，但 `rest_framework_simplejwt.token_blacklist` 未添加到 `INSTALLED_APPS`。刷新后的旧 token 仍然有效。

**修复**：

```python
# settings.py INSTALLED_APPS
INSTALLED_APPS = [
    ...
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',  # 添加这行
]
```

然后执行迁移：

```bash
python manage.py migrate
```

---

### 2.3 无限流保护

**现状**：所有接口零限流。攻击者可无限调用 LLM 聊天接口，快速消耗 API 额度。

**修复**：使用 DRF 内置 Throttle：

```python
# settings.py
REST_FRAMEWORK = {
    ...
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '10/min',
        'user': '60/min',
    },
}
```

聊天接口单独加更严格的限流：

```python
from rest_framework.throttling import UserRateThrottle

class ChatThrottle(UserRateThrottle):
    rate = '20/min'  # LLM 调用成本高，限制更严

class MessageChatView(APIView):
    throttle_classes = [ChatThrottle]
    ...
```

---

### 2.4 零 Serializer — 无输入校验

**现状**：所有视图裸取 `request.data['field']`，无类型校验、长度限制、格式验证。多处 `int()` 直接转换会 500。`GetListCharacterView` 可查任意用户数据（IDOR）。

**修复**：为每个视图添加 Serializer：

```python
# serializers.py
from rest_framework import serializers

class ChatSerializer(serializers.Serializer):
    friend_id = serializers.IntegerField()
    message = serializers.CharField(max_length=5000)

class MessageChatView(APIView):
    def post(self, request):
        serializer = ChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        friend_id = serializer.validated_data['friend_id']
        message = serializer.validated_data['message'].strip()
        ...
```

IDOR 修复：`GetListCharacterView` 应只返回当前用户的数据，而非接受任意 `user_id`。

---

### 2.5 文件上传未校验

**现状**：`validate_image()` 已实现在 `image_utils.py`，但从未被调用。上传的文件直接保存，无类型、大小、内容校验。

**修复**：在所有接收文件的视图（`CreateCharacterView`、`UpdateCharacterView`、`UpdateProfileView`、`MultiModalChatView`）中调用：

```python
from web.utils.image_utils import ImageProcessor

if image_file:
    is_valid, error = ImageProcessor.validate_image(image_file, max_size_mb=5)
    if not is_valid:
        return Response({'error': error}, status=400)
```

---

### 2.6 35+ print 替代日志，零 LOGGING 配置

**现状**：全项目用 `print()` 输出调试信息，`settings.py` 无 `LOGGING` 配置。生产环境下日志无级别、无轮转、无持久化。

**修复**：

```python
# settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'app.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'web': {
            'handlers': ['console', 'file'],
            'level': os.getenv('LOG_LEVEL', 'INFO'),
        },
    },
}
```

然后逐步将 `print()` 替换为 `logger.info()` / `logger.warning()` / `logger.error()`。

---

### 2.7 异常返回 HTTP 200

**现状**：多个视图的 `except` 块返回 `Response({'result': '系统异常'})` 但 HTTP 状态码为 200。监控系统无法发现错误。

**修复**：所有错误响应对应正确的 HTTP 状态码：

```python
# 参数错误
return Response({'error': '...'}, status=400)
# 未找到
return Response({'error': '...'}, status=404)
# 服务端异常
return Response({'error': '...'}, status=500)
```

---

### 2.8 IDOR — 越权访问

**现状**：`GetListCharacterView` 接受 `user_id` 参数，任意已认证用户可查询其他用户的角色数据。

**修复**：只允许查询自己的数据：

```python
# 改动前
user_id = request.query_params.get('user_id')
profile = UserProfile.objects.get(pk=user_id)

# 改动后
profile = request.user.userprofile
```

---

## P2 — 上线后尽快补

### 3.1 无 Docker / 容器化

**现状**：无 Dockerfile、docker-compose。

**修复**：创建 Dockerfile 和 docker-compose.yml，统一部署环境。

---

### 3.2 无 HTTPS 安全头

**现状**：`SESSION_COOKIE_SECURE=False`，无 HSTS，无 `SECURE_SSL_REDIRECT`。

**修复**：

```python
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_REFERRER_POLICY = 'same-origin'
```

---

### 3.3 无数据库连接池

**现状**：无 `CONN_MAX_AGE`，每次请求新建连接。

**修复**：

```python
DATABASES['default']['CONN_MAX_AGE'] = 60  # 连接复用 60 秒
DATABASES['default']['CONN_HEALTH_CHECKS'] = True
```

高并发场景可考虑 pgbouncer。

---

### 3.4 STATIC_ROOT 被注释 / MEDIA_URL 硬编码 localhost

**现状**：`STATIC_ROOT` 注释导致 `collectstatic` 失败；`MEDIA_URL = 'http://127.0.0.1:8000/media/'` 在非本机部署下图片全挂。

**修复**：

```python
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
```

生产环境用 nginx 托管 static/media，或使用 OSS/S3。

---

### 3.5 无健康检查端点

**现状**：无 `/health/` 接口，K8s/Docker 无法探活。

**修复**：

```python
# urls.py
path('health/', HealthCheckView.as_view()),

# views.py
class HealthCheckView(APIView):
    permission_classes = []
    def get(self, request):
        return Response({'status': 'ok'})
```

---

### 3.6 无 Sentry / 错误追踪

**现状**：线上问题无法感知，全靠用户反馈。

**修复**：

```bash
pip install sentry-sdk
```

```python
# settings.py
import sentry_sdk
sentry_sdk.init(dsn=os.getenv('SENTRY_DSN'), traces_sample_rate=0.1)
```

---

### 3.7 无 settings 分层

**现状**：单 `settings.py` 管理开发和生产配置。

**修复**：拆分为 `settings/base.py`、`settings/dev.py`、`settings/prod.py`，通过 `DJANGO_SETTINGS_MODULE` 切换。

---

## 优先级总览

| 优先级 | 编号 | 改进项 | 工作量 |
|--------|------|--------|--------|
| P0 | 1.1 | SECRET_KEY 从环境变量读取 | 小 |
| P0 | 1.2 | DEBUG 从环境变量读取 | 小 |
| P0 | 1.3 | ALLOWED_HOSTS 从环境变量读取 | 小 |
| P0 | 1.4 | 检查 git 历史中的 key 泄露 | 小 |
| P1 | 2.1 | 添加 gunicorn WSGI 服务器 | 小 |
| P1 | 2.2 | 注册 JWT blacklist app | 小 |
| P1 | 2.3 | 添加接口限流 | 小 |
| P1 | 2.4 | 添加 Serializer 输入校验 | 中 |
| P1 | 2.5 | 调用文件上传校验 | 小 |
| P1 | 2.6 | 替换 print 为 logging | 中 |
| P1 | 2.7 | 错误响应使用正确 HTTP 状态码 | 小 |
| P1 | 2.8 | 修复 IDOR 越权访问 | 小 |
| P2 | 3.1 | Docker 容器化 | 中 |
| P2 | 3.2 | HTTPS 安全头 | 小 |
| P2 | 3.3 | 数据库连接池 | 小 |
| P2 | 3.4 | STATIC_ROOT / MEDIA_URL 修复 | 小 |
| P2 | 3.5 | 健康检查端点 | 小 |
| P2 | 3.6 | Sentry 错误追踪 | 小 |
| P2 | 3.7 | Settings 分层 | 中 |
