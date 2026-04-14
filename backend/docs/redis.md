# Redis 缓存配置指南

## 概述

本文档详细说明了 AIFriends 项目中 Redis 缓存配置的实施步骤、使用方法和监控策略。

### Redis 在项目中的角色

| 功能 | 说明 | Redis DB |
|------|------|----------|
| **会话存储** | 用户登录状态和会话数据 | DB1 |
| **Token 缓存** | 缓存 Token 计算结果，减少重复计算 | DB0 |
| **查询缓存** | 缓存常用查询结果，减少数据库压力 | DB0 |
| **未来扩展** | 任务队列、分布式锁、实时通知等 | DB2-3 |

### 架构示意

```
┌─────────────────────────────────────────────────┐
│                    Django 应用                   │
├───────────────┬───────────────┬──────────────┤
│   业务逻辑    │   缓存逻辑    │   会话管理        │
│  (查询数据)   │ (Redis缓存)   │ (Redis会话)      │
└───────────────┴───────────────┴──────────────┘
       │                 │               │
       ▼                 ▼               ▼
┌─────────────────────────────────────────────────┐
│                数据层                            │
├───────────────────────┬─────────────────────────────┤
│   PostgreSQL         │        Redis                │
│  (持久化数据)      │  (缓存数据)               │
│                       │                             │
│  • 用户数据          │  • Token 缓存                │
│  • 消息记录          │  • 会话存储                  │
│  • 角色信息          │  • 查询缓存                  │
│  • 系统提示词          │  • 分布式锁                  │
│                       │  • 消息队列                  │
└───────────────────────┴─────────────────────────────┘
```

---

## 一、Redis 服务部署

### 1.1 Docker 方式（推荐）

```bash
# 运行 Redis
docker run -d \
  --name aifriends-redis \
  -p 6379:6379 \
  -v redis_data:/data \
  redis:alpine \
  redis-server --appendonly yes

# 验证运行
docker ps | grep aifriends-redis
docker exec aifriends-redis redis-cli ping  # 应返回 PONG
```

### 1.2 本地安装方式

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install redis-server
sudo systemctl start redis
sudo systemctl enable redis

# 验证
redis-cli ping  # 应返回 PONG
```

---

## 二、Django 配置

### 2.1 安装依赖

```bash
cd /home/jzl/projects/LLM/AIFriends/backend
pip install django-redis
```

### 2.2 配置 settings.py

在 `backend/backend/settings.py` 中添加以下配置：

```python
# ========== Redis 缓存配置 ==========
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/0'),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
            "IGNORE_EXCEPTIONS": True,  # Redis 宕机时不报错
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
        },
        "KEY_PREFIX": "aifriends",
    },
    # 会话专用缓存
    "sessions": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/1'),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "aifriends_session",
    },
}

# ========== 会话存储 ==========
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "sessions"
SESSION_COOKIE_NAME = "aifriends_sid"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = False  # 生产环境改为 True (HTTPS)
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # 7天
```

### 2.3 配置环境变量

在 `backend/.env` 中添加：

```bash
# Redis 配置 (用于缓存和会话)
REDIS_URL="redis://127.0.0.1:6379"
```

---

## 三、Token 缓存实现

### 3.1 Token 缓存工具类

已创建 `backend/web/utils/token_cache.py`，提供以下功能：

```python
from web.utils.token_cache import TokenCache

# 估算 Token 数量（带缓存）
tokens = TokenCache.estimate_tokens("这是一段测试文本")
# 第二次调用相同文本时，直接从缓存获取
tokens = TokenCache.estimate_tokens("这是一段测试文本")  # 命中
```

### 3.2 在 chat.py 中应用

修改 `backend/web/views/friend/message/chat/chat.py`：

```python
# 添加导入
from web.utils.token_cache import TokenCache

# 在 event_stream 函数中使用 Token 缓存
def event_stream(self, app, inputs, friend, message):
    # ... 之前的代码 ...
    
    # 使用 Token 缓存
    input_text = ' '.join([m.content for m in inputs['messages']])
    input_tokens = TokenCache.estimate_tokens(input_text)
    output_tokens = TokenCache.estimate_tokens(full_output)
    total_tokens = input_tokens + output_tokens
    
    Message.objects.create(
        # ... 其他字段 ...
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )
```

---

## 四、Redis 命令参考

### 4.1 常用监控命令

```bash
# 连接 Redis
docker exec -it aifriends-redis redis-cli
# 或
redis-cli -h 127.0.0.1 -p 6379

# 查看 Redis 信息
INFO
# 或特定信息
INFO memory
INFO stats
INFO keyspace
INFO replication

# 查看所有 key
KEYS "*"
KEYS "aifriends:*"

# 查看特定 key
GET "aifriends:token_count:..."

# 删除特定 key
DEL "key_name"

# 清空当前数据库
FLUSHDB
# 清空所有数据库（危险！）
FLUSHALL

# 查看数据大小
DBSIZE

# 实时监控所有命令
MONITOR
```

### 4.2 缓存相关操作

```bash
# 查看 Token 缓存数量
docker exec aifriends-redis redis-cli KEYS "aifriends:token:*" | wc -l

# 查看会话数量
docker exec aifriends-redis redis-cli KEYS "aifriends_session:*" | wc -l

# 清空 Token 缓存
docker exec aifriends-redis redis-cli --scan --pattern "aifriends:token:*" | xargs redis-cli DEL

# 设置测试缓存
SET "test:key" "test_value" EX 60  # 60秒后过期

# 获取缓存
GET "test:key"

# 检查缓存是否存在
EXISTS "test:key"

# 查看缓存剩余时间
TTL "test:key"
```

---

## 五、性能测试

### 5.1 延迟测试

```python
# 创建测试文件 backend/test_redis_latency.py
import time
from django.core.cache import cache

# 写入延迟测试
start = time.perf_counter()
cache.set('test_key', 'test_value', timeout=60)
write_time = (time.perf_counter() - start) * 1000  # ms

# 读取延迟测试
start = time.perf_counter()
result = cache.get('test_key')
read_time = (time.perf_counter() - start) * 1000  # ms

print(f"写入延迟: {write_time:.3f} ms")
print(f"读取延迟: {read_time:.3f} ms")

# 预期结果（优秀）:
# 写入延迟: <1 ms
# 读取延迟: <1 ms
```

### 5.2 缓存命中率测试

```python
# 模拟用户请求，测试缓存命中率
from web.utils.token_cache import TokenCache

# 第一次调用（未命中）
tokens1 = TokenCache.estimate_tokens("你好")

# 第二次调用（命中）
tokens2 = TokenCache.estimate_tokens("你好")

# 验证结果
print(f"Token 数量: {tokens1}")
print(f"应该相等: {tokens1 == tokens2}")  # True 表示命中
```

### 5.3 吞吐量测试

```bash
# 批量写入测试
time redis-cli --pipe <<EOF
SET bench:1 "v1"
SET bench:2 "v2"
SET bench:3 "v3"
...
EOF

# 批量读取测试
time redis-cli --pipe <<EOF
GET bench:1
GET bench:2
GET bench:3
...
EOF
```

---

## 六、监控和运维

### 6.1 实时监控

```bash
# 使用 watch 实时监控
watch -n 2 '
echo "=== Redis 状态 $(date +%H:%M:%S) ==="
docker exec aifriends-redis redis-cli INFO | grep -E "used_memory_human|connected_clients|total_commands_received|keyspace_hits|keyspace_misses"
echo ""
echo "缓存数据量:"
docker exec aifriends-redis redis-cli DBSIZE
echo "Token 缓存数量:"
docker exec aifriends-redis redis-cli KEYS "aifriends:token:*" | wc -l
echo "会话数量:"
docker exec aifriends-redis redis-cli KEYS "aifriends_session:*" | wc -l
'
```

### 6.2 性能指标解读

| 指标 | 优秀 | 良好 | 需要优化 |
|------|------|------|----------|
| 平均延迟 | <1ms | 1-3ms | >3ms |
| 缓存命中率 | >80% | 60-80% | <60% |
| 吞吐量 | >50000/s | 20000-50000/s | <20000/s |
| 内存使用 | <100MB | 100-500MB | >500MB |
| 连接数 | <10 | 10-50 | >50 |

### 6.3 日志和告警

```python
# settings.py 中添加日志配置
LOGGING = {
    'version': 1,
    'handlers': {
        'redis_file': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/aifriends/redis.log',
            'maxBytes': 1024*1024*10,
            'backupCount': 5,
        },
    },
    'loggers': {
        'django_redis': {
            'handlers': ['redis_file'],
            'level': 'WARNING',
        },
    },
}
```

---

## 七、故障排查

### 7.1 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 连接被拒绝 | Redis 未启动 | `docker start aifriends-redis` |
| 缓存未生效 | URL 配置错误 | 检查 `.env` 中 `REDIS_URL` |
| 内存占用高 | 数据过期时间过长 | 检查缓存 TTL 设置 |
| 性能下降 | 网络延迟 | 检查 Docker 网络配置 |

### 7.2 诊断命令

```bash
# 检查连接
docker exec aifriends-redis redis-cli ping

# 检查配置
docker exec aifriends-redis redis-cli CONFIG GET "*"

# 检查慢查询
docker exec aifriends-redis redis-cli SLOWLOG GET 10

# 检查客户端连接
docker exec aifriends-redis redis-cli CLIENT LIST

# 检查内存使用详情
docker exec aifriends-redis redis-cli MEMORY USAGE "key_name"
```

---

## 八、生产环境注意事项

### 8.1 安全配置

```python
# 生产环境 Redis 配置
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://:password@host:port/0",  # 使用密码认证
        "OPTIONS": {
            "SSL": True,  # 启用 SSL/TLS
            "CONNECTION_POOL_KWARGS": {
                "max_connections": 50,
                "retry_on_timeout": True,
            },
        },
    }
}

# 生产环境会话配置
SESSION_COOKIE_SECURE = True  # 仅 HTTPS
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
```

### 8.2 持久化配置

```bash
# Redis 持久化配置 (docker 运行时）
docker run -d \
  --name aifriends-redis \
  -p 6379:6379 \
  -v redis_data:/data \
  -v $(pwd)/redis.conf:/usr/local/etc/redis/redis.conf \
  redis:alpine \
  redis-server /usr/local/etc/redis/redis.conf

# redis.conf 示例配置
appendonly yes
save 900 1
save 300 10
save 60 10000
```

---

## 九、优化建议

### 9.1 缓存策略

| 场景 | 建议策略 | TTL |
|------|----------|-----|
| Token 缓存 | 固定过期 | 24小时 |
| 用户信息 | 用户活跃时更新 | 1小时 |
| 首页数据 | 高峰期短缓存 | 5分钟 |
| API 响应 | 固定过期 | 30分钟 |

### 9.2 性能优化

1. **使用连接池**
```python
"CONNECTION_POOL_KWARGS": {
    "max_connections": 50,
    "retry_on_timeout": True,
}
```

2. **启用压缩**
```python
"COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
```

3. **合理设置过期时间**
```python
# 避免内存无限增长
cache.set(key, value, timeout=3600)  # 1小时
```

---

## 十、扩展功能（未来）

| 功能 | 用途 | 实现难度 |
|------|------|----------|
| **任务队列** | 异步处理消息、记忆更新 | 中 |
| **分布式锁** | 防止重复操作 | 低 |
| **Pub/Sub** | 实时通知 | 中 |
| **布隆过滤器** | 快速判断数据是否存在 | 中 |

---

## 参考资源

- [Django-Redis 官方文档](https://github.com/jazzband/django-redis)
- [Redis 命令参考](https://redis.io/commands/)
- [Redis 性能优化](https://redis.io/topics/memory-optimization/)

---

**文档版本**: 1.0  
**更新日期**: 2026-04-14  
**维护者**: AIFriends Team
